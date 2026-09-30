"""Dify 知识库同步脚本 —— 把 dify_knowledge 文档按优化分段重传，并切换混合检索。

用法：
    python dify_sync.py                          # dry-run：只显示计划动作
    DIFY_DATASET_API_KEY=dataset-xxx python dify_sync.py --apply --dataset-id <id>

前置条件（缺一不可）：
    1. Docker Desktop 启动且 Dify 容器组在运行（check_services.py 体检）
    2. Dify 知识库已建好，嵌入模型指向本地 bge-m3（host.docker.internal:8081/v1）
    3. Dify 知识库 API Key（dataset- 开头，知识库页面「API」里创建）

行为：
    --apply 时对每个文档：先删除同名旧文档，再按优化分段参数上传
    （按 Markdown 标题分段，段 800 token / 重叠 100），最后把数据集检索
    设置切换为 hybrid_search（向量 0.7 + 全文 0.3）。
"""

from __future__ import annotations

import argparse
import json
import os
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
KNOWLEDGE_DIR = REPO_ROOT / "dify_knowledge"
DEFAULT_BASE = os.environ.get("DIFY_BASE_URL", "http://localhost/v1")

RETRIEVAL_MODEL = {
    "search_method": "hybrid_search",
    "reranking_enable": False,       # llama.cpp 栈暂无 rerank 供应商，用权重混合
    "reranking_mode": "weight",
    "weights": {"weight_type": "semantic", "vector": 0.7, "keyword": 0.3},
    "top_k": 6,
    "score_threshold_enabled": False,
}

PROCESS_RULE = {
    "mode": "custom",
    "rules": {
        "pre_processing_rules": [
            {"id": "remove_extra_spaces", "enabled": True},
            {"id": "remove_urls_emails", "enabled": False},
        ],
        "segmentation": {
            "separator": "\n\n",      # 知识文档均按空行/标题组织，双换行分段最贴结构
            "max_tokens": 800,
            "chunk_overlap": 100,
        },
    },
}


def api(method: str, path: str, key: str, payload: dict = None) -> tuple[int, dict]:
    url = f"{DEFAULT_BASE}{path}"
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {key}")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read())
        except Exception:
            return exc.code, {"error": exc.reason}


def list_existing(dataset_id: str, key: str) -> dict:
    code, body = api("GET", f"/datasets/{dataset_id}/documents?page=1&limit=100", key)
    if code != 200:
        raise SystemExit(f"获取文档列表失败（{code}）：{body}——检查 dataset-id 与 API Key")
    return {doc["name"]: doc["id"] for doc in body.get("data", [])}


def main() -> None:
    parser = argparse.ArgumentParser(description="Dify 知识库同步（dify_knowledge → Dify）")
    parser.add_argument("--dataset-id", default=os.environ.get("DIFY_DATASET_ID"))
    parser.add_argument("--apply", action="store_true", help="真实执行（默认 dry-run）")
    args = parser.parse_args()

    docs = sorted(KNOWLEDGE_DIR.glob("*.md"))
    print(f"待同步文档：{[d.name for d in docs]}")
    print(f"计划检索配置：{json.dumps(RETRIEVAL_MODEL, ensure_ascii=False)}")
    print(f"计划分段：按 '\\n\\n' 分段，max_tokens=800，overlap=100\n")

    key = os.environ.get("DIFY_DATASET_API_KEY", "")
    if not args.apply:
        print("当前为 dry-run，未连接 Dify。执行同步：")
        print(f"  DIFY_DATASET_API_KEY=dataset-xxx python dify_sync.py --apply"
              + (f" --dataset-id {args.dataset_id}" if args.dataset_id else ""))
        return

    if not key:
        raise SystemExit("缺少 DIFY_DATASET_API_KEY 环境变量（dataset- 开头）")
    if not args.dataset_id:
        raise SystemExit("缺少 --dataset-id")

    existing = list_existing(args.dataset_id, key)
    for doc in docs:
        name = doc.stem  # 文件名即文档名，便于幂等替换
        if name in existing:
            code, body = api("DELETE",
                             f"/datasets/{args.dataset_id}/documents/{existing[name]}", key)
            print(f"  删除旧文档 {name}：{code}")
        code, body = api("POST", f"/datasets/{args.dataset_id}/document/create-by-text", key, {
            "name": name,
            "text": doc.read_text(encoding="utf-8"),
            "indexing_technique": "high_quality",
            "process_rule": PROCESS_RULE,
        })
        print(f"  上传 {name}：{code}" + ("" if code == 200 else f" {body}"))

    code, body = api("PATCH", f"/datasets/{args.dataset_id}", key,
                     {"retrieval_model": RETRIEVAL_MODEL})
    print(f"  更新检索配置：{code}" + ("" if code == 200 else f" {body}"))
    print("\n完成。到 Dify「命中测试」页验证：'抽样怎么做的' 应命中 02_methodology。")


if __name__ == "__main__":
    main()

"""服务体检 —— 一条命令检查 AI 集成栈的全部依赖是否就绪。"""

from __future__ import annotations

import json
import urllib.request


def probe(name: str, url: str, expect: str = None) -> tuple[bool, str]:
    try:
        with urllib.request.urlopen(url, timeout=3) as resp:
            body = resp.read(200).decode("utf-8", "ignore")
            ok = expect is None or expect in body
            return ok, f"HTTP {resp.status}" + (f"，含 '{expect}'" if expect else "")
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)[:60]


CHECKS = [
    ("Dify（nginx）", "http://localhost/apps", None),
    ("SQL 工具服务", "http://127.0.0.1:5057/health", '"status": "ok"'),
    ("本地 LLM（llama.cpp）", "http://127.0.0.1:8080/health", None),
    ("本地 Embedding（bge-m3）", "http://127.0.0.1:8081/health", None),
]


def main() -> None:
    print(f"{'服务':<24} 状态")
    print("-" * 60)
    all_ok = True
    for name, url, expect in CHECKS:
        ok, detail = probe(name, url, expect)
        all_ok &= ok
        print(f"{name:<24} {'✅' if ok else '❌ 未启动'}   {detail}")

    print("\n启动顺序提示：")
    print("  1. Docker Desktop → Dify 容器组（docker compose up -d）")
    print("  2. llm service/qwen2.5_0.5b.bat（:8080，Agent 建议换 7B）")
    print("  3. emd_service/bge-m3-Q8_0.bat（:8081）")
    print("  4. ai_assistant/sql_tool_service.py（:5057）")
    if not all_ok:
        raise SystemExit(1)
    print("\n全部就绪 ✅ 可按 dify/*.md 指南配置 NL2SQL / Agent / 知识库。")


if __name__ == "__main__":
    main()

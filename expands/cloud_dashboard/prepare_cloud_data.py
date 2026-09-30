"""生成云部署版 Dashboard 的预聚合数据（cloud_dashboard/data/cloud_data.json）。

为什么需要预聚合：
Streamlit Community Cloud 无法访问本地的 222MB 清洗 CSV / 3.5GB 原始数据，
云端 app 只能加载仓库内的小文件。本脚本把清洗后抽样数据聚合为
< 200KB 的 JSON（不含任何 user_id / item_id 明细，仅聚合指标，可安全公开）。

聚合口径与 python/src/analysis.py 完全一致（直接复用其函数）。

用法（本地）：
    python prepare_cloud_data.py
"""

from __future__ import annotations

import json
import sys
from datetime import date, datetime
from pathlib import Path

CLOUD_DIR = Path(__file__).resolve().parent
PYTHON_DIR = CLOUD_DIR.parents[1] / "python"  # 仓库根（本模块在 expands/ 下）
sys.path.insert(0, str(PYTHON_DIR / "src"))

from analysis import (  # noqa: E402
    load_data,
    repurchase_analysis,
    summarize_behavior_metrics,
    top_categories_by_purchase,
    user_item_sequential_funnel,
    user_segmentation,
)

OUTPUT = CLOUD_DIR / "data" / "cloud_data.json"


def _default(obj):
    """JSON 序列化 numpy / date 类型。"""
    if isinstance(obj, (date, datetime)):
        return obj.strftime("%Y-%m-%d")
    if hasattr(obj, "item"):
        return obj.item()
    raise TypeError(f"unserializable: {type(obj)}")


def main() -> None:
    df = load_data(PYTHON_DIR / "data" / "cleaned_stratified_data.csv")
    df = df[(df["timestamp"] >= "2017-11-25") & (df["timestamp"] < "2017-12-04")]
    print("聚合中……")

    # 日期 × 行为 计数（支撑日期/行为筛选）
    daily_behavior = (
        df.groupby(["date", "behavior_type"]).size().reset_index(name="count")
    )

    # 日期级用户指标（DAU / 购买用户数）
    daily_users = df.groupby("date")["user_id"].nunique().reset_index(name="dau")
    buy_users = (
        df[df["behavior_type"] == "buy"].groupby("date")["user_id"].nunique()
        .reset_index(name="purchase_users")
    )
    daily_users = daily_users.merge(buy_users, on="date", how="left").fillna(0)

    # 日期 × 小时 × 行为（支撑小时热力图的全部筛选组合）
    hourly_behavior = (
        df.groupby(["date", "hour", "behavior_type"]).size().reset_index(name="count")
    )

    # 静态视图（全窗口口径）
    funnel = user_item_sequential_funnel(df)
    seg = user_segmentation(df)
    segmentation = seg.assign(
        purchase_segment=seg["purchase_segment"].astype(str)
    ).to_dict("records")
    top_categories = top_categories_by_purchase(df, top_n=10)
    repurchase = repurchase_analysis(df)
    summary = summarize_behavior_metrics(df)

    payload = {
        "meta": {
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "window": "2017-11-25 ~ 2017-12-03",
            "sampling": "用户级分层等比例抽样 5%（全量 1 亿行的 5% 用户，保留其全部行为）",
            "validation": "DuckDB 全量交叉验证，核心指标差异 < 0.1%",
            "privacy": "仅含聚合指标，不含 user_id / item_id 明细",
            "static_views": "转化漏斗、用户分层、类目 TOP10 为全窗口口径，不随筛选变化",
        },
        "summary": {**summary, **repurchase},
        "daily_behavior": daily_behavior.to_dict("records"),
        "daily_users": daily_users.to_dict("records"),
        "hourly_behavior": hourly_behavior.to_dict("records"),
        "funnel": funnel,
        "segmentation": segmentation,
        "top_categories": top_categories.to_dict("records"),
    }

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, default=_default),
                      encoding="utf-8")
    size_kb = OUTPUT.stat().st_size / 1024
    print(f"✅ 已生成 {OUTPUT}（{size_kb:.0f} KB）")


if __name__ == "__main__":
    main()

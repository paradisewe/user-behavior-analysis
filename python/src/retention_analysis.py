"""留存分析（9 天窗口缩水版：只做次日留存 + 按活跃分层对比）。

对应 plan.md 深化方向 #4。9 天窗口下：
- 7 日留存只对第 1~2 天活跃的用户有效，样本太薄，不做
- 30 日留存做不了
因此只做次日留存（any-action 口径），并按用户活跃度分层对比。

活跃分层（按窗口内活跃天数）：
    1 天 / 2~3 天 / 4~5 天 / 6~9 天

输入：cleaned_stratified_data.csv
输出：reports/retention_summary.csv + reports/figures/retention_*.png
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from analysis import load_data
from config import FIG_DIR, REPORTS_DIR

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei"]
plt.rcParams["axes.unicode_minus"] = False

LAYER_ORDER = ["1天", "2~3天", "4~5天", "6~9天"]


def activity_layer(days: int) -> str:
    if days <= 1:
        return "1天"
    if days <= 3:
        return "2~3天"
    if days <= 5:
        return "4~5天"
    return "6~9天"


# ---------- 1. 分日期的次日留存 ----------
def daily_next_day_retention(df: pd.DataFrame) -> pd.DataFrame:
    """每个日期的活跃用户中，次日仍活跃的比例（末日无次日，不计）。"""
    dates = sorted(df["date"].unique())
    user_sets = {d: set(df[df["date"] == d]["user_id"]) for d in dates}

    rows = []
    for i, d in enumerate(dates[:-1]):
        next_d = dates[i + 1]
        cohort = user_sets[d]
        retained = cohort & user_sets[next_d]
        rows.append({
            "date": d,
            "next_date": next_d,
            "cohort_users": len(cohort),
            "retained_users": len(retained),
            "next_day_retention": round(len(retained) / len(cohort), 4),
        })
    return pd.DataFrame(rows)


# ---------- 2. 按活跃分层的次日留存 ----------
def retention_by_activity_layer(df: pd.DataFrame) -> pd.DataFrame:
    """分层口径：对每个用户，其每个"有次日"的活跃日，
    若次日仍活跃计 1 次留存；层内按 人-日对 汇总。"""
    user_days = df.groupby("user_id")["date"].apply(lambda s: set(s.unique()))
    layer_of = df.groupby("user_id")["date"].nunique().apply(activity_layer).rename("layer")

    dates = sorted(df["date"].unique())
    date_index = {d: i for i, d in enumerate(dates)}

    rows = []
    for user_id, days in user_days.items():
        eligible = retained = 0
        for d in days:
            i = date_index[d]
            if i + 1 >= len(dates):
                continue  # 窗口最后一天无次日
            eligible += 1
            if dates[i + 1] in days:
                retained += 1
        rows.append({"user_id": user_id, "layer": layer_of[user_id],
                     "eligible_days": eligible, "retained_days": retained})

    detail = pd.DataFrame(rows)
    summary = detail.groupby("layer").agg(
        users=("user_id", "nunique"),
        eligible_pairs=("eligible_days", "sum"),
        retained_pairs=("retained_days", "sum"),
    ).reindex(LAYER_ORDER).reset_index()
    summary["next_day_retention"] = (
        summary["retained_pairs"] / summary["eligible_pairs"]
    ).round(4)
    summary["avg_eligible_days"] = (summary["eligible_pairs"] / summary["users"]).round(2)
    return summary[["layer", "users", "avg_eligible_days",
                    "eligible_pairs", "retained_pairs", "next_day_retention"]]


# ---------- 可视化 ----------
def plot_retention(daily: pd.DataFrame, layered: pd.DataFrame, fig_dir: Path):
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.5))

    axes[0].plot(daily["date"].astype(str).str[5:], daily["next_day_retention"] * 100,
                 marker="o", color="#2b7bba", linewidth=2)
    for x, y in zip(daily["date"].astype(str).str[5:], daily["next_day_retention"] * 100):
        axes[0].annotate(f"{y:.1f}%", (x, y), textcoords="offset points",
                         xytext=(0, 8), ha="center", fontsize=9)
    axes[0].set_title("分日期的次日留存率（末日不计）")
    axes[0].set_ylabel("次日留存率（%）")
    axes[0].set_ylim(0, 100)
    axes[0].grid(axis="y", alpha=0.3)

    bars = axes[1].bar(layered["layer"], layered["next_day_retention"] * 100,
                       color=["#c7e9c0", "#74c476", "#31a354", "#006d2c"])
    for bar, users in zip(bars, layered["users"]):
        axes[1].text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 1,
                     f"n={users:,}", ha="center", fontsize=9)
    axes[1].set_title("按活跃分层的次日留存率")
    axes[1].set_ylabel("次日留存率（%）")
    axes[1].set_xlabel("窗口内活跃天数")
    axes[1].set_ylim(0, 100)

    fig.suptitle("次日留存分析（9 天窗口，活跃分层差异显著）", y=1.02)
    fig.tight_layout()
    fig.savefig(fig_dir / "retention_overview.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


# ---------- 主入口 ----------
def main() -> None:
    parser = argparse.ArgumentParser(description="次日留存分析（9天窗口缩水版）")
    parser.add_argument("--input", type=Path, default=None, help="Cleaned CSV path.")
    args = parser.parse_args()

    df = load_data(args.input) if args.input else load_data()

    print("\n===== 1. 分日期的次日留存 =====")
    daily = daily_next_day_retention(df)
    print(daily.to_string(index=False))

    print("\n===== 2. 按活跃分层的次日留存 =====")
    layered = retention_by_activity_layer(df)
    print(layered.to_string(index=False))

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    out_path = REPORTS_DIR / "retention_summary.csv"
    layered.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"\n✅ 结果已保存：{out_path}")

    plot_retention(daily, layered, FIG_DIR)
    print(f"✅ 图表已保存：{FIG_DIR / 'retention_overview.png'}")


if __name__ == "__main__":
    main()

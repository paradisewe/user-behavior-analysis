"""RFM 用户分层（无金额维度，做 RF 两维打分）。

对应 plan.md 深化方向 #3。数据窗口仅 9 天（2017-11-25 ~ 12-03），
R 粒度粗、F 上限低，因此分箱按 9 天窗口设计，不照搬 30 天经典阈值。

口径说明：
- R（Recency）：最近一次购买距观测窗口最后一天的天数（仅购买用户）
- F（Frequency）：窗口内购买次数（去重到天？否——按购买行为次数计）
- 非购买用户（F=0）不参与 RF 打分，单列一类报告

8 类映射规则（R_score、F_score 各 1~4 分，按购买用户四分位）：
    R>=3 & F>=3  重要价值客户      R<3 & F>=3  重要保持客户
    R>=3 & F=2   重要发展客户      R<3 & F=2   重要挽留客户
    R>=3 & F=1   一般价值客户      R<3 & F=1   一般挽留客户
    （F_score=4 与 >=3 合并为"高频"层，8 类 = R 两档 × F 三档 + 细分）

输入：cleaned_stratified_data.csv
输出：reports/rfm_segments.csv + reports/figures/rfm_*.png
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from analysis import load_data
from config import FIG_DIR, REPORTS_DIR

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei"]
plt.rcParams["axes.unicode_minus"] = False

SEGMENT_ORDER = [
    "重要价值客户", "重要发展客户", "重要保持客户", "重要挽留客户",
    "一般价值客户", "一般挽留客户", "未购买用户",
]


# ---------- RF 原始指标 ----------
def compute_rf(df: pd.DataFrame) -> pd.DataFrame:
    """对每个用户计算 R（距末日的天数）与 F（购买次数）。"""
    last_date = df["date"].max()
    buy_df = df[df["behavior_type"] == "buy"]

    rf = buy_df.groupby("user_id").agg(
        last_buy_date=("date", "max"),
        frequency=("behavior_type", "size"),
    ).reset_index()
    rf["recency_days"] = rf["last_buy_date"].apply(lambda d: (last_date - d).days)

    # 全量用户打标，未购买用户 F=0
    all_users = pd.DataFrame({"user_id": df["user_id"].unique()})
    rf = all_users.merge(rf[["user_id", "recency_days", "frequency"]],
                         on="user_id", how="left")
    rf["is_buyer"] = rf["frequency"].notna()
    return rf


# ---------- 打分 ----------
def score_rf(rf: pd.DataFrame) -> pd.DataFrame:
    buyers = rf[rf["is_buyer"]].copy()

    # R 越小越好：天数越小分越高；F 越大分越高
    # 9 天窗口下 R 天粒度粗、四分位边界大量重复（大量用户末日购买），
    # 按窗口手工分箱：0 天=4 分，1 天=3 分，2~3 天=2 分，4~8 天=1 分
    buyers["r_score"] = pd.cut(
        buyers["recency_days"], bins=[-0.1, 0, 1, 3, 8], labels=[4, 3, 2, 1]
    ).astype(int)
    buyers["f_score"] = pd.qcut(buyers["frequency"].rank(method="first"), 4, labels=[1, 2, 3, 4]).astype(int)
    rf = rf.merge(buyers[["user_id", "r_score", "f_score"]], on="user_id", how="left")

    def segment(row):
        if not row["is_buyer"]:
            return "未购买用户"
        r, f = row["r_score"], row["f_score"]
        if r >= 3 and f >= 3:
            return "重要价值客户"
        if r >= 3 and f == 2:
            return "重要发展客户"
        if r < 3 and f >= 3:
            return "重要保持客户"
        if r < 3 and f == 2:
            return "重要挽留客户"
        if r >= 3:
            return "一般价值客户"
        return "一般挽留客户"

    rf["segment"] = rf.apply(segment, axis=1)
    return rf


# ---------- 汇总 ----------
def segment_summary(rf: pd.DataFrame) -> pd.DataFrame:
    summary = rf.groupby("segment").agg(
        users=("user_id", "nunique"),
        avg_frequency=("frequency", "mean"),
        avg_recency_days=("recency_days", "mean"),
    ).reset_index()
    total = summary["users"].sum()
    summary["user_share"] = (summary["users"] / total).round(4)
    summary["avg_frequency"] = summary["avg_frequency"].round(2)
    summary["avg_recency_days"] = summary["avg_recency_days"].round(2)
    return summary.set_index("segment").reindex(SEGMENT_ORDER).reset_index()


# ---------- 可视化 ----------
def plot_segments(summary: pd.DataFrame, fig_dir: Path):
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    plot_df = summary[summary["segment"] != "未购买用户"]
    colors = ["#d62728", "#ff7f0e", "#2ca02c", "#8c564b", "#1f77b4", "#7f7f7f"]
    bars = axes[0].bar(plot_df["segment"], plot_df["users"], color=colors)
    for bar, share in zip(bars, plot_df["user_share"]):
        axes[0].text(bar.get_x() + bar.get_width() / 2, bar.get_height(),
                     f"{share:.1%}", ha="center", va="bottom", fontsize=9)
    axes[0].set_title("购买用户 RF 分层分布（% 为占全体用户比例）")
    axes[0].tick_params(axis="x", rotation=30)

    buyers = summary[summary["segment"] != "未购买用户"]
    axes[1].bar(buyers["segment"], buyers["avg_frequency"], color=colors)
    axes[1].set_title("各层级平均购买次数")
    axes[1].tick_params(axis="x", rotation=30)

    fig.suptitle("RF 用户分层（窗口仅 9 天，F 上限低属预期）", y=1.02)
    fig.tight_layout()
    fig.savefig(fig_dir / "rfm_segments.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


def plot_rf_matrix(rf: pd.DataFrame, fig_dir: Path):
    buyers = rf[rf["is_buyer"]]
    matrix = buyers.pivot_table(
        index="r_score", columns="f_score", values="user_id", aggfunc="count"
    ).reindex(index=[4, 3, 2, 1])

    fig, ax = plt.subplots(figsize=(7, 5.5))
    im = ax.imshow(matrix.values, cmap="YlOrRd", aspect="auto")
    ax.set_xticks(range(4), labels=[f"F={c}" for c in matrix.columns])
    ax.set_yticks(range(4), labels=[f"R={r}" for r in matrix.index])
    for i in range(matrix.shape[0]):
        for j in range(matrix.shape[1]):
            v = matrix.values[i, j]
            ax.text(j, i, f"{v:,}", ha="center", va="center",
                    color="white" if v > matrix.values.max() * 0.6 else "black")
    ax.set_title("购买用户 R×F 得分矩阵（人数）")
    ax.set_xlabel("F_score（购买频次，1~4）")
    ax.set_ylabel("R_score（最近购买，1~4，4=最近）")
    fig.colorbar(im, ax=ax, shrink=0.8)
    fig.tight_layout()
    fig.savefig(fig_dir / "rfm_matrix.png", dpi=150)
    plt.close(fig)


# ---------- 主入口 ----------
def main() -> None:
    parser = argparse.ArgumentParser(description="RFM 用户分层（RF 两维）")
    parser.add_argument("--input", type=Path, default=None, help="Cleaned CSV path.")
    args = parser.parse_args()

    df = load_data(args.input) if args.input else load_data()

    rf = compute_rf(df)
    rf = score_rf(rf)

    buyer_count = int(rf["is_buyer"].sum())
    print(f"\n购买用户：{buyer_count:,}，未购买用户：{len(rf) - buyer_count:,}")
    print(f"购买用户 F 分布（9 天窗口）：\n{rf[rf['is_buyer']]['frequency'].describe().round(2)}")

    summary = segment_summary(rf)
    print("\n===== RF 分层结果 =====")
    print(summary.to_string(index=False))

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    out_path = REPORTS_DIR / "rfm_segments.csv"
    summary.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"\n✅ 结果已保存：{out_path}")

    plot_segments(summary, FIG_DIR)
    plot_rf_matrix(rf, FIG_DIR)
    print(f"✅ 图表已保存：{FIG_DIR / 'rfm_segments.png'}")
    print(f"✅ 图表已保存：{FIG_DIR / 'rfm_matrix.png'}")


if __name__ == "__main__":
    main()

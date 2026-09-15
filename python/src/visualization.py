"""淘宝用户行为分析 - 可视化模块

生成 8 张核心图表，保存到 reports/figures/ 目录。
所有汇总类图表使用加权数据。
"""

from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd
import seaborn as sns

from analysis import (
    load_data,
    behavior_type_distribution,
    user_level_funnel,
    user_item_sequential_funnel,
    daily_active_users,
    daily_purchase_trend,
    hourly_activity,
    top_categories_by_purchase,
    user_segmentation,
)


# ============================================================
# 全局配置
# ============================================================
# 中文字体（Windows 优先微软雅黑，回退黑体）
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Arial Unicode MS"]
plt.rcParams["axes.unicode_minus"] = False   # 负号正常显示
plt.rcParams["figure.dpi"] = 120              # 默认 DPI

sns.set_theme(style="whitegrid", font="Microsoft YaHei")

# 项目路径
PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIG_DIR = PROJECT_ROOT / "reports" / "figures"
FIG_DIR.mkdir(parents=True, exist_ok=True)


# 配色方案（统一的品牌色）
COLORS = {
    "pv": "#4C9BE8",     # 蓝 - 浏览
    "fav": "#F5A623",    # 橙 - 收藏
    "cart": "#7B68EE",   # 紫 - 加购
    "buy": "#E94E4E",    # 红 - 购买
}


def _format_thousands(x, pos):
    """把数字格式化成 12.3万 或 1.2亿"""
    if x >= 1e8:
        return f"{x/1e8:.1f}亿"
    elif x >= 1e4:
        return f"{x/1e4:.0f}万"
    return f"{x:.0f}"


# ============================================================
# 图 1：行为类型分布（饼图 + 柱状图）
# ============================================================
def plot_behavior_distribution(df: pd.DataFrame):
    """行为类型分布：饼图展示占比 + 柱状图展示绝对量。"""
    dist = behavior_type_distribution(df)
    dist = dist.sort_values("behavior_type")

    fig, axes = plt.subplots(1, 2, figsize=(13, 5))

    # 左图：饼图
    colors = [COLORS.get(t, "#999") for t in dist["behavior_type"]]
    labels = [f"{t}\n{s:.2%}" for t, s in zip(dist["behavior_type"], dist["behavior_share_weighted"])]
    axes[0].pie(
    dist["behavior_count_weighted"],
    colors=colors,
    startangle=90,
    wedgeprops={"edgecolor": "white", "linewidth": 2},
    autopct=lambda p: f"{p:.1f}%" if p > 5 else "",   # 小于 5% 不标
    )
    axes[0].legend(
    labels=[f"{t} ({s:.2%})" for t, s in zip(dist["behavior_type"], dist["behavior_share_weighted"])],
    loc="center left", bbox_to_anchor=(1.0, 0.5), fontsize=11,
    )
    axes[0].set_title("行为类型占比（加权）", fontsize=14, fontweight="bold")

    # 右图：柱状图
    bars = axes[1].bar(
        dist["behavior_type"],
        dist["behavior_count_weighted"],
        color=colors,
        edgecolor="white",
    )
    axes[1].set_title("行为类型绝对量（加权）", fontsize=14, fontweight="bold")
    axes[1].set_xlabel("行为类型", fontsize=12)
    axes[1].set_ylabel("行为次数", fontsize=12)
    axes[1].yaxis.set_major_formatter(mticker.FuncFormatter(_format_thousands))

    # 柱顶标数值
    for bar in bars:
        h = bar.get_height()
        axes[1].text(
            bar.get_x() + bar.get_width() / 2, h,
            _format_thousands(h, 0),
            ha="center", va="bottom", fontsize=11,
        )

    plt.tight_layout()
    plt.savefig(FIG_DIR / "01_behavior_distribution.png", bbox_inches="tight")
    plt.close()
    print("✅ 01_behavior_distribution.png")


# ============================================================
# 图 2：用户-商品级漏斗（核心洞察图）
# ============================================================
def plot_sequential_funnel(df):
    """用户-商品级漏斗：真实转化效率。"""
    metrics = user_item_sequential_funnel(df)

    stages = [
        ("浏览 (pv)", metrics["viewed_pairs"], 1.0),
        ("加购 (cart)", metrics["pv_to_cart_pairs"], metrics["pv_to_cart_pair_rate"]),
        ("购买 (buy)", metrics["pv_to_buy_pairs"], metrics["pv_to_buy_pair_rate"]),
    ]

    fig, ax = plt.subplots(figsize=(10, 6))

    # 用对数比例映射宽度，保证小阶段可见
    values = [v for _, v, _ in stages]
    log_values = np.log10([max(v, 1) for v in values])
    log_max = log_values[0]

    # 宽度 = log比例，再夹到 [0.25, 1.0] 保证可读
    widths = [max(0.25, lv / log_max) for lv in log_values]

    y_positions = np.arange(len(stages))[::-1]
    colors = ["#4C9BE8", "#7B68EE", "#E94E4E"]

    for i, ((label, val, rate), w, y) in enumerate(zip(stages, widths, y_positions)):
        left = (1 - w) / 2
        ax.barh(y, w, left=left, height=0.6, color=colors[i],
                edgecolor="white", linewidth=2)
        # 数字标在条形中央
        ax.text(0.5, y,
                f"{label}\n{val:,} 对\n转化率 {rate:.2%}",
                ha="center", va="center",
                fontsize=13, fontweight="bold", color="white")

    # 右侧标注真实比例
    for i, ((label, val, rate), y) in enumerate(zip(stages, y_positions)):
        ax.text(1.02, y, f"真实比例: {rate:.2%}",
                ha="left", va="center", fontsize=11, color="#333")

    ax.set_xlim(0, 1.3)
    ax.set_ylim(-0.5, len(stages) - 0.5)
    ax.set_yticks([])
    ax.set_xticks([])
    ax.set_title("用户-商品级漏斗：真实转化效率", fontsize=15, fontweight="bold", pad=20)
    ax.text(0.5, -0.75,
            "说明：条形宽度用对数映射，保证小阶段可见；右侧标注真实转化比例",
            ha="center", fontsize=10, color="#666", style="italic")

    plt.tight_layout()
    plt.savefig(FIG_DIR / "02_sequential_funnel.png", bbox_inches="tight")
    plt.close()
    print("✅ 02_sequential_funnel.png")

# ============================================================
# 图 3：用户级漏斗（对比图）
# ============================================================
def plot_user_funnel(df: pd.DataFrame):
    """用户级漏斗：展示用户覆盖面。"""
    funnel = user_level_funnel(df)

    steps = ["浏览", "收藏", "加购", "购买"]
    weights = funnel["weighted_users"].values
    conv = funnel["conversion_from_view"].values

    fig, ax = plt.subplots(figsize=(10, 5))

    bars = ax.bar(
        steps, weights,
        color=["#4C9BE8", "#F5A623", "#7B68EE", "#E94E4E"],
        edgecolor="white", linewidth=2,
    )
    ax.set_title("用户级漏斗：用户覆盖面", fontsize=15, fontweight="bold")
    ax.set_ylabel("加权用户数", fontsize=12)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(_format_thousands))

    for bar, w, c in zip(bars, weights, conv):
        h = bar.get_height()
        ax.text(
            bar.get_x() + bar.get_width() / 2, h,
            f"{_format_thousands(w, 0)}\n({c:.1%})",
            ha="center", va="bottom", fontsize=11,
        )

    # 加注释
    ax.text(
        0.5, -0.22,
        "说明：只要用户曾经有过该行为即计入，反映用户覆盖广度，转化率天然偏高",
        ha="center", transform=ax.transAxes, fontsize=10, color="#666", style="italic",
    )

    plt.tight_layout()
    plt.savefig(FIG_DIR / "03_user_funnel.png", bbox_inches="tight")
    plt.close()
    print("✅ 03_user_funnel.png")


# ============================================================
# 图 4：DAU 趋势
# ============================================================
def plot_dau_trend(df: pd.DataFrame):
    dau = daily_active_users(df)

    fig, ax = plt.subplots(figsize=(11, 5))
    ax.plot(dau["date"], dau["dau_weighted"], marker="o",
            linewidth=2.5, markersize=8, color="#4C9BE8")

    # 填充面积
    ax.fill_between(dau["date"], dau["dau_weighted"], alpha=0.15, color="#4C9BE8")

    ax.set_title("每日活跃用户趋势（加权）", fontsize=15, fontweight="bold")
    ax.set_xlabel("日期", fontsize=12)
    ax.set_ylabel("DAU", fontsize=12)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(_format_thousands))
    ax.tick_params(axis="x", rotation=45)

    # 标最高点
    max_idx = dau["dau_weighted"].idxmax()
    max_date = dau.loc[max_idx, "date"]
    max_val = dau.loc[max_idx, "dau_weighted"]
    ax.annotate(
        f"峰值 {_format_thousands(max_val, 0)}",
        xy=(max_date, max_val),
        xytext=(10, 15), textcoords="offset points",
        fontsize=11, color="#E94E4E",
        arrowprops=dict(arrowstyle="->", color="#E94E4E"),
    )

    plt.tight_layout()
    plt.savefig(FIG_DIR / "04_dau_trend.png", bbox_inches="tight")
    plt.close()
    print("✅ 04_dau_trend.png")


# ============================================================
# 图 5：购买趋势
# ============================================================
def plot_purchase_trend(df: pd.DataFrame):
    trend = daily_purchase_trend(df)

    fig, ax1 = plt.subplots(figsize=(11, 5))

    # 左轴：购买行为数
    color1 = "#E94E4E"
    ax1.plot(trend["date"], trend["purchase_count_weighted"],
             marker="o", linewidth=2.5, markersize=8, color=color1, label="购买行为数")
    ax1.set_xlabel("日期", fontsize=12)
    ax1.set_ylabel("购买行为数", fontsize=12, color=color1)
    ax1.tick_params(axis="y", labelcolor=color1)
    ax1.yaxis.set_major_formatter(mticker.FuncFormatter(_format_thousands))

    # 右轴：购买用户数
    ax2 = ax1.twinx()
    color2 = "#4C9BE8"
    ax2.plot(trend["date"], trend["purchase_users_weighted"],
             marker="s", linewidth=2.5, markersize=8, color=color2,
             linestyle="--", label="购买用户数")
    ax2.set_ylabel("购买用户数", fontsize=12, color=color2)
    ax2.tick_params(axis="y", labelcolor=color2)
    ax2.yaxis.set_major_formatter(mticker.FuncFormatter(_format_thousands))

    ax1.set_title("每日购买趋势（加权）", fontsize=15, fontweight="bold")
    ax1.tick_params(axis="x", rotation=45)

    # 合并图例
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper left", fontsize=11)

    plt.tight_layout()
    plt.savefig(FIG_DIR / "05_purchase_trend.png", bbox_inches="tight")
    plt.close()
    print("✅ 05_purchase_trend.png")


# ============================================================
# 图 6：小时活跃度热力图
# ============================================================
def plot_hourly_heatmap(df: pd.DataFrame):
    hourly = hourly_activity(df)

    pivot = hourly.pivot_table(
        index="behavior_type",
        columns="hour",
        values="behavior_count",
        fill_value=0,
    )
    # 按行为顺序排列
    pivot = pivot.reindex(["pv", "cart", "fav", "buy"])

    # 按行为归一化（每行之和为 1），让不同行为可比较
    normalized = pivot.div(pivot.sum(axis=1), axis=0)

    fig, ax = plt.subplots(figsize=(14, 4))
    sns.heatmap(
        normalized,
        cmap="YlOrRd",
        annot=False,
        cbar_kws={"label": "该行为在各小时的分布比例"},
        linewidths=0.5,
        linecolor="white",
        ax=ax,
    )
    ax.set_title("用户行为的小时分布（按行为归一化）", fontsize=15, fontweight="bold", pad=15)
    ax.set_xlabel("小时（0-23）", fontsize=12)
    ax.set_ylabel("行为类型", fontsize=12)

    plt.tight_layout()
    plt.savefig(FIG_DIR / "06_hourly_heatmap.png", bbox_inches="tight")
    plt.close()
    print("✅ 06_hourly_heatmap.png")


# ============================================================
# 图 7：类目 TOP10 购买排行
# ============================================================
def plot_top_categories(df: pd.DataFrame):
    top = top_categories_by_purchase(df, top_n=10)
    top = top.sort_values("purchase_count_weighted")

    fig, ax = plt.subplots(figsize=(10, 6))
    bars = ax.barh(
        [f"类目 {int(c)}" for c in top["category_id"]],
        top["purchase_count_weighted"],
        color="#E94E4E", edgecolor="white",
    )
    ax.set_title("购买量 TOP10 类目（加权）", fontsize=15, fontweight="bold")
    ax.set_xlabel("购买次数", fontsize=12)
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(_format_thousands))

    for bar in bars:
        w = bar.get_width()
        ax.text(w, bar.get_y() + bar.get_height() / 2,
                f" {_format_thousands(w, 0)}",
                va="center", fontsize=10)

    plt.tight_layout()
    plt.savefig(FIG_DIR / "07_top_categories.png", bbox_inches="tight")
    plt.close()
    print("✅ 07_top_categories.png")


# ============================================================
# 图 8：用户行为深度分层
# ============================================================
def plot_user_segmentation(df: pd.DataFrame):
    seg = user_segmentation(df)

    # 透视：行=行为深度，列=购买分段
    pivot = seg.pivot_table(
        index="behavior_depth",
        columns="purchase_segment",
        values="users",
        fill_value=0,
    )
    # 按行为深度顺序排列
    order_depth = ["browse_only", "favorited", "added_to_cart", "purchased"]
    pivot = pivot.reindex(order_depth).fillna(0)

    # 只保留有购买行为的行的 purchase_segment 有意义
    # 但为了展示完整结构，全部保留

    fig, ax = plt.subplots(figsize=(11, 6))
    pivot.plot(
        kind="barh",
        stacked=True,
        ax=ax,
        colormap="Set2",
        edgecolor="white",
        width=0.7,
    )

    ax.set_title("用户行为深度 × 购买分段（未加权，样本内部结构）",
                 fontsize=15, fontweight="bold")
    ax.set_xlabel("用户数（样本）", fontsize=12)
    ax.set_ylabel("行为深度", fontsize=12)
    ax.legend(title="购买分段", bbox_to_anchor=(1.02, 1), loc="upper left", fontsize=10)

    plt.tight_layout()
    plt.savefig(FIG_DIR / "08_user_segmentation.png", bbox_inches="tight")
    plt.close()
    print("✅ 08_user_segmentation.png")
# ============================================================
# 图 9a：不同行为的时间分布
# ============================================================
def plot_purchase_heatmap_by_day(df: pd.DataFrame):
    """每日 × 小时 购买行为热力图（加权）。"""
    buy_df = df[df["behavior_type"] == "buy"].copy()

    # 确保 date / hour 列存在（load_data 已派生）
    pivot = buy_df.pivot_table(
        index="date",
        columns="hour",
        values="weight",
        aggfunc="sum",
        fill_value=0,
    )

    # 保证 24 列都在（某些小时可能没数据）
    for h in range(24):
        if h not in pivot.columns:
            pivot[h] = 0
    pivot = pivot[sorted(pivot.columns)]

    fig, ax = plt.subplots(figsize=(14, 5))
    sns.heatmap(
        pivot,
        cmap="YlOrRd",
        cbar_kws={"label": "加权购买次数"},
        linewidths=0.5,
        linecolor="white",
        ax=ax,
    )
    ax.set_title("每日购买时段热力图（加权）", fontsize=15, fontweight="bold", pad=15)
    ax.set_xlabel("小时（0-23）", fontsize=12)
    ax.set_ylabel("日期", fontsize=12)

    plt.tight_layout()
    plt.savefig(FIG_DIR / "09a_purchase_heatmap_by_day.png", bbox_inches="tight")
    plt.close()
    print("✅ 09a_purchase_heatmap_by_day.png")
# ============================================================
# 图 9b：不同行为的时间分布
# ============================================================
def plot_purchase_heatmap_by_weekday(df: pd.DataFrame):
    """星期 × 小时 购买行为热力图（加权）。"""
    buy_df = df[df["behavior_type"] == "buy"].copy()
    buy_df["weekday"] = pd.to_datetime(buy_df["date"]).dt.dayofweek  # 0=周一, 6=周日

    pivot = buy_df.pivot_table(
        index="weekday",
        columns="hour",
        values="weight",
        aggfunc="sum",
        fill_value=0,
    )
    for h in range(24):
        if h not in pivot.columns:
            pivot[h] = 0
    pivot = pivot[sorted(pivot.columns)]

    # 星期标签
    weekday_labels = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    pivot.index = [weekday_labels[i] for i in pivot.index]

    fig, ax = plt.subplots(figsize=(14, 4))
    sns.heatmap(
        pivot, cmap="YlOrRd",
        cbar_kws={"label": "加权购买次数"},
        linewidths=0.5, linecolor="white", ax=ax,
    )
    ax.set_title("工作日 vs 周末购买时段热力图（加权）", fontsize=15, fontweight="bold", pad=15)
    ax.set_xlabel("小时（0-23）", fontsize=12)
    ax.set_ylabel("星期", fontsize=12)

    plt.tight_layout()
    plt.savefig(FIG_DIR / "09b_purchase_heatmap_by_weekday.png", bbox_inches="tight")
    plt.close()
    print("✅ 09b_purchase_heatmap_by_weekday.png")
# ============================================================
# 主入口
# ============================================================
def main():
    from config import CLEANED_FILE

    print("=" * 60)
    print("📊 开始生成可视化图表")
    print("=" * 60)
    print(f"输出目录：{FIG_DIR}\n")

    df = load_data(CLEANED_FILE)

    plot_behavior_distribution(df)
    plot_sequential_funnel(df)
    plot_user_funnel(df)
    plot_dau_trend(df)
    plot_purchase_trend(df)
    plot_hourly_heatmap(df)visualization
    plot_top_categories(df)
    plot_user_segmentation(df)
    plot_purchase_heatmap_by_day(df)
    plot_purchase_heatmap_by_weekday(df)

    print("\n" + "=" * 60)
    print(f"✅ 全部完成，保存到：{FIG_DIR}")
    print("=" * 60)


if __name__ == "__main__":
    main()
"""淘宝用户行为分析 - 可视化模块

生成核心图表（漏斗/趋势/热力图 9 张 + 深化分析图表），保存到 reports/figures/ 目录。
"""

from pathlib import Path

import matplotlib
matplotlib.use("Agg")

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
    sampling_confidence_checks,
    dau_peak_analysis,
    compute_rfm,
    score_rfm,
    rfm_segment_summary,
    daily_next_day_retention,
    retention_by_activity_layer,
    classify_user_paths,
    build_baskets,
    mine_association_rules,
)


# ============================================================
# 全局配置
# ============================================================
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Arial Unicode MS"]
plt.rcParams["axes.unicode_minus"] = False
plt.rcParams["figure.dpi"] = 120

sns.set_theme(style="whitegrid", font="Microsoft YaHei")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIG_DIR = PROJECT_ROOT / "reports" / "figures"
FIG_DIR.mkdir(parents=True, exist_ok=True)


COLORS = {
    "pv": "#4C9BE8",
    "fav": "#F5A623",
    "cart": "#7B68EE",
    "buy": "#E94E4E",
}


def _format_thousands(x, pos):
    """把数字格式化成 12.3万 或 1.2亿"""
    if x >= 1e8:
        return f"{x/1e8:.1f}亿"
    elif x >= 1e4:
        return f"{x/1e4:.0f}万"
    return f"{x:.0f}"


# ============================================================
# 图 1：行为类型分布
# ============================================================
def plot_behavior_distribution(df: pd.DataFrame):
    dist = behavior_type_distribution(df)
    dist = dist.sort_values("behavior_type")

    fig, axes = plt.subplots(1, 2, figsize=(13, 5))

    # 左图：饼图
    colors = [COLORS.get(t, "#999") for t in dist["behavior_type"]]
    axes[0].pie(
        dist["behavior_count"],
        colors=colors,
        startangle=90,
        wedgeprops={"edgecolor": "white", "linewidth": 2},
        autopct=lambda p: f"{p:.1f}%" if p > 5 else "",
    )
    axes[0].legend(
        labels=[f"{t} ({s:.2%})" for t, s in zip(dist["behavior_type"], dist["behavior_share"])],
        loc="center left", bbox_to_anchor=(1.0, 0.5), fontsize=11,
    )
    axes[0].set_title("行为类型占比", fontsize=14, fontweight="bold")

    # 右图：柱状图
    bars = axes[1].bar(
        dist["behavior_type"],
        dist["behavior_count"],
        color=colors,
        edgecolor="white",
    )
    axes[1].set_title("行为类型绝对量", fontsize=14, fontweight="bold")
    axes[1].set_xlabel("行为类型", fontsize=12)
    axes[1].set_ylabel("行为次数", fontsize=12)
    axes[1].yaxis.set_major_formatter(mticker.FuncFormatter(_format_thousands))

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
    print("01_behavior_distribution.png")


# ============================================================
# 图 2：用户-商品级漏斗
# ============================================================
def plot_sequential_funnel(df: pd.DataFrame):
    metrics = user_item_sequential_funnel(df)

    stages = [
        ("浏览 (pv)", metrics["viewed_pairs"], 1.0),
        ("加购 (cart)", metrics["pv_to_cart_pairs"], metrics["pv_to_cart_rate"]),
        ("购买 (buy)", metrics["pv_to_buy_pairs"], metrics["pv_to_buy_rate"]),
    ]

    fig, ax = plt.subplots(figsize=(10, 6))

    values = [v for _, v, _ in stages]
    log_values = np.log10([max(v, 1) for v in values])
    log_max = log_values[0]
    widths = [max(0.25, lv / log_max) for lv in log_values]

    y_positions = np.arange(len(stages))[::-1]
    colors = ["#4C9BE8", "#7B68EE", "#E94E4E"]

    for i, ((label, val, rate), w, y) in enumerate(zip(stages, widths, y_positions)):
        left = (1 - w) / 2
        ax.barh(y, w, left=left, height=0.6, color=colors[i],
                edgecolor="white", linewidth=2)
        ax.text(0.5, y,
                f"{label}\n{val:,} 对\n转化率 {rate:.2%}",
                ha="center", va="center",
                fontsize=13, fontweight="bold", color="white")

    for (label, val, rate), y in zip(stages, y_positions):
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
    print("02_sequential_funnel.png")


# ============================================================
# 图 3：用户级漏斗
# ============================================================
def plot_user_funnel(df: pd.DataFrame):
    funnel = user_level_funnel(df)

    steps = ["浏览", "收藏", "加购", "购买"]
    users = funnel["users"].values
    conv = funnel["conversion_from_view"].values

    fig, ax = plt.subplots(figsize=(10, 5))

    bars = ax.bar(
        steps, users,
        color=["#4C9BE8", "#F5A623", "#7B68EE", "#E94E4E"],
        edgecolor="white", linewidth=2,
    )
    ax.set_title("用户级漏斗：用户覆盖面", fontsize=15, fontweight="bold")
    ax.set_ylabel("用户数", fontsize=12)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(_format_thousands))

    for bar, u, c in zip(bars, users, conv):
        h = bar.get_height()
        ax.text(
            bar.get_x() + bar.get_width() / 2, h,
            f"{_format_thousands(u, 0)}\n({c:.1%})",
            ha="center", va="bottom", fontsize=11,
        )

    ax.text(
        0.5, -0.22,
        "说明：只要用户曾经有过该行为即计入，反映用户覆盖广度，转化率天然偏高",
        ha="center", transform=ax.transAxes, fontsize=10, color="#666", style="italic",
    )

    plt.tight_layout()
    plt.savefig(FIG_DIR / "03_user_funnel.png", bbox_inches="tight")
    plt.close()
    print("03_user_funnel.png")


# ============================================================
# 图 4：用户趋势（三子图）
# ============================================================
def plot_user_trend(df: pd.DataFrame):
    dau = daily_active_users(df)
    purchase = daily_purchase_trend(df)
    trend = dau.merge(purchase, on="date", how="left").fillna(0)

    fig, axes = plt.subplots(1, 3, figsize=(16, 4.5), sharex=True)

    # 子图 1：DAU
    axes[0].plot(trend["date"], trend["dau"],
                 marker="o", linewidth=2.5, color="#4C9BE8")
    axes[0].fill_between(trend["date"], trend["dau"], alpha=0.15, color="#4C9BE8")
    axes[0].set_title("DAU（活跃用户）", fontsize=13, fontweight="bold")
    axes[0].set_ylabel("用户数", fontsize=11)
    axes[0].yaxis.set_major_formatter(mticker.FuncFormatter(_format_thousands))
    axes[0].tick_params(axis="x", rotation=45)

    mx = trend["dau"].idxmax()
    axes[0].annotate(f"峰值 {_format_thousands(trend.loc[mx, 'dau'], 0)}",
                     xy=(trend.loc[mx, "date"], trend.loc[mx, "dau"]),
                     xytext=(5, 10), textcoords="offset points",
                     fontsize=10, color="#E94E4E",
                     arrowprops=dict(arrowstyle="->", color="#E94E4E"))

    # 子图 2：购买用户数
    axes[1].plot(trend["date"], trend["purchase_users"],
                 marker="s", linewidth=2.5, color="#7B68EE", linestyle="--")
    axes[1].fill_between(trend["date"], trend["purchase_users"],
                         alpha=0.15, color="#7B68EE")
    axes[1].set_title("购买用户数", fontsize=13, fontweight="bold")
    axes[1].set_ylabel("用户数", fontsize=11)
    axes[1].yaxis.set_major_formatter(mticker.FuncFormatter(_format_thousands))
    axes[1].tick_params(axis="x", rotation=45)

    # 子图 3：购买行为数
    axes[2].plot(trend["date"], trend["purchase_count"],
                 marker="^", linewidth=2.5, color="#E94E4E", linestyle=":")
    axes[2].fill_between(trend["date"], trend["purchase_count"],
                         alpha=0.15, color="#E94E4E")
    axes[2].set_title("购买行为数", fontsize=13, fontweight="bold")
    axes[2].set_ylabel("行为数", fontsize=11)
    axes[2].yaxis.set_major_formatter(mticker.FuncFormatter(_format_thousands))
    axes[2].tick_params(axis="x", rotation=45)

    fig.suptitle("用户趋势：DAU · 购买用户 · 购买行为", fontsize=15, fontweight="bold")
    plt.tight_layout()
    plt.savefig(FIG_DIR / "04_user_trend.png", bbox_inches="tight")
    plt.close()
    print("04_user_trend.png")


# ============================================================
# 图 5：小时活跃度热力图
# ============================================================
def plot_hourly_heatmap(df: pd.DataFrame):
    hourly = hourly_activity(df)

    pivot = hourly.pivot_table(
        index="behavior_type",
        columns="hour",
        values="behavior_count",
        fill_value=0,
    )
    pivot = pivot.reindex(["pv", "cart", "fav", "buy"])

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
    plt.savefig(FIG_DIR / "05_hourly_heatmap.png", bbox_inches="tight")
    plt.close()
    print("05_hourly_heatmap.png")


# ============================================================
# 图 6：类目 TOP10 购买排行
# ============================================================
def plot_top_categories(df: pd.DataFrame):
    top = top_categories_by_purchase(df, top_n=10)
    top = top.sort_values("purchase_count")

    fig, ax = plt.subplots(figsize=(10, 6))
    bars = ax.barh(
        [f"类目 {int(c)}" for c in top["category_id"]],
        top["purchase_count"],
        color="#E94E4E", edgecolor="white",
    )
    ax.set_title("购买量 TOP10 类目", fontsize=15, fontweight="bold")
    ax.set_xlabel("购买次数", fontsize=12)

    ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, p: f"{int(x):,}"))

    for bar in bars:
        w = bar.get_width()
        ax.text(
            w * 0.98, bar.get_y() + bar.get_height() / 2,
            f" {int(w):,}",
            va="center", ha="right", fontsize=10,
            color="white", fontweight="bold",
        )

    plt.tight_layout()
    plt.savefig(FIG_DIR / "06_top_categories.png", bbox_inches="tight")
    plt.close()
    print("06_top_categories.png")


# ============================================================
# 图 7：用户行为深度分层
# ============================================================
def plot_user_segmentation(df: pd.DataFrame):
    seg = user_segmentation(df)

    pivot = seg.pivot_table(
        index="behavior_depth",
        columns="purchase_segment",
        values="users",
        fill_value=0,
        observed=True,
    )
    order_depth = ["browse_only", "favorited", "added_to_cart", "purchased"]
    pivot = pivot.reindex(order_depth).fillna(0)

    fig, ax = plt.subplots(figsize=(11, 6))
    pivot.plot(
        kind="barh",
        stacked=True,
        ax=ax,
        colormap="Set2",
        edgecolor="white",
        width=0.7,
    )

    ax.set_title("用户行为深度 × 购买分段", fontsize=15, fontweight="bold")
    ax.set_xlabel("用户数（样本）", fontsize=12)
    ax.set_ylabel("行为深度", fontsize=12)
    ax.legend(title="购买分段", bbox_to_anchor=(1.02, 1), loc="upper left", fontsize=10)

    plt.tight_layout()
    plt.savefig(FIG_DIR / "07_user_segmentation.png", bbox_inches="tight")
    plt.close()
    print("07_user_segmentation.png")


# ============================================================
# 图 8a：每日 × 小时 购买热力图
# ============================================================
def plot_purchase_heatmap_by_day(df: pd.DataFrame):
    buy_df = df[df["behavior_type"] == "buy"]

    pivot = buy_df.pivot_table(
        index="date",
        columns="hour",
        aggfunc="size",
        fill_value=0,
    )

    for h in range(24):
        if h not in pivot.columns:
            pivot[h] = 0
    pivot = pivot[sorted(pivot.columns)]

    fig, ax = plt.subplots(figsize=(14, 5))
    sns.heatmap(
        pivot,
        cmap="YlOrRd",
        cbar_kws={"label": "购买次数"},
        linewidths=0.5,
        linecolor="white",
        ax=ax,
    )
    ax.set_title("每日购买时段热力图", fontsize=15, fontweight="bold", pad=15)
    ax.set_xlabel("小时（0-23）", fontsize=12)
    ax.set_ylabel("日期", fontsize=12)

    plt.tight_layout()
    plt.savefig(FIG_DIR / "08a_purchase_heatmap_by_day.png", bbox_inches="tight")
    plt.close()
    print("08a_purchase_heatmap_by_day.png")


# ============================================================
# 图 8b：星期 × 小时 购买热力图
# ============================================================
def plot_purchase_heatmap_by_weekday(df: pd.DataFrame):
    buy_df = df[df["behavior_type"] == "buy"].copy()
    buy_df["weekday"] = pd.to_datetime(buy_df["date"]).dt.dayofweek

    pivot = buy_df.pivot_table(
        index="weekday",
        columns="hour",
        aggfunc="size",
        fill_value=0,
    )
    for h in range(24):
        if h not in pivot.columns:
            pivot[h] = 0
    pivot = pivot[sorted(pivot.columns)]

    weekday_labels = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    pivot.index = [weekday_labels[i] for i in pivot.index]

    fig, ax = plt.subplots(figsize=(14, 4))
    sns.heatmap(
        pivot, cmap="YlOrRd",
        cbar_kws={"label": "购买次数"},
        linewidths=0.5, linecolor="white", ax=ax,
    )
    ax.set_title("工作日 vs 周末购买时段热力图", fontsize=15, fontweight="bold", pad=15)
    ax.set_xlabel("小时（0-23）", fontsize=12)
    ax.set_ylabel("星期", fontsize=12)

    plt.tight_layout()
    plt.savefig(FIG_DIR / "08b_purchase_heatmap_by_weekday.png", bbox_inches="tight")
    plt.close()
    print("08b_purchase_heatmap_by_weekday.png")


# ============================================================
# 图 9a：抽样 95% 置信区间 vs SQL 全量值
# ============================================================
def plot_significance_ci(df: pd.DataFrame):
    checks = sampling_confidence_checks(df)

    fig, ax = plt.subplots(figsize=(9, 5))
    for i, row in enumerate(checks):
        y = len(checks) - 1 - i
        ax.errorbar(
            row["sample_rate"] * 100, y,
            xerr=[[(row["sample_rate"] - row["ci95_low"]) * 100],
                  [(row["ci95_high"] - row["sample_rate"]) * 100]],
            fmt="o", capsize=5, color="#4C9BE8", markersize=8, linewidth=2,
            label="抽样均值 ± 95% CI" if i == 0 else None,
        )
        ax.plot(row["full_data_rate"] * 100, y, "d", color="#E94E4E",
                markersize=9, label="SQL 全量值" if i == 0 else None)
    ax.set_yticks(range(len(checks)))
    ax.set_yticklabels([r["metric"] for r in reversed(checks)])
    ax.set_xlabel("比率（%）", fontsize=12)
    ax.set_title("核心指标：抽样 95% 置信区间 vs SQL 全量值（红钻均落在区间内）",
                 fontsize=14, fontweight="bold")
    ax.legend(loc="lower right")
    ax.grid(axis="x", alpha=0.3)

    plt.tight_layout()
    plt.savefig(FIG_DIR / "significance_ci.png", bbox_inches="tight")
    plt.close()
    print("significance_ci.png")


# ============================================================
# 图 9b：DAU 工作日 vs 周末
# ============================================================
def plot_dau_weekday(df: pd.DataFrame):
    daily = pd.DataFrame(dau_peak_analysis(df)["daily_detail"])
    daily["date"] = pd.to_datetime(daily["date"])

    fig, axes = plt.subplots(1, 2, figsize=(13, 4.5))

    colors = ["#E94E4E" if w else "#4C9BE8" for w in daily["is_weekend"]]
    axes[0].bar(daily["date"].dt.strftime("%m-%d"), daily["dau"], color=colors)
    axes[0].set_title("每日 DAU（红=周末）", fontsize=13, fontweight="bold")
    axes[0].tick_params(axis="x", rotation=45)
    axes[0].yaxis.set_major_formatter(mticker.FuncFormatter(_format_thousands))

    axes[1].bar(daily["date"].dt.strftime("%m-%d"), daily["buy_users"], color=colors)
    axes[1].set_title("每日购买用户数（红=周末）", fontsize=13, fontweight="bold")
    axes[1].tick_params(axis="x", rotation=45)
    axes[1].yaxis.set_major_formatter(mticker.FuncFormatter(_format_thousands))

    fig.suptitle("工作日 vs 周末对比：DAU 与购买用户数", fontsize=15,
                 fontweight="bold", y=1.02)
    plt.tight_layout()
    plt.savefig(FIG_DIR / "dau_weekday_weekend.png", bbox_inches="tight")
    plt.close()
    print("dau_weekday_weekend.png")


# ============================================================
# 图 10a/10b：RFM 用户分层
# ============================================================
def plot_rfm(df: pd.DataFrame):
    rf = score_rfm(compute_rfm(df))
    summary = rfm_segment_summary(rf)
    plot_df = summary[summary["segment"] != "未购买用户"]

    colors = ["#E94E4E", "#F5A623", "#2CA02C", "#8C564B", "#4C9BE8", "#7F7F7F"]

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    bars = axes[0].bar(plot_df["segment"], plot_df["users"], color=colors)
    for bar, share in zip(bars, plot_df["user_share"]):
        axes[0].text(bar.get_x() + bar.get_width() / 2, bar.get_height(),
                     f"{share:.1%}", ha="center", va="bottom", fontsize=9)
    axes[0].set_title("购买用户 RF 分层分布（% 为占全体用户比例）",
                      fontsize=13, fontweight="bold")
    axes[0].tick_params(axis="x", rotation=30)
    axes[0].yaxis.set_major_formatter(mticker.FuncFormatter(_format_thousands))

    axes[1].bar(plot_df["segment"], plot_df["avg_frequency"], color=colors)
    axes[1].set_title("各层级平均购买次数", fontsize=13, fontweight="bold")
    axes[1].tick_params(axis="x", rotation=30)

    fig.suptitle("RF 用户分层（窗口仅 9 天，F 上限低属预期）", fontsize=15,
                 fontweight="bold", y=1.02)
    plt.tight_layout()
    plt.savefig(FIG_DIR / "rfm_segments.png", bbox_inches="tight")
    plt.close()
    print("rfm_segments.png")

    # R×F 得分矩阵
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
    ax.set_title("购买用户 R×F 得分矩阵（人数）", fontsize=14, fontweight="bold")
    ax.set_xlabel("F_score（购买频次，1~4）", fontsize=12)
    ax.set_ylabel("R_score（最近购买，1~4，4=最近）", fontsize=12)
    fig.colorbar(im, ax=ax, shrink=0.8)

    plt.tight_layout()
    plt.savefig(FIG_DIR / "rfm_matrix.png", bbox_inches="tight")
    plt.close()
    print("rfm_matrix.png")


# ============================================================
# 图 11：次日留存
# ============================================================
def plot_retention(df: pd.DataFrame):
    daily = daily_next_day_retention(df)
    layered = retention_by_activity_layer(df)

    fig, axes = plt.subplots(1, 2, figsize=(13, 4.5))

    axes[0].plot(daily["date"].astype(str).str[5:],
                 daily["next_day_retention"] * 100,
                 marker="o", color="#4C9BE8", linewidth=2)
    for x, y in zip(daily["date"].astype(str).str[5:],
                    daily["next_day_retention"] * 100):
        axes[0].annotate(f"{y:.1f}%", (x, y), textcoords="offset points",
                         xytext=(0, 8), ha="center", fontsize=9)
    axes[0].set_title("分日期的次日留存率（末日不计）", fontsize=13, fontweight="bold")
    axes[0].set_ylabel("次日留存率（%）", fontsize=12)
    axes[0].set_ylim(0, 100)
    axes[0].grid(axis="y", alpha=0.3)

    bars = axes[1].bar(layered["layer"], layered["next_day_retention"] * 100,
                       color=["#c7e9c0", "#74c476", "#31a354", "#006d2c"])
    for bar, users in zip(bars, layered["users"]):
        axes[1].text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 1,
                     f"n={users:,}", ha="center", fontsize=9)
    axes[1].set_title("按活跃分层的次日留存率", fontsize=13, fontweight="bold")
    axes[1].set_ylabel("次日留存率（%）", fontsize=12)
    axes[1].set_xlabel("窗口内活跃天数", fontsize=12)
    axes[1].set_ylim(0, 100)

    fig.suptitle("次日留存分析（9 天窗口，活跃分层差异显著）", fontsize=15,
                 fontweight="bold", y=1.02)
    plt.tight_layout()
    plt.savefig(FIG_DIR / "retention_overview.png", bbox_inches="tight")
    plt.close()
    print("retention_overview.png")


# ============================================================
# 图 12：用户路径桑基图（plotly 交互式 HTML）
# ============================================================
def plot_path_sankey(df: pd.DataFrame):
    import plotly.graph_objects as go

    pairs = classify_user_paths(df)
    n = len(pairs)
    stage2 = pairs.groupby("path").size()
    stage2_to_outcome = pairs.groupby(["path", "outcome"]).size()

    labels = ["浏览 (pv)", *stage2.index.tolist(), "购买", "未购买"]
    node_index = {name: i for i, name in enumerate(labels)}
    colors = ["#4C9BE8", "#E94E4E", "#7B68EE", "#F5A623", "#2CA02C", "#7F7F7F"]

    link_color = {
        "直接购买": "rgba(0, 204, 150, 0.4)",
        "先加购": "rgba(239, 85, 59, 0.35)",
        "先收藏": "rgba(171, 99, 250, 0.35)",
        "仅浏览": "rgba(127, 127, 127, 0.3)",
    }

    sources, targets, values, clist = [], [], [], []
    for path_name, count in stage2.items():
        sources.append(node_index["浏览 (pv)"])
        targets.append(node_index[path_name])
        values.append(int(count))
        clist.append(link_color.get(path_name, "rgba(200,200,200,0.3)"))

    for (path_name, outcome), count in stage2_to_outcome.items():
        sources.append(node_index[path_name])
        targets.append(node_index[outcome])
        values.append(int(count))
        clist.append(link_color.get(path_name, "rgba(200,200,200,0.3)"))

    fig = go.Figure(go.Sankey(
        node=dict(
            pad=18, thickness=22,
            label=[f"{name}<br>({v:,})" for name, v in zip(
                labels,
                [n, *stage2.values,
                 int((pairs["outcome"] == "购买").sum()),
                 int((pairs["outcome"] == "未购买").sum())],
            )],
            color=colors[: len(labels)],
        ),
        link=dict(source=sources, target=targets, value=values, color=clist),
    ))
    fig.update_layout(
        title=f"用户-商品级路径桑基图（n={n:,} 个浏览过的商品对）",
        font=dict(size=13),
    )
    fig.write_html(str(FIG_DIR / "path_sankey.html"))
    print("path_sankey.html")


# ============================================================
# 图 13：类目关联规则
# ============================================================
def plot_association(df: pd.DataFrame):
    baskets = build_baskets(df)
    rules = mine_association_rules(baskets, min_support=0.0005,
                                   min_confidence=0.10, min_lift=1.0, top_n=100)

    fig, ax = plt.subplots(figsize=(9, 6))
    sc = ax.scatter(rules["support"] * 100, rules["confidence"] * 100,
                    s=np.clip(rules["lift"], 1, None) * 12,
                    c=rules["lift"], cmap="viridis", alpha=0.7,
                    edgecolors="k", linewidths=0.3)
    fig.colorbar(sc, ax=ax, label="提升度 lift")
    ax.set_xlabel("支持度（%）", fontsize=12)
    ax.set_ylabel("置信度（%）", fontsize=12)
    ax.set_title("类目级关联规则：支持度 × 置信度（气泡大小=提升度）",
                 fontsize=14, fontweight="bold")
    ax.grid(alpha=0.3)

    plt.tight_layout()
    plt.savefig(FIG_DIR / "association_scatter.png", bbox_inches="tight")
    plt.close()
    print("association_scatter.png")

    top = rules.head(15).iloc[::-1]
    labels = [f"{int(r.antecedent_category)} → {int(r.consequent_category)}"
              for r in top.itertuples()]
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.barh(labels, top["lift"], color="#4C9BE8")
    for i, (lift, conf) in enumerate(zip(top["lift"], top["confidence"])):
        ax.text(lift, i, f"  lift={lift:.1f}, conf={conf:.1%}",
                va="center", fontsize=8)
    ax.set_xlabel("提升度 lift", fontsize=12)
    ax.set_title("Top 15 类目关联规则（按提升度）", fontsize=14, fontweight="bold")

    plt.tight_layout()
    plt.savefig(FIG_DIR / "association_top_rules.png", bbox_inches="tight")
    plt.close()
    print("association_top_rules.png")


# ============================================================
# 主入口
# ============================================================
def main():
    from config import CLEANED_FILE

    print(f"输出目录：{FIG_DIR}")

    df = load_data(CLEANED_FILE)

    plot_behavior_distribution(df)
    plot_sequential_funnel(df)
    plot_user_funnel(df)
    plot_user_trend(df)
    plot_hourly_heatmap(df)
    plot_top_categories(df)
    plot_user_segmentation(df)
    plot_purchase_heatmap_by_day(df)
    plot_purchase_heatmap_by_weekday(df)

    # 深化分析图表
    plot_significance_ci(df)
    plot_dau_weekday(df)
    plot_rfm(df)
    plot_retention(df)
    plot_path_sankey(df)
    plot_association(df)

    print(f"全部完成，保存到：{FIG_DIR}")


if __name__ == "__main__":
    main()
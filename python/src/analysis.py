"""Core Pandas analysis for Taobao user behavior and conversion funnels.

核心分析（漏斗、复购、分层等）+ 深化分析（显著性检验、RFM、次日留存、
用户路径、类目关联规则）。

输入：cleaned_stratified_data.csv
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

from config import CLEANED_FILE, REPORTS_DIR


DEFAULT_INPUT = CLEANED_FILE


# ---------- 加载数据 ----------
def load_data(input_path: Path = DEFAULT_INPUT) -> pd.DataFrame:
    df = pd.read_csv(input_path, parse_dates=["timestamp"])
    # 时间戳在 data_cleaning 阶段已转为北京时间，这里直接使用

    # 派生分析所需的三列
    df["behavior_time"] = df["timestamp"]
    df["date"] = df["timestamp"].dt.date
    df["hour"] = df["timestamp"].dt.hour

    print(f"加载数据：{input_path}")
    print(f"行数：{len(df):,}")
    print(f"用户数：{df['user_id'].nunique():,}")
    print(f"时间范围：{df['timestamp'].min()} ~ {df['timestamp'].max()}")
    return df


# ---------- 1. 核心指标汇总 ----------
def summarize_behavior_metrics(df: pd.DataFrame) -> dict:
    behavior_counts = df["behavior_type"].value_counts()
    total = len(df)

    return {
        "total_behaviors": total,
        "uv": int(df["user_id"].nunique()),
        "item_count": int(df["item_id"].nunique()),
        "category_count": int(df["category_id"].nunique()),
        "pv_count": int(behavior_counts.get("pv", 0)),
        "fav_count": int(behavior_counts.get("fav", 0)),
        "cart_count": int(behavior_counts.get("cart", 0)),
        "buy_count": int(behavior_counts.get("buy", 0)),
        "pv_share": round(behavior_counts.get("pv", 0) / total, 4),
        "cart_share": round(behavior_counts.get("cart", 0) / total, 4),
        "buy_share": round(behavior_counts.get("buy", 0) / total, 4),
    }


# ---------- 2. 用户级漏斗 ----------
def user_level_funnel(df: pd.DataFrame) -> pd.DataFrame:
    """用户级漏斗：只要用户曾经有过该行为即计入。"""
    steps = [
        ("01_viewed", "pv"),
        ("02_favorited", "fav"),
        ("03_added_to_cart", "cart"),
        ("04_purchased", "buy"),
    ]

    rows = []
    for step_name, behavior in steps:
        users = df[df["behavior_type"] == behavior]["user_id"].nunique()
        rows.append({"step": step_name, "users": users})

    result = pd.DataFrame(rows)
    first = result.loc[0, "users"]
    result["conversion_from_view"] = (result["users"] / first).round(4)
    return result


# ---------- 3. 用户-商品级漏斗 ----------
def user_item_sequential_funnel(df: pd.DataFrame) -> dict:
    """用户-商品级漏斗：同一用户在同一商品上的先后行为。"""
    events = df[df["behavior_type"].isin(["pv", "fav", "cart", "buy"])].copy()

    first_times = events.pivot_table(
        index=["user_id", "item_id"],
        columns="behavior_type",
        values="behavior_time",
        aggfunc="min",
    )
    for column in ["pv", "fav", "cart", "buy"]:
        if column not in first_times.columns:
            first_times[column] = pd.NaT

    viewed = first_times["pv"].notna()
    favorited = first_times["fav"].notna()
    carted = first_times["cart"].notna()
    bought = first_times["buy"].notna()

    pv_to_buy = viewed & bought & (first_times["buy"] >= first_times["pv"])
    pv_to_cart = viewed & carted & (first_times["cart"] >= first_times["pv"])
    cart_to_buy = carted & bought & (first_times["buy"] >= first_times["cart"])
    fav_to_buy = favorited & bought & (first_times["buy"] >= first_times["fav"])

    viewed_pairs = int(viewed.sum())
    carted_pairs = int(carted.sum())
    favorited_pairs = int(favorited.sum())

    return {
        "user_item_pairs": int(len(first_times)),
        "viewed_pairs": viewed_pairs,
        "carted_pairs": carted_pairs,
        "favorited_pairs": favorited_pairs,
        "bought_pairs": int(bought.sum()),
        "pv_to_cart_pairs": int(pv_to_cart.sum()),
        "pv_to_buy_pairs": int(pv_to_buy.sum()),
        "cart_to_buy_pairs": int(cart_to_buy.sum()),
        "fav_to_buy_pairs": int(fav_to_buy.sum()),
        "pv_to_cart_rate": round(int(pv_to_cart.sum()) / viewed_pairs, 4) if viewed_pairs else 0,
        "pv_to_buy_rate": round(int(pv_to_buy.sum()) / viewed_pairs, 4) if viewed_pairs else 0,
        "cart_to_buy_rate": round(int(cart_to_buy.sum()) / carted_pairs, 4) if carted_pairs else 0,
        "fav_to_buy_rate": round(int(fav_to_buy.sum()) / favorited_pairs, 4) if favorited_pairs else 0,
    }


# ---------- 4. 行为类型分布 ----------
def behavior_type_distribution(df: pd.DataFrame) -> pd.DataFrame:
    counts = df["behavior_type"].value_counts().reset_index()
    counts.columns = ["behavior_type", "behavior_count"]
    counts["behavior_share"] = (counts["behavior_count"] / counts["behavior_count"].sum()).round(4)
    return counts


# ---------- 5. 每日活跃用户 ----------
def daily_active_users(df: pd.DataFrame) -> pd.DataFrame:
    return df.groupby("date")["user_id"].nunique().reset_index(name="dau")


# ---------- 6. 每日购买趋势 ----------
def daily_purchase_trend(df: pd.DataFrame) -> pd.DataFrame:
    buy_df = df[df["behavior_type"] == "buy"]
    return (
        buy_df.groupby("date")
        .agg(
            purchase_count=("behavior_type", "size"),
            purchase_users=("user_id", "nunique"),
        )
        .reset_index()
    )


# ---------- 7. 小时活跃度 ----------
def hourly_activity(df: pd.DataFrame) -> pd.DataFrame:
    return df.groupby(["hour", "behavior_type"]).size().reset_index(name="behavior_count")


# ---------- 8. 购买 TOP10 类目 ----------
def top_categories_by_purchase(df: pd.DataFrame, top_n: int = 10) -> pd.DataFrame:
    buy_df = df[df["behavior_type"] == "buy"]
    return (
        buy_df.groupby("category_id")
        .agg(
            purchase_count=("behavior_type", "size"),
            buyer_count=("user_id", "nunique"),
        )
        .sort_values("purchase_count", ascending=False)
        .head(top_n)
        .reset_index()
    )


# ---------- 9. 类目转化分析 ----------
def category_conversion_analysis(df: pd.DataFrame, top_n: int = 20, min_pv: int = 30) -> pd.DataFrame:
    category_behavior = (
        df.pivot_table(
            index="category_id",
            columns="behavior_type",
            values="user_id",
            aggfunc="count",
            fill_value=0,
        )
        .rename_axis(None, axis=1)
        .reset_index()
    )
    for column in ["pv", "fav", "cart", "buy"]:
        if column not in category_behavior.columns:
            category_behavior[column] = 0

    category_behavior = category_behavior.rename(columns={
        "pv": "pv_count", "fav": "fav_count",
        "cart": "cart_count", "buy": "buy_count",
    })
    category_behavior["browse_to_buy_rate"] = (
        category_behavior["buy_count"] / category_behavior["pv_count"].replace(0, float("nan"))
    ).fillna(0.0).round(4)
    category_behavior["cart_to_buy_rate"] = (
        category_behavior["buy_count"] / category_behavior["cart_count"].replace(0, float("nan"))
    ).fillna(0.0).round(4)

    return (
        category_behavior[category_behavior["pv_count"] >= min_pv]
        .sort_values(["buy_count", "browse_to_buy_rate"], ascending=False)
        .head(top_n)
        .reset_index(drop=True)
    )


# ---------- 10. 复购分析 ----------
def repurchase_analysis(df: pd.DataFrame) -> dict:
    user_buy = df[df["behavior_type"] == "buy"].groupby("user_id").size()
    total_buyers = int(len(user_buy))
    repurchase_users = int((user_buy >= 2).sum())
    return {
        "total_buyers": total_buyers,
        "repurchase_users": repurchase_users,
        "repurchase_rate": round(repurchase_users / total_buyers, 4) if total_buyers else 0,
    }


# ---------- 11. 加购未购买用户 ----------
def cart_without_purchase_users(df: pd.DataFrame) -> pd.DataFrame:
    user_flags = df.pivot_table(
        index="user_id",
        columns="behavior_type",
        values="item_id",
        aggfunc="count",
        fill_value=0,
    )
    user_flags.columns.name = None
    for column in ["cart", "buy"]:
        if column not in user_flags.columns:
            user_flags[column] = 0

    result = user_flags[(user_flags["cart"] > 0) & (user_flags["buy"] == 0)].reset_index()
    return result[["user_id", "cart"]].rename(columns={"cart": "cart_count"})


# ---------- 12. 高价值用户 ----------
def high_value_users(df: pd.DataFrame, top_n: int = 20) -> pd.DataFrame:
    buy_df = df[df["behavior_type"] == "buy"]
    if buy_df.empty:
        return pd.DataFrame(columns=["user_id", "purchase_count", "distinct_items_bought", "active_days", "value_score"])

    user_purchase = buy_df.groupby("user_id").agg(
        purchase_count=("behavior_type", "size"),
        distinct_items_bought=("item_id", "nunique"),
        distinct_categories_bought=("category_id", "nunique"),
    )
    user_active_days = df.groupby("user_id")["date"].nunique().rename("active_days")
    result = user_purchase.join(user_active_days, how="left").fillna(0)
    result["value_score"] = (
        result["purchase_count"] * 5
        + result["distinct_items_bought"] * 2
        + result["distinct_categories_bought"]
        + result["active_days"]
    )
    return result.sort_values(["value_score", "purchase_count"], ascending=False).head(top_n).reset_index()


# ---------- 13. 用户分层 ----------
def user_segmentation(df: pd.DataFrame) -> pd.DataFrame:
    user_behavior = (
        df.pivot_table(
            index="user_id",
            columns="behavior_type",
            values="item_id",
            aggfunc="count",
            fill_value=0,
        )
        .rename_axis(None, axis=1)
        .reset_index()
    )
    for column in ["pv", "fav", "cart", "buy"]:
        if column not in user_behavior.columns:
            user_behavior[column] = 0

    active_days = df.groupby("user_id")["date"].nunique().rename("active_days").reset_index()
    user_behavior = user_behavior.merge(active_days, on="user_id", how="left")

    user_behavior["purchase_segment"] = pd.cut(
        user_behavior["buy"],
        bins=[-1, 0, 1, 3, float("inf")],
        labels=["no_purchase", "one_purchase", "two_to_three", "four_plus"],
    )
    user_behavior["behavior_depth"] = "browse_only"
    user_behavior.loc[user_behavior["fav"] > 0, "behavior_depth"] = "favorited"
    user_behavior.loc[user_behavior["cart"] > 0, "behavior_depth"] = "added_to_cart"
    user_behavior.loc[user_behavior["buy"] > 0, "behavior_depth"] = "purchased"

    return (
        user_behavior.groupby(["behavior_depth", "purchase_segment"], observed=True)
        .agg(
            users=("user_id", "nunique"),
            avg_active_days=("active_days", "mean"),
            total_purchases=("buy", "sum"),
            avg_purchase_count=("buy", "mean"),
            avg_cart_count=("cart", "mean"),
        )
        .reset_index()
        .sort_values(["behavior_depth", "purchase_segment"])
    )


# ---------- 14. 显著性检验 ----------
# 全量 SQL 分析结果（来自顶层 README「SQL × Python 交叉验证」表）
FULL_DATA_METRICS = {
    "buy_share": {"full": 0.0201, "n_desc": "全量行为数 100,150,807"},
    "pv_to_buy_rate": {"full": 0.0140, "n_desc": "全量用户-商品对（pv）"},
    "cart_to_buy_rate": {"full": 0.0606, "n_desc": "全量用户-商品对（cart）"},
    "repurchase_rate": {"full": 0.6601, "n_desc": "全量购买用户数"},
}


def two_proportion_z_test(success_a: int, n_a: int, success_b: int, n_b: int) -> dict:
    """双样本比例 z 检验，返回 z 值、p 值与差值的 95% 置信区间。"""
    p_a, p_b = success_a / n_a, success_b / n_b
    p_pool = (success_a + success_b) / (n_a + n_b)
    se_pool = np.sqrt(p_pool * (1 - p_pool) * (1 / n_a + 1 / n_b))
    z = (p_a - p_b) / se_pool
    p_value = 2 * (1 - stats.norm.cdf(abs(z)))

    # 差值置信区间（非合并标准误）
    se_diff = np.sqrt(p_a * (1 - p_a) / n_a + p_b * (1 - p_b) / n_b)
    ci_low = (p_a - p_b) - 1.96 * se_diff
    ci_high = (p_a - p_b) + 1.96 * se_diff

    return {
        "rate_a": round(p_a, 4),
        "rate_b": round(p_b, 4),
        "diff": round(p_a - p_b, 4),
        "diff_ci95": [round(ci_low, 4), round(ci_high, 4)],
        "z": round(float(z), 3),
        "p_value": float(f"{p_value:.3e}"),
        "significant": bool(p_value < 0.05),
        "n_a": n_a,
        "n_b": n_b,
    }


def conversion_test_by_flag(df: pd.DataFrame, flag_behavior: str) -> dict:
    """有某行为的用户 vs 没有的用户，购买转化率两比例 z 检验（用户级）。"""
    label = {"cart": "加购", "fav": "收藏"}[flag_behavior]
    user_flags = df.groupby("user_id")["behavior_type"].agg(lambda s: set(s.unique()))
    has = user_flags[user_flags.apply(lambda x: flag_behavior in x)]
    hasnt = user_flags[user_flags.apply(lambda x: flag_behavior not in x)]

    result = two_proportion_z_test(
        success_a=int(has.apply(lambda x: "buy" in x).sum()),
        n_a=len(has),
        success_b=int(hasnt.apply(lambda x: "buy" in x).sum()),
        n_b=len(hasnt),
    )
    result["group_a"] = f"{label}用户（{flag_behavior}）"
    result["group_b"] = f"未{label}用户"
    return result


def wilson_ci(success: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score 置信区间，小比例下比正态近似更稳。"""
    p = success / n
    denom = 1 + z**2 / n
    center = (p + z**2 / (2 * n)) / denom
    margin = z * np.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / denom
    return center - margin, center + margin


def sampling_confidence_checks(df: pd.DataFrame) -> list[dict]:
    """核心指标的 95% 置信区间，并检查全量值是否落在区间内。"""
    funnel = user_item_sequential_funnel(df)
    repurchase = repurchase_analysis(df)
    behavior_counts = df["behavior_type"].value_counts()
    total = len(df)

    samples = {
        "buy_share": (int(behavior_counts.get("buy", 0)), total),
        "pv_to_buy_rate": (funnel["pv_to_buy_pairs"], funnel["viewed_pairs"]),
        "cart_to_buy_rate": (funnel["cart_to_buy_pairs"], funnel["carted_pairs"]),
        "repurchase_rate": (repurchase["repurchase_users"], repurchase["total_buyers"]),
    }

    rows = []
    for metric, (success, n) in samples.items():
        low, high = wilson_ci(success, n)
        full = FULL_DATA_METRICS[metric]["full"]
        rows.append({
            "metric": metric,
            "sample_rate": round(success / n, 4),
            "ci95_low": round(low, 4),
            "ci95_high": round(high, 4),
            "full_data_rate": full,
            "full_in_ci": bool(low <= full <= high),
            "margin_of_error": round((high - low) / 2, 4),
            "n": n,
            "n_desc": FULL_DATA_METRICS[metric]["n_desc"],
        })
    return rows


def dau_peak_analysis(df: pd.DataFrame) -> dict:
    """DAU 峰值分析：工作日 vs 周末分组对比 + 12-02 相对基线提升。

    样本仅 9 天，z-score 统计上不成立，采用分组对比。
    """
    daily = df.groupby("date")["user_id"].nunique().reset_index(name="dau")
    daily["date"] = pd.to_datetime(daily["date"])
    daily["weekday"] = daily["date"].dt.weekday  # 0=周一
    daily["is_weekend"] = daily["weekday"] >= 5

    buy_daily = (
        df[df["behavior_type"] == "buy"].groupby("date")["user_id"].nunique().reset_index(name="buy_users")
    )
    buy_daily["date"] = pd.to_datetime(buy_daily["date"])
    daily = daily.merge(buy_daily, on="date", how="left").fillna({"buy_users": 0})

    weekend = daily[daily["is_weekend"]]
    weekday = daily[~daily["is_weekend"]]

    baseline = daily[daily["date"] < "2017-12-02"]
    peak = daily[daily["date"] == "2017-12-02"].iloc[0]

    return {
        "weekday_dau_mean": round(weekday["dau"].mean()),
        "weekend_dau_mean": round(weekend["dau"].mean()),
        "weekend_vs_weekday_lift": round(
            weekend["dau"].mean() / weekday["dau"].mean() - 1, 4
        ),
        "weekday_buy_users_mean": round(weekday["buy_users"].mean()),
        "weekend_buy_users_mean": round(weekend["buy_users"].mean()),
        "peak_date": "2017-12-02",
        "peak_dau": int(peak["dau"]),
        "baseline_dau_mean": round(baseline["dau"].mean()),
        "peak_vs_baseline_lift": round(
            peak["dau"] / baseline["dau"].mean() - 1, 4
        ),
        "peak_buy_users": int(peak["buy_users"]),
        "baseline_buy_users_mean": round(baseline["buy_users"].mean()),
        "peak_buy_vs_baseline_lift": round(
            peak["buy_users"] / baseline["buy_users"].mean() - 1, 4
        ),
        "note": "样本仅 9 天，不做 z-score 异常检测，采用分组对比 + 基线提升幅度",
        "daily_detail": daily.assign(date=daily["date"].dt.strftime("%Y-%m-%d")).to_dict("records"),
    }


# ---------- 15. RFM 用户分层 ----------
# 无金额维度，做 RF 两维打分；窗口仅 9 天，R 天粒度粗（大量用户末日购买），
# 按窗口手工分箱而非 30 天经典阈值
RFM_SEGMENT_ORDER = [
    "重要价值客户", "重要发展客户", "重要保持客户", "重要挽留客户",
    "一般价值客户", "一般挽留客户", "未购买用户",
]


def compute_rfm(df: pd.DataFrame) -> pd.DataFrame:
    """对每个用户计算 R（最近一次购买距观测窗口最后一天的天数）与 F（购买次数）。"""
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


def score_rfm(rf: pd.DataFrame) -> pd.DataFrame:
    """R/F 打分（1~4）并映射到 6 个购买用户层级 + 未购买用户。"""
    buyers = rf[rf["is_buyer"]].copy()

    # R 越小越好：0 天=4 分，1 天=3 分，2~3 天=2 分，4~8 天=1 分
    buyers["r_score"] = pd.cut(
        buyers["recency_days"], bins=[-0.1, 0, 1, 3, 8], labels=[4, 3, 2, 1]
    ).astype(int)
    # F 越大分越高（rank 避免 qcut 重复边界）
    buyers["f_score"] = pd.qcut(
        buyers["frequency"].rank(method="first"), 4, labels=[1, 2, 3, 4]
    ).astype(int)
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


def rfm_segment_summary(rf: pd.DataFrame) -> pd.DataFrame:
    summary = rf.groupby("segment").agg(
        users=("user_id", "nunique"),
        avg_frequency=("frequency", "mean"),
        avg_recency_days=("recency_days", "mean"),
    ).reset_index()
    total = summary["users"].sum()
    summary["user_share"] = (summary["users"] / total).round(4)
    summary["avg_frequency"] = summary["avg_frequency"].round(2)
    summary["avg_recency_days"] = summary["avg_recency_days"].round(2)
    return summary.set_index("segment").reindex(RFM_SEGMENT_ORDER).reset_index()


# ---------- 16. 次日留存分析 ----------
# 9 天窗口缩水版：7 日留存只对第 1~2 天活跃用户有效，样本太薄，30 日做不了
RETENTION_LAYER_ORDER = ["1天", "2~3天", "4~5天", "6~9天"]


def _activity_layer(days: int) -> str:
    if days <= 1:
        return "1天"
    if days <= 3:
        return "2~3天"
    if days <= 5:
        return "4~5天"
    return "6~9天"


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


def retention_by_activity_layer(df: pd.DataFrame) -> pd.DataFrame:
    """按活跃分层（窗口内活跃天数）的次日留存。

    分层口径：对每个用户，其每个"有次日"的活跃日，若次日仍活跃计 1 次
    留存；层内按 人-日对 汇总。
    """
    user_days = df.groupby("user_id")["date"].apply(lambda s: set(s.unique()))
    layer_of = df.groupby("user_id")["date"].nunique().apply(_activity_layer).rename("layer")

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
    ).reindex(RETENTION_LAYER_ORDER).reset_index()
    summary["next_day_retention"] = (
        summary["retained_pairs"] / summary["eligible_pairs"]
    ).round(4)
    summary["avg_eligible_days"] = (summary["eligible_pairs"] / summary["users"]).round(2)
    return summary[["layer", "users", "avg_eligible_days",
                    "eligible_pairs", "retained_pairs", "next_day_retention"]]


# ---------- 17. 用户路径分析 ----------
# 用户-商品级三段路径：浏览 → 中间行为 → 结果。
# 同一 (user,item,behavior) 多条记录取首次；时间并列时按 pv<fav<cart<buy 次序
PATH_BEHAVIOR_ORDER = {"pv": 0, "fav": 1, "cart": 2, "buy": 3}


def classify_user_paths(df: pd.DataFrame) -> pd.DataFrame:
    """对每个用户-商品对归类主路径，返回带 path / outcome 列的 pair 级表。

    path：仅浏览 / 直接购买（buy 之前无 fav/cart）/ 先加购 / 先收藏
    outcome：购买 / 未购买
    """
    events = df[df["behavior_type"].isin(["pv", "fav", "cart", "buy"])].copy()

    tie_break = events["behavior_type"].map(PATH_BEHAVIOR_ORDER).astype(float) / 1e6
    events["first_time"] = events["behavior_time"] + pd.to_timedelta(tie_break, unit="s")

    first = events.pivot_table(
        index=["user_id", "item_id"],
        columns="behavior_type",
        values="first_time",
        aggfunc="min",
    )
    for col in ["pv", "fav", "cart", "buy"]:
        if col not in first.columns:
            first[col] = pd.NaT
    first = first.reset_index()

    pairs = first[first["pv"].notna()].copy()

    buy, cart, fav = pairs["buy"], pairs["cart"], pairs["fav"]
    any_after = buy.notna() | cart.notna() | fav.notna()
    direct_buy = buy.notna() & (cart.isna() | (buy < cart)) & (fav.isna() | (buy < fav))
    cart_first = ~direct_buy & cart.notna() & (fav.isna() | (cart <= fav))
    fav_first = ~direct_buy & ~cart_first & fav.notna()

    pairs["path"] = np.select(
        [~any_after, direct_buy, cart_first, fav_first],
        ["仅浏览", "直接购买", "先加购", "先收藏"],
        default="先加购",
    )

    pairs["outcome"] = "未购买"
    pairs.loc[pairs["buy"].notna(), "outcome"] = "购买"
    pairs.loc[pairs["path"] == "仅浏览", "outcome"] = "未购买"
    return pairs[["user_id", "item_id", "path", "outcome"]]


def user_path_summary(pairs: pd.DataFrame) -> pd.DataFrame:
    n = len(pairs)
    summary = pairs.groupby("path").agg(
        pairs=("item_id", "size"),
        purchased=("outcome", lambda s: (s == "购买").sum()),
    ).reset_index()
    summary["share_of_browsed"] = (summary["pairs"] / n).round(4)
    summary["purchase_rate"] = (summary["purchased"] / summary["pairs"]).round(4)
    return summary.sort_values("pairs", ascending=False).reset_index(drop=True)


# ---------- 18. 类目级关联规则挖掘 ----------
# 技术红线（见 plan.md）：商品 ID 脱敏无业务含义且数据极稀疏，商品级
# Apriori（support=0.01）挖不出规则；稠密 one-hot 会 OOM。
# 因此按 category_id 聚合购物篮，做 2-项集精确计数——结果与 FP-Growth
# 的 2-项集完全一致，无需稠密矩阵，也不依赖 mlxtend。


def build_baskets(df: pd.DataFrame, min_categories: int = 2) -> list[frozenset]:
    """购买记录 → 每用户去重类目集合，过滤无法形成关联的篮子。"""
    baskets = (
        df[df["behavior_type"] == "buy"]
        .groupby("user_id")["category_id"]
        .apply(lambda s: frozenset(s.unique()))
    )
    baskets = baskets[baskets.apply(len) >= min_categories]
    print(f"购物篮数（购买 ≥{min_categories} 个类目）：{len(baskets):,}")
    sizes = baskets.apply(len)
    print(f"篮子类目数分布：均值 {sizes.mean():.2f}，中位数 {sizes.median():.0f}，"
          f"最大 {sizes.max()}")
    return baskets.tolist()


def mine_association_rules(baskets: list[frozenset], min_support: float,
                           min_confidence: float, min_lift: float,
                           top_n: int) -> pd.DataFrame:
    """对购物篮做 2-项集精确挖掘，按提升度排序取 Top N。

    support(A→B) = 同时含 A、B 的购物篮数 / 总购物篮数
    confidence(A→B) = 同时含 A、B 的购物篮数 / 含 A 的购物篮数
    lift(A→B) = confidence(A→B) / P(B)
    """
    n_baskets = len(baskets)
    item_count = Counter()
    pair_count = Counter()
    for basket in baskets:
        item_count.update(basket)
        if len(basket) >= 2:
            pair_count.update(combinations(sorted(basket), 2))

    min_pair = min_support * n_baskets
    rows = []
    for (a, b), both in pair_count.items():
        support = both / n_baskets
        confidence_ab = both / item_count[a]
        confidence_ba = both / item_count[b]
        # A→B 与 B→A 支持度相同，置信度不同，各生成一条规则
        for ante, cons, conf in ((a, b, confidence_ab), (b, a, confidence_ba)):
            lift = conf / (item_count[cons] / n_baskets)
            if support >= min_support and conf >= min_confidence and lift > min_lift:
                rows.append({
                    "antecedent_category": ante,
                    "consequent_category": cons,
                    "support": round(support, 6),
                    "confidence": round(conf, 4),
                    "lift": round(lift, 4),
                    "pair_baskets": both,
                    "antecedent_baskets": int(item_count[ante]),
                    "consequent_baskets": int(item_count[cons]),
                    "total_baskets": n_baskets,
                })
    rules = pd.DataFrame(rows)
    if rules.empty:
        return rules
    return rules.sort_values("lift", ascending=False).head(top_n).reset_index(drop=True)


# ---------- 打印工具 ----------
def print_section(title: str, value: object) -> None:
    print(f"\n{title}")
    print("-" * len(title))
    print(value)


# ---------- 主入口 ----------
def main() -> None:
    parser = argparse.ArgumentParser(description="Taobao behavior analysis on cleaned stratified data.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="Cleaned CSV path.")
    args = parser.parse_args()

    df = load_data(args.input)

    # 核心分析
    print_section("Core Metrics", pd.Series(summarize_behavior_metrics(df)))
    print_section("Behavior Type Distribution", behavior_type_distribution(df))
    print_section("User-Level Funnel", user_level_funnel(df))
    print_section("User-Item Sequential Funnel", pd.Series(user_item_sequential_funnel(df)))
    print_section("Daily Active Users", daily_active_users(df))
    print_section("Daily Purchase Trend", daily_purchase_trend(df))
    print_section("Hourly Activity", hourly_activity(df).head(24))
    print_section("Top 10 Categories by Purchase", top_categories_by_purchase(df))
    print_section("Category Conversion Analysis", category_conversion_analysis(df, top_n=10))
    print_section("Repurchase Analysis", pd.Series(repurchase_analysis(df)))
    print_section("Cart Without Purchase Users", cart_without_purchase_users(df).head(20))
    print_section("High Value Users", high_value_users(df))
    print_section("User Segmentation", user_segmentation(df))

    # 深化分析，结果表保存到 reports/
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    cart_test = conversion_test_by_flag(df, "cart")
    fav_test = conversion_test_by_flag(df, "fav")
    print_section("Significance: cart vs non-cart (two-proportion z-test)",
                  pd.Series(cart_test))
    print_section("Significance: fav vs non-fav (two-proportion z-test)",
                  pd.Series(fav_test))
    checks = sampling_confidence_checks(df)
    print_section("Sampling vs Full: 95% CI", pd.DataFrame(checks))
    dau = dau_peak_analysis(df)
    daily_detail = dau.pop("daily_detail")
    print_section("DAU Peak Analysis", pd.Series(dau))

    rfm_summary = rfm_segment_summary(score_rfm(compute_rfm(df)))
    print_section("RFM Segments", rfm_summary)

    print_section("Next-Day Retention (daily)", daily_next_day_retention(df))
    layered = retention_by_activity_layer(df)
    print_section("Next-Day Retention (by activity layer)", layered)

    pairs = classify_user_paths(df)
    print_section("User-Item Path Summary", user_path_summary(pairs))

    baskets = build_baskets(df)
    rules = mine_association_rules(baskets, min_support=0.0005,
                                   min_confidence=0.10, min_lift=1.0, top_n=100)
    print_section("Association Rules (category-level, top by lift)", rules.head(20))

    # 保存结果表
    significance = {
        "z_tests": {"加购 vs 未加购": cart_test, "收藏 vs 未收藏": fav_test},
        "sampling_vs_full": checks,
        "dau_peak": dau,
    }
    (REPORTS_DIR / "significance_tests.json").write_text(
        json.dumps(significance, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    rfm_summary.to_csv(
        REPORTS_DIR / "rfm_segments.csv", index=False, encoding="utf-8-sig")
    layered.to_csv(REPORTS_DIR / "retention_summary.csv", index=False, encoding="utf-8-sig")
    user_path_summary(pairs).to_csv(REPORTS_DIR / "path_summary.csv", index=False, encoding="utf-8-sig")
    rules.to_csv(REPORTS_DIR / "association_rules.csv", index=False, encoding="utf-8-sig")
    print(f"\n结果表已保存到：{REPORTS_DIR}")


if __name__ == "__main__":
    main()
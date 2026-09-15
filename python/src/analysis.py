"""Core Pandas analysis for Taobao user behavior and conversion funnels.

本版本分析「分层抽样 + 正式清洗」后的数据。
输入：cleaned_stratified_data.csv
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from config import CLEANED_FILE


DEFAULT_INPUT = CLEANED_FILE


# ---------- 修改点 1：load_data 派生分析所需列 ----------
def load_data(input_path: Path = DEFAULT_INPUT) -> pd.DataFrame:
    """读取清洗后的分层数据，并派生分析所需的时间列。"""
    df = pd.read_csv(input_path, parse_dates=["timestamp"])

    # 从 timestamp 派生分析所需的三列
    df["behavior_time"] = df["timestamp"]     # 完整时间戳
    df["date"] = df["timestamp"].dt.date      # 日期
    df["hour"] = df["timestamp"].dt.hour      # 小时（0~23）

    print(f"📥 加载数据：{input_path}")
    print(f"   行数：{len(df):,}")
    print(f"   用户数：{df['user_id'].nunique():,}")
    print(f"   时间范围：{df['timestamp'].min()} ~ {df['timestamp'].max()}")
    return df


def weighted_count(df: pd.DataFrame, group_col: str = None) -> pd.Series:
    """加权计数：按 group_col 分组，对 weight 求和。"""
    if group_col:
        return df.groupby(group_col)["weight"].sum()
    return pd.Series([df["weight"].sum()], index=["total"])


# ---------- 以下所有分析函数保持不变 ----------
def summarize_behavior_metrics(df: pd.DataFrame) -> dict:
    # 加权后的行为计数
    weighted_counts = df.groupby("behavior_type")["weight"].sum()

    # 加权后的行为分布
    total_weight = df["weight"].sum()

    return {
        "total_behaviors_weighted": round(total_weight, 2),
        "uv": int(df["user_id"].nunique()),   # UV 不必加权（已经抽了用户）
        "item_count": int(df["item_id"].nunique()),
        "category_count": int(df["category_id"].nunique()),
        "pv_count_weighted": round(weighted_counts.get("pv", 0), 2),
        "fav_count_weighted": round(weighted_counts.get("fav", 0), 2),
        "cart_count_weighted": round(weighted_counts.get("cart", 0), 2),
        "buy_count_weighted": round(weighted_counts.get("buy", 0), 2),
        "pv_share_weighted": round(weighted_counts.get("pv", 0) / total_weight, 4),
        "cart_share_weighted": round(weighted_counts.get("cart", 0) / total_weight, 4),
        "buy_share_weighted": round(weighted_counts.get("buy", 0) / total_weight, 4),
    }


def user_level_funnel(df: pd.DataFrame) -> pd.DataFrame:
    """加权版漏斗：每个用户按其权重计入。"""
    # 每个用户在所有行为上的权重（同一用户各行 weight 相同）
    user_weight = df.groupby("user_id")["weight"].first()

    steps = [
        ("01_viewed", "pv"),
        ("02_favorited", "fav"),
        ("03_added_to_cart", "cart"),
        ("04_purchased", "buy"),
    ]

    rows = []
    for step_name, behavior in steps:
        # 有该行为的用户
        users = df[df["behavior_type"] == behavior]["user_id"].unique()
        weighted_users = user_weight.loc[users].sum()
        rows.append({"step": step_name, "weighted_users": weighted_users})

    result = pd.DataFrame(rows)
    first = result.loc[0, "weighted_users"]
    result["conversion_from_view"] = (result["weighted_users"] / first).round(4)
    return result


def user_item_sequential_funnel(df: pd.DataFrame) -> dict[str, float | int]:
    """Calculate stricter user-item funnel rates that respect event order."""
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
        "pv_to_cart_pair_rate": round(int(pv_to_cart.sum()) / viewed_pairs, 4) if viewed_pairs else 0,
        "pv_to_buy_pair_rate": round(int(pv_to_buy.sum()) / viewed_pairs, 4) if viewed_pairs else 0,
        "cart_to_buy_pair_rate": round(int(cart_to_buy.sum()) / carted_pairs, 4) if carted_pairs else 0,
        "fav_to_buy_pair_rate": round(int(fav_to_buy.sum()) / favorited_pairs, 4) if favorited_pairs else 0,
    }


def behavior_type_distribution(df: pd.DataFrame) -> pd.DataFrame:
    counts = df.groupby("behavior_type")["weight"].sum().reset_index()
    counts = counts.rename(columns={"weight": "behavior_count_weighted"})
    counts["behavior_share_weighted"] = (
        counts["behavior_count_weighted"] / counts["behavior_count_weighted"].sum()
    ).round(4)
    return counts

def daily_active_users(df: pd.DataFrame) -> pd.DataFrame:
    # 加权 DAU：每个用户的权重就是 1/抽样率，除以权重就是还原后的 UV
    dau = df.groupby(["date", "user_id"])["weight"].first().reset_index()
    result = dau.groupby("date")["weight"].sum().reset_index(name="dau_weighted")
    return result

def daily_purchase_trend(df: pd.DataFrame) -> pd.DataFrame:
    buy_df = df[df["behavior_type"] == "buy"]

    # 每天的加权购买行为数
    counts = buy_df.groupby("date")["weight"].sum().rename("purchase_count_weighted")

    # 每天的加权购买用户数（按 user_id 去重后加权）
    user_day = (
        buy_df.groupby(["date", "user_id"])["weight"]
        .first()
        .reset_index()
    )
    users = user_day.groupby("date")["weight"].sum().rename("purchase_users_weighted")

    return pd.concat([counts, users], axis=1).reset_index()


def hourly_activity(df: pd.DataFrame) -> pd.DataFrame:
    return df.groupby(["hour", "behavior_type"]).size().reset_index(name="behavior_count")

def top_categories_by_purchase(df: pd.DataFrame, top_n: int = 10) -> pd.DataFrame:
    buy_df = df[df["behavior_type"] == "buy"]
    return (
        buy_df.groupby("category_id")
        .agg(
            purchase_count_weighted=("weight", "sum"),
            buyer_count=("user_id", "nunique"),
        )
        .sort_values("purchase_count_weighted", ascending=False)
        .head(top_n)
        .reset_index()
    )


def category_conversion_analysis(df: pd.DataFrame, top_n: int = 20, min_pv: int = 30) -> pd.DataFrame:
    """Summarize category-level behavior volume and conversion efficiency."""
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

    category_behavior = category_behavior.rename(
        columns={
            "pv": "pv_count",
            "fav": "fav_count",
            "cart": "cart_count",
            "buy": "buy_count",
        }
    )
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


def repurchase_analysis(df: pd.DataFrame) -> dict:
    buy_df = df[df["behavior_type"] == "buy"]

    # 每个用户的：实际购买次数 + 权重
    user_stats = buy_df.groupby("user_id").agg(
        buy_count=("behavior_type", "size"),   # 实际次数（不加权）
        weight=("weight", "first"),            # 该用户的权重
    )

    # 加权总购买用户数
    total_buyers_weighted = user_stats["weight"].sum()

    # 加权复购用户数：用"实际次数 >= 2"筛选，再按权重汇总
    repurchase_users_weighted = user_stats[user_stats["buy_count"] >= 2]["weight"].sum()

    return {
        "total_buyers": int(total_buyers_weighted),
        "repurchase_users": int(repurchase_users_weighted),
        "repurchase_rate": round(repurchase_users_weighted / total_buyers_weighted, 4)
        if total_buyers_weighted else 0,
    }


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


def user_segmentation(df: pd.DataFrame) -> pd.DataFrame:
    """Group users by behavior depth and summarize value indicators."""
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
    user_behavior["activity_segment"] = pd.cut(
        user_behavior["active_days"],
        bins=[0, 2, 5, float("inf")],
        labels=["low_active", "medium_active", "high_active"],
        include_lowest=True,
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


def print_section(title: str, value: object) -> None:
    print(f"\n{title}")
    print("-" * len(title))
    print(value)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Taobao behavior analysis on stratified cleaned data.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="Cleaned stratified CSV path.")
    args = parser.parse_args()

    df = load_data(args.input)
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


if __name__ == "__main__":
    main()
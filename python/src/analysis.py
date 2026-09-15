"""Core Pandas analysis for Taobao user behavior and conversion funnels.

输入：cleaned_stratified_data.csv
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from config import CLEANED_FILE


DEFAULT_INPUT = CLEANED_FILE


# ---------- 加载数据 ----------
def load_data(input_path: Path = DEFAULT_INPUT) -> pd.DataFrame:
    df = pd.read_csv(input_path, parse_dates=["timestamp"])

    # 派生分析所需的三列
    df["behavior_time"] = df["timestamp"]     # 完整时间戳
    df["date"] = df["timestamp"].dt.date      # 日期
    df["hour"] = df["timestamp"].dt.hour      # 小时

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
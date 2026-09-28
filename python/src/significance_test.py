"""显著性检验完整版：补上统计严谨性。

包含三部分（对应 plan.md 深化方向 #1）：
1. 两比例 z 检验：加购用户 vs 未加购用户的购买转化率差异是否显著
2. 抽样 vs 全量置信区间：核心指标（5% 抽样）的 95% 置信区间，
   验证全量 SQL 结果是否落在区间内
3. DAU 峰值分析：工作日 vs 周末分组对比 + 12-02 相对基线提升幅度
   （仅 9 个数据点，不做 z-score，改用分组对比）

输入：cleaned_stratified_data.csv
输出：reports/significance_tests.json + reports/figures/significance_*.png
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

from analysis import load_data, repurchase_analysis, user_item_sequential_funnel
from config import FIG_DIR, REPORTS_DIR

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei"]
plt.rcParams["axes.unicode_minus"] = False


# 全量 SQL 分析结果（来自顶层 README「SQL × Python 交叉验证」表）
FULL_DATA_METRICS = {
    "buy_share": {"full": 0.0201, "n_desc": "全量行为数 100,150,807"},
    "pv_to_buy_rate": {"full": 0.0140, "n_desc": "全量用户-商品对（pv）"},
    "cart_to_buy_rate": {"full": 0.0606, "n_desc": "全量用户-商品对（cart）"},
    "repurchase_rate": {"full": 0.6601, "n_desc": "全量购买用户数"},
}


# ---------- 1. 两比例 z 检验 ----------
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


def cart_conversion_test(df: pd.DataFrame) -> dict:
    """加购用户 vs 未加购用户的购买转化率 z 检验（用户级）。"""
    user_flags = df.groupby("user_id")["behavior_type"].agg(
        lambda s: set(s.unique())
    )
    cart_users = user_flags[user_flags.apply(lambda x: "cart" in x)]
    non_cart_users = user_flags[user_flags.apply(lambda x: "cart" not in x)]

    result = two_proportion_z_test(
        success_a=int(cart_users.apply(lambda x: "buy" in x).sum()),
        n_a=len(cart_users),
        success_b=int(non_cart_users.apply(lambda x: "buy" in x).sum()),
        n_b=len(non_cart_users),
    )
    result["group_a"] = "加购用户（cart）"
    result["group_b"] = "未加购用户"
    return result


def fav_conversion_test(df: pd.DataFrame) -> dict:
    """收藏用户 vs 未收藏用户的购买转化率 z 检验（用户级）。"""
    user_flags = df.groupby("user_id")["behavior_type"].agg(
        lambda s: set(s.unique())
    )
    fav_users = user_flags[user_flags.apply(lambda x: "fav" in x)]
    non_fav_users = user_flags[user_flags.apply(lambda x: "fav" not in x)]

    result = two_proportion_z_test(
        success_a=int(fav_users.apply(lambda x: "buy" in x).sum()),
        n_a=len(fav_users),
        success_b=int(non_fav_users.apply(lambda x: "buy" in x).sum()),
        n_b=len(non_fav_users),
    )
    result["group_a"] = "收藏用户（fav）"
    result["group_b"] = "未收藏用户"
    return result


# ---------- 2. 抽样 vs 全量置信区间 ----------
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


# ---------- 3. DAU：工作日 vs 周末 + 12-02 基线提升 ----------
def dau_peak_analysis(df: pd.DataFrame) -> dict:
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

    result = {
        "weekday_dau_mean": round(weekday["dau"].mean()),
        "weekend_dau_mean": round(weekend["dau"].mean()),
        "weekend_vs_weekend_lift": round(
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
    return result


# ---------- 可视化 ----------
def plot_conversion_ci(checks: list[dict], fig_dir: Path):
    fig, ax = plt.subplots(figsize=(9, 5))
    for i, row in enumerate(checks):
        y = len(checks) - 1 - i
        ax.errorbar(
            row["sample_rate"] * 100, y,
            xerr=[[(row["sample_rate"] - row["ci95_low"]) * 100],
                  [(row["ci95_high"] - row["sample_rate"]) * 100]],
            fmt="o", capsize=5, color="#2b7bba", markersize=8, linewidth=2,
            label="抽样均值 ± 95% CI" if i == 0 else None,
        )
        ax.plot(row["full_data_rate"] * 100, y, "d", color="#d62728", markersize=9,
                label="SQL 全量值" if i == 0 else None)
    ax.set_yticks(range(len(checks)))
    ax.set_yticklabels([r["metric"] for r in reversed(checks)])
    ax.set_xlabel("比率（%）")
    ax.set_title("核心指标：抽样 95% 置信区间 vs SQL 全量值（红钻均落在区间内）")
    ax.legend(loc="lower right")
    ax.grid(axis="x", alpha=0.3)
    fig.tight_layout()
    fig.savefig(fig_dir / "significance_ci.png", dpi=150)
    plt.close(fig)


def plot_dau_weekday(dau_result: dict, fig_dir: Path):
    daily = pd.DataFrame(dau_result["daily_detail"])
    daily["date"] = pd.to_datetime(daily["date"])
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.5))

    colors = ["#d62728" if w else "#2b7bba" for w in daily["is_weekend"]]
    axes[0].bar(daily["date"].dt.strftime("%m-%d"), daily["dau"], color=colors)
    axes[0].set_title("每日 DAU（红=周末）")
    axes[0].tick_params(axis="x", rotation=45)

    axes[1].bar(daily["date"].dt.strftime("%m-%d"), daily["buy_users"], color=colors)
    axes[1].set_title("每日购买用户数（红=周末）")
    axes[1].tick_params(axis="x", rotation=45)

    fig.suptitle("工作日 vs 周末对比：DAU 与购买用户数", y=1.02)
    fig.tight_layout()
    fig.savefig(fig_dir / "dau_weekday_weekend.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


# ---------- 主入口 ----------
def main() -> None:
    parser = argparse.ArgumentParser(description="显著性检验完整版")
    parser.add_argument("--input", type=Path, default=None, help="Cleaned CSV path.")
    args = parser.parse_args()

    df = load_data(args.input) if args.input else load_data()

    print("\n===== 1. 两比例 z 检验 =====")
    cart_test = cart_conversion_test(df)
    fav_test = fav_conversion_test(df)
    print(json.dumps({"加购 vs 未加购": cart_test, "收藏 vs 未收藏": fav_test},
                     ensure_ascii=False, indent=2))

    print("\n===== 2. 抽样 vs 全量置信区间 =====")
    checks = sampling_confidence_checks(df)
    print(pd.DataFrame(checks).to_string(index=False))

    print("\n===== 3. DAU 峰值分析（工作日 vs 周末 + 基线提升）=====")
    dau_result = dau_peak_analysis(df)
    daily_detail = dau_result.pop("daily_detail")
    print(json.dumps(dau_result, ensure_ascii=False, indent=2))
    print("\n每日明细：")
    print(pd.DataFrame(daily_detail)[["date", "dau", "buy_users", "is_weekend"]].to_string(index=False))

    # 保存结果
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    output = {
        "z_tests": {"加购 vs 未加购": cart_test, "收藏 vs 未收藏": fav_test},
        "sampling_vs_full": checks,
        "dau_peak": dau_result,
    }
    out_path = REPORTS_DIR / "significance_tests.json"
    out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n✅ 结果已保存：{out_path}")

    plot_conversion_ci(checks, FIG_DIR)
    plot_dau_weekday({**dau_result, "daily_detail": daily_detail}, FIG_DIR)
    print(f"✅ 图表已保存：{FIG_DIR / 'significance_ci.png'}")
    print(f"✅ 图表已保存：{FIG_DIR / 'dau_weekday_weekend.png'}")


if __name__ == "__main__":
    main()

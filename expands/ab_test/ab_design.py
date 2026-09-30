"""A/B 测试框架 —— 实验设计与功效分析（基于历史数据的模拟实验）。

⚠️ 表述红线：这是**基于历史数据的模拟实验**，用于展示 A/B 测试方法论
（实验设计 → 随机化 → 检验 → AA 校准），不是真实在线实验。

模拟场景：双 12 前给「加购未购买」用户推送提醒，观察后续购买转化。

口径：
- 实验总体：2017-11-25 ~ 12-01 有加购、且截至 12-01 尚未购买的用户
- 观测结局：12-02 ~ 12-03 是否发生购买（历史真实结局，作为对照基线 p0）
- 干预效应：模拟注入（见 ab_simulation.py），历史数据本身不包含干预

本脚本回答实验设计问题：
1. 实验总体有多大、基线转化率 p0 是多少
2. 给定最小可检测效应 MDE，每组需要多少样本
3. 反过来：现有总体能支撑的最小可检测效应是多少（α=0.05, power=0.8）
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]  # 仓库根（本模块在 expands/ 下）
DATA_FILE = REPO_ROOT / "python" / "data" / "cleaned_stratified_data.csv"

CUTOFF = pd.Timestamp("2017-12-01 23:59:59")   # 实验开始前夜
END = pd.Timestamp("2017-12-03 23:59:59")      # 窗口结束

Z_ALPHA = 1.96    # α=0.05 双侧
Z_BETA = 0.84     # power=0.8


# ---------- 实验总体 ----------
def build_experiment_pool(df: pd.DataFrame) -> pd.DataFrame:
    """加购未购买用户池 + 历史真实结局。"""
    pre = df[df["behavior_time"] <= CUTOFF]
    post = df[df["behavior_time"] > CUTOFF]

    carted_users = set(pre.loc[pre["behavior_type"] == "cart", "user_id"])
    bought_users = set(pre.loc[pre["behavior_type"] == "buy", "user_id"])
    pool_users = carted_users - bought_users

    post_buyers = set(post.loc[post["behavior_type"] == "buy", "user_id"])
    pool = pd.DataFrame({"user_id": sorted(pool_users)})
    pool["observed_converted"] = pool["user_id"].isin(post_buyers).astype(int)
    return pool


# ---------- 样本量与 MDE ----------
def required_n_per_arm(p0: float, delta: float,
                       alpha_z: float = Z_ALPHA, beta_z: float = Z_BETA) -> int:
    """双比例检验每组所需样本量（不考虑不依从的简化公式）。"""
    p1 = p0 + delta
    var = p0 * (1 - p0) + p1 * (1 - p1)
    return int(np.ceil((alpha_z + beta_z) ** 2 * var / delta**2))


def mde(p0: float, n_per_arm: int,
        alpha_z: float = Z_ALPHA, beta_z: float = Z_BETA) -> float:
    """给定每组样本量，数值求解可检测的最小绝对提升。"""
    lo, hi = 1e-4, 0.5
    for _ in range(60):
        mid = (lo + hi) / 2
        if required_n_per_arm(p0, mid, alpha_z, beta_z) <= n_per_arm:
            hi = mid
        else:
            lo = mid
    return round((lo + hi) / 2, 5)


# ---------- 主入口 ----------
def main() -> None:
    df = pd.read_csv(DATA_FILE, parse_dates=["timestamp"])
    df["behavior_time"] = df["timestamp"]
    print(f"数据：{len(df):,} 行，{df['user_id'].nunique():,} 用户")

    pool = build_experiment_pool(df)
    p0 = pool["observed_converted"].mean()
    n_total = len(pool)
    n_per_arm = n_total // 2

    print(f"\n实验总体（加购未购买）：{n_total:,} 人")
    print(f"历史基线转化率 p0（12-02~03 购买）：{p0:.4f}")

    print("\n—— 实验设计速查（α=0.05，power=0.8，双尾）——")
    rows = []
    for delta in (0.01, 0.02, 0.03, 0.05):
        rows.append({
            "mde_abs": delta,
            "required_n_per_arm": required_n_per_arm(p0, delta),
            "feasible_with_pool": required_n_per_arm(p0, delta) <= n_per_arm,
        })
    design = pd.DataFrame(rows)
    print(design.to_string(index=False))

    print(f"\n现有总体（每组 {n_per_arm:,} 人）能检测的最小效应："
          f"MDE = {mde(p0, n_per_arm):.4f}（绝对提升）")
    print(f"等价于相对提升 {mde(p0, n_per_arm) / p0:.1%}")

    out = Path(__file__).resolve().parent / "reports"
    out.mkdir(exist_ok=True)
    pd.DataFrame([{
        "pool_users": n_total, "baseline_p0": round(p0, 4),
        "mde_abs_pool": mde(p0, n_per_arm),
        "mde_relative": round(mde(p0, n_per_arm) / p0, 4),
    }]).to_csv(out / "ab_design_summary.csv", index=False, encoding="utf-8-sig")
    print(f"\n✅ 设计摘要已保存：{out / 'ab_design_summary.csv'}")


if __name__ == "__main__":
    main()

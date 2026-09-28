"""A/B 测试框架 —— 模拟实验执行与分析。

流程（对每组模拟注入效应 δ，再做分析端检验）：
1. 随机分组 50/50（固定种子），样本比例一致性检查（SRM）
2. 效应注入：处理组非转化用户以 δ/(1-p0) 的概率翻转为转化，
   使期望提升恰为 δ（历史结局本身不含干预，只能模拟注入）
3. 分析端：两比例 z 检验 + 差值 95% CI（分析端不知道 δ 是多少）
4. 校准实验：
   - δ=0（AA 实验）× 200 次 → 假阳性率应接近 5%
   - δ>0 各档 × 200 次 → 检验功效（检出率）与 CI 覆盖率

⚠️ 基于历史数据的模拟实验，非真实在线实验。
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from ab_design import build_experiment_pool, DATA_FILE

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei"]
plt.rcParams["axes.unicode_minus"] = False

REPORTS = Path(__file__).resolve().parent / "reports"
N_SIMS = 200
SCENARIOS = [0.0, 0.01, 0.02, 0.05]  # δ=0 即 AA 实验


def two_proportion_z_test(success_a: int, n_a: int,
                          success_b: int, n_b: int) -> dict:
    p_a, p_b = success_a / n_a, success_b / n_b
    p_pool = (success_a + success_b) / (n_a + n_b)
    se = np.sqrt(p_pool * (1 - p_pool) * (1 / n_a + 1 / n_b))
    z = (p_a - p_b) / se
    p_value = 2 * (1 - _norm_cdf(abs(z)))
    se_diff = np.sqrt(p_a * (1 - p_a) / n_a + p_b * (1 - p_b) / n_b)
    return {
        "diff": p_a - p_b,
        "ci_low": p_a - p_b - 1.96 * se_diff,
        "ci_high": p_a - p_b + 1.96 * se_diff,
        "z": z,
        "p_value": p_value,
    }


def _norm_cdf(x: float) -> float:
    from math import erf, sqrt
    return 0.5 * (1 + erf(x / sqrt(2)))


def srm_check(n_a: int, n_b: int) -> dict:
    """样本比例一致性检查：50/50 分组是否被破坏。"""
    n = n_a + n_b
    z = (n_a - n / 2) / np.sqrt(n / 4)
    p_value = 2 * (1 - _norm_cdf(abs(z)))
    return {"n_treatment": n_a, "n_control": n_b, "srm_z": round(z, 3),
            "srm_p": round(p_value, 4), "srm_ok": bool(p_value > 0.001)}


def inject_effect(outcomes: np.ndarray, treated_mask: np.ndarray,
                  delta: float, p0: float, rng: np.random.Generator) -> np.ndarray:
    """对处理组注入绝对提升 δ（期望意义下）。"""
    sim = outcomes.copy()
    flip_prob = delta / (1 - p0)
    candidates = treated_mask & (sim == 0)
    flips = rng.random(candidates.sum()) < flip_prob
    sim[np.where(candidates)[0][flips]] = 1
    return sim


def run_scenario(outcomes: np.ndarray, delta: float,
                 rng: np.random.Generator) -> list[dict]:
    n = len(outcomes)
    treated_mask = rng.random(n) < 0.5
    p0 = outcomes.mean()
    sim = inject_effect(outcomes, treated_mask, delta, p0, rng)

    t_idx, c_idx = treated_mask, ~treated_mask
    srm = srm_check(int(t_idx.sum()), int(c_idx.sum()))
    test = two_proportion_z_test(int(sim[t_idx].sum()), int(t_idx.sum()),
                                 int(sim[c_idx].sum()), int(c_idx.sum()))
    return {**srm, **{k: test[k] for k in ("diff", "ci_low", "ci_high", "z", "p_value")},
            "delta_true": delta}


def main() -> None:
    df = pd.read_csv(DATA_FILE, parse_dates=["timestamp"])
    df["behavior_time"] = df["timestamp"]
    pool = build_experiment_pool(df)
    outcomes = pool["observed_converted"].to_numpy()
    p0 = outcomes.mean()
    print(f"实验总体 {len(outcomes):,} 人，基线 p0={p0:.4f}")

    # —— 单次代表性实验 ——
    rng = np.random.default_rng(42)
    rep = run_scenario(outcomes, delta=0.02, rng=rng)
    print("\n—— 代表性实验（真实注入 δ=+2pp）——")
    print(f"SRM: {rep['srm_ok']}（z={rep['srm_z']}, p={rep['srm_p']}）")
    print(f"分析端结论：估计提升 {rep['diff']:+.4f}，"
          f"95% CI [{rep['ci_low']:+.4f}, {rep['ci_high']:+.4f}]，"
          f"p={rep['p_value']:.2e} → "
          f"{'显著，拒绝 H0' if rep['p_value'] < 0.05 else '不显著'}")

    # —— 校准实验：AA 假阳性率 + 各档功效 ——
    rng = np.random.default_rng(7)
    rows = []
    for delta in SCENARIOS:
        results = [run_scenario(outcomes, delta, rng) for _ in range(N_SIMS)]
        df_sim = pd.DataFrame(results)
        rows.append({
            "delta_true": delta,
            "detection_rate": (df_sim["p_value"] < 0.05).mean(),
            "avg_diff": df_sim["diff"].mean(),
            "ci_coverage": ((df_sim["ci_low"] <= delta) &
                            (df_sim["ci_high"] >= delta)).mean(),
            "avg_p": df_sim["p_value"].mean(),
        })
    summary = pd.DataFrame(rows)
    print(f"\n—— {N_SIMS} 次模拟校准 ——")
    print(summary.round(4).to_string(index=False))
    print("\n解读：δ=0 行是 AA 实验，detection_rate 即假阳性率（应≈5%）；")
    print("δ>0 行的 detection_rate 即统计功效；ci_coverage 应接近 95%。")

    REPORTS.mkdir(exist_ok=True)
    summary.to_csv(REPORTS / "ab_sim_summary.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame([rep]).to_csv(REPORTS / "ab_representative_run.csv",
                               index=False, encoding="utf-8-sig")
    print(f"\n✅ 已保存：{REPORTS / 'ab_sim_summary.csv'}")

    # —— 校准图：检出率（含假阳性线）与 CI 覆盖率 ——
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.5))
    axes[0].bar(summary["delta_true"].astype(str), summary["detection_rate"],
                color=["#999999", "#4C9BE8", "#2CA02C", "#E94E4E"])
    axes[0].axhline(0.05, color="k", linestyle="--", linewidth=1)
    axes[0].text(3.1, 0.05, "5% 假阳性线", fontsize=9, va="bottom", ha="right")
    axes[0].set_title(f"检出率（{N_SIMS} 次模拟，δ=0 行为假阳性率）",
                      fontsize=13, fontweight="bold")
    axes[0].set_xlabel("注入的真实提升 δ（绝对 pp）")
    axes[0].set_ylabel("检出率（p<0.05 比例）")
    axes[0].set_ylim(0, 1.05)

    axes[1].bar(summary["delta_true"].astype(str), summary["ci_coverage"],
                color="#7B68EE")
    axes[1].axhline(0.95, color="k", linestyle="--", linewidth=1)
    axes[1].set_title("95% CI 对真实 δ 的覆盖率（应≈95%）",
                      fontsize=13, fontweight="bold")
    axes[1].set_xlabel("注入的真实提升 δ（绝对 pp）")
    axes[1].set_ylabel("覆盖率")
    axes[1].set_ylim(0, 1.05)

    fig.suptitle("A/B 测试框架校准（历史数据模拟）", fontsize=15,
                 fontweight="bold", y=1.02)
    plt.tight_layout()
    plt.savefig(REPORTS / "ab_calibration.png", dpi=150, bbox_inches="tight")
    plt.close()
    print(f"✅ 图表已保存：{REPORTS / 'ab_calibration.png'}")


if __name__ == "__main__":
    main()

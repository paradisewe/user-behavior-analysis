"""关联规则挖掘（类目级购物篮分析）。

对应 plan.md 深化方向 #5。技术红线（见 plan.md）：
1. 按 category_id（类目）聚合购物篮——商品 ID 脱敏无业务含义，且商品级数据
   极稀疏，min_support=0.01 的商品级 Apriori 一条规则都挖不出来
2. 不用 TransactionEncoder 稠密 one-hot（几十万购物篮 × 400 万商品会 OOM）。
   这里直接对购物篮做 2-项集精确计数——结果与 FP-Growth 的 2-项集完全一致，
   无需稠密矩阵，也不依赖 mlxtend
3. 购物篮先按类目去重

指标口径（basket = 用户窗口内购买过的去重类目集合）：
    support(A→B)   = 同时含 A、B 的购物篮数 / 总购物篮数
    confidence(A→B) = 同时含 A、B 的购物篮数 / 含 A 的购物篮数
    lift(A→B)      = confidence(A→B) / P(B)

输入：cleaned_stratified_data.csv
输出：reports/association_rules.csv + reports/figures/association_*.png
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from itertools import combinations
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


# ---------- 购物篮构建 ----------
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


# ---------- 2-项集精确挖掘 ----------
def mine_rules(baskets: list[frozenset], min_support: float,
               min_confidence: float, min_lift: float,
               top_n: int) -> pd.DataFrame:
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


# ---------- 可视化 ----------
def plot_support_confidence(rules: pd.DataFrame, fig_dir: Path):
    fig, ax = plt.subplots(figsize=(9, 6))
    sc = ax.scatter(rules["support"] * 100, rules["confidence"] * 100,
                    s=np.clip(rules["lift"], 1, None) * 12,
                    c=rules["lift"], cmap="viridis", alpha=0.7, edgecolors="k",
                    linewidths=0.3)
    fig.colorbar(sc, ax=ax, label="提升度 lift")
    ax.set_xlabel("支持度（%）")
    ax.set_ylabel("置信度（%）")
    ax.set_title("类目级关联规则：支持度 × 置信度（气泡大小=提升度）")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(fig_dir / "association_scatter.png", dpi=150)
    plt.close(fig)


def plot_top_rules(rules: pd.DataFrame, fig_dir: Path, top_n: int = 15):
    top = rules.head(top_n).iloc[::-1]
    labels = [
        f"{int(r.antecedent_category)} → {int(r.consequent_category)}"
        for r in top.itertuples()
    ]
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.barh(labels, top["lift"], color="#2b7bba")
    for i, (lift, conf) in enumerate(zip(top["lift"], top["confidence"])):
        ax.text(lift, i, f"  lift={lift:.1f}, conf={conf:.1%}", va="center", fontsize=8)
    ax.set_xlabel("提升度 lift")
    ax.set_title(f"Top {top_n} 类目关联规则（按提升度）")
    fig.tight_layout()
    fig.savefig(fig_dir / "association_top_rules.png", dpi=150)
    plt.close(fig)


# ---------- 主入口 ----------
def main() -> None:
    parser = argparse.ArgumentParser(description="类目级关联规则挖掘（购物篮分析）")
    parser.add_argument("--input", type=Path, default=None, help="Cleaned CSV path.")
    parser.add_argument("--min-support", type=float, default=0.0005,
                        help="最小支持度（默认 5e-4；0.01 在本数据集上一条规则都没有）")
    parser.add_argument("--min-confidence", type=float, default=0.10)
    parser.add_argument("--min-lift", type=float, default=1.0)
    parser.add_argument("--top-n", type=int, default=100)
    args = parser.parse_args()

    df = load_data(args.input) if args.input else load_data()

    baskets = build_baskets(df)
    print(f"\n阈值：support>={args.min_support}, confidence>={args.min_confidence}, "
          f"lift>{args.min_lift}")
    rules = mine_rules(baskets, args.min_support, args.min_confidence,
                       args.min_lift, args.top_n)

    print(f"\n===== 关联规则（Top {len(rules)}，按提升度）=====")
    if rules.empty:
        print("未挖掘到规则，请降低阈值后重试。")
        return
    print(rules.head(20).to_string(index=False))

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    out_path = REPORTS_DIR / "association_rules.csv"
    rules.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"\n✅ 结果已保存：{out_path}")

    plot_support_confidence(rules, FIG_DIR)
    plot_top_rules(rules, FIG_DIR)
    print(f"✅ 图表已保存：{FIG_DIR / 'association_scatter.png'}")
    print(f"✅ 图表已保存：{FIG_DIR / 'association_top_rules.png'}")


if __name__ == "__main__":
    main()

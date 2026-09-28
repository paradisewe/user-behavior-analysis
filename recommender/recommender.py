"""轻量商品推荐原型 —— 类目级协同过滤 + 时间切分离线评估。

plan.md 深化方向 #9 的**轻量版**（该方向原定为低优先级）。

方法：
- 粒度：类目级（商品 ID 脱敏无业务含义，且类目共现矩阵小、可解释）
- 协同过滤：基于用户购买篮内类目共现的 item-based CF，
  候选打分 = Σ_{c∈用户历史} lift(c → 候选类目)（lift 来自训练期的 2-项集挖掘）
- 基线：热门推荐（训练期购买用户数 Top 类目）

评估（时间切分，模拟真实上线场景）：
- 训练期：2017-11-25 ~ 12-01；测试期：12-02 ~ 12-03
- 对测试期发生「新类目购买」（测试期购买的类目 ∉ 训练期历史）的用户，
  推荐列表命中其测试期新类目的比例
- 指标：Precision@10、Recall@10、类目覆盖率

⚠️ 9 天窗口 + 5% 抽样数据的局限：共现信号稀疏，绝对值不高，
重点是 CF vs 热门基线的相对比较与评估方法论。
"""

from __future__ import annotations

from collections import Counter
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei"]
plt.rcParams["axes.unicode_minus"] = False

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_FILE = REPO_ROOT / "python" / "data" / "cleaned_stratified_data.csv"
REPORTS = Path(__file__).resolve().parent / "reports"

SPLIT = pd.Timestamp("2017-12-01 23:59:59")
TOP_K = 10


# ---------- 训练期：类目共现 lift ----------
def build_cooccurrence(train_buys: pd.DataFrame, min_pair_count: int = 3
                       ) -> tuple[dict, dict, int]:
    """返回 (lift[(a,b)] 字典, 类目流行度字典, 购物篮数)。

    min_pair_count：共现对至少出现在多少个购物篮才保留——
    过滤长尾高 lift 的偶然共现（9 天数据共现信号极稀疏）。
    """
    baskets = (
        train_buys.groupby("user_id")["category_id"]
        .apply(lambda s: frozenset(s.unique()))
    )
    baskets = [b for b in baskets if len(b) >= 2]

    item_count = Counter()
    pair_count = Counter()
    for basket in baskets:
        item_count.update(basket)
        pair_count.update(combinations(sorted(basket), 2))
    n_baskets = len(baskets)

    lift = {}
    for (a, b), both in pair_count.items():
        if both < min_pair_count:
            continue
        lift[(a, b)] = (both / n_baskets) / (
            (item_count[a] / n_baskets) * (item_count[b] / n_baskets)
        )
    return lift, dict(item_count), n_baskets


def sym_lift(lift: dict, a, b) -> float:
    return lift.get((a, b), lift.get((b, a), 0.0))


# ---------- 推荐器 ----------
def recommend_cf(history: frozenset, lift: dict, k: int = TOP_K) -> list:
    """item-based CF：候选分 = Σ lift(历史类目 → 候选)。"""
    scores = Counter()
    for cat in history:
        for (a, b), value in lift.items():
            other = b if a == cat else (a if b == cat else None)
            if other is not None and other not in history:
                scores[other] += value
    return [c for c, _ in scores.most_common(k)]


def recommend_popular(popularity: Counter, history: frozenset, k: int = TOP_K) -> list:
    return [c for c, _ in popularity.most_common() if c not in history][:k]


def recommend_cf_with_fallback(history: frozenset, lift: dict,
                               popularity: Counter, k: int = TOP_K) -> list:
    """CF 打分 + 热门补齐：CF 候选不足 K 个时用热门类目填充。"""
    recs = recommend_cf(history, lift, k)
    if len(recs) < k:
        recs += recommend_popular(popularity, history | set(recs), k - len(recs))
    return recs[:k]


# ---------- 评估 ----------
def evaluate(test_users: dict, lift: dict, popularity: Counter,
             k: int = TOP_K) -> pd.DataFrame:
    """test_users: {user_id: 训练期历史 frozenset, ...} 附测试期新类目。"""
    rows = []
    for user_id, (history, new_cats) in test_users.items():
        if not new_cats:
            continue
        rec_cf = set(recommend_cf_with_fallback(history, lift, popularity, k))
        rec_pop = set(recommend_popular(popularity, history, k))
        rows.append({
            "user_id": user_id,
            "n_new_cats": len(new_cats),
            "cf_precision": len(rec_cf & new_cats) / k,
            "cf_recall": len(rec_cf & new_cats) / len(new_cats),
            "pop_precision": len(rec_pop & new_cats) / k,
            "pop_recall": len(rec_pop & new_cats) / len(new_cats),
        })
    detail = pd.DataFrame(rows)
    summary = detail[["cf_precision", "cf_recall", "pop_precision", "pop_recall"]].mean()
    return summary, detail


# ---------- 主入口 ----------
def main() -> None:
    df = pd.read_csv(DATA_FILE, parse_dates=["timestamp"])
    df["behavior_time"] = df["timestamp"]
    buys = df[df["behavior_type"] == "buy"]
    train_buys = buys[buys["behavior_time"] <= SPLIT]
    test_buys = buys[buys["behavior_time"] > SPLIT]
    print(f"训练期购买 {len(train_buys):,} 条 / 测试期购买 {len(test_buys):,} 条")

    print("挖掘训练期类目共现 lift……")
    lift, item_count, n_baskets = build_cooccurrence(train_buys)
    print(f"有效购物篮 {n_baskets:,}，类目对 {len(lift):,} 个")
    popularity = Counter(
        train_buys.groupby("user_id")["category_id"].apply(lambda s: frozenset(s.unique())).explode()
    )

    # 每个用户的训练期历史与测试期新类目
    train_history = train_buys.groupby("user_id")["category_id"].apply(lambda s: frozenset(s.unique()))
    test_new = test_buys.groupby("user_id")["category_id"].apply(
        lambda s: frozenset(s.unique()) - train_history.get(s.name, frozenset())
    )
    eval_users = {
        u: (train_history[u], new_cats)
        for u, new_cats in test_new.items()
        if len(new_cats) > 0 and u in train_history.index  # 排除测试期冷启动新用户
    }
    n_cold = sum(1 for u, cats in test_new.items()
                 if len(cats) > 0 and u not in train_history.index)
    print(f"评估用户（测试期有新类目购买且有训练期历史）：{len(eval_users):,}"
          f"（另排除冷启动新用户 {n_cold:,} 人，CF 无法为其生成历史）")

    summary, detail = evaluate(eval_users, lift, popularity)
    print("\n===== 离线评估（Top-10 推荐）=====")
    print(summary.round(4).to_string())
    print("\n解读：CF 的 Precision/Recall 相对热门基线的倍数 "
          f"= {summary['cf_precision'] / max(summary['pop_precision'], 1e-9):.2f}x")

    # 展示一个推荐示例
    sample_user = max(eval_users, key=lambda u: len(eval_users[u][1]))
    history, new_cats = eval_users[sample_user]
    recs = [int(c) for c in recommend_cf_with_fallback(history, lift, popularity)]
    print(f"\n示例用户 {sample_user}：历史类目 {[int(c) for c in sorted(history)]}")
    print(f"CF+热门补齐 Top-10：{recs}")
    print(f"测试期实际购买的新类目：{[int(c) for c in sorted(new_cats)]}")

    REPORTS.mkdir(exist_ok=True)
    summary.to_frame("value").to_csv(REPORTS / "recommender_eval.csv", encoding="utf-8-sig")
    detail.to_csv(REPORTS / "recommender_eval_detail.csv", index=False, encoding="utf-8-sig")

    fig, ax = plt.subplots(figsize=(8, 5))
    x = np.arange(2)
    ax.bar(x - 0.18, [summary["cf_precision"], summary["cf_recall"]] , 0.36,
           label="类目协同过滤", color="#4C9BE8")
    ax.bar(x + 0.18, [summary["pop_precision"], summary["pop_recall"]], 0.36,
           label="热门推荐基线", color="#F5A623")
    ax.set_xticks(x, ["Precision@10", "Recall@10"])
    ax.set_title("推荐原型离线评估：CF vs 热门基线", fontsize=14, fontweight="bold")
    for i, v in enumerate([summary["cf_precision"], summary["cf_recall"]]):
        ax.text(i - 0.18, v, f"{v:.3f}", ha="center", va="bottom", fontsize=10)
    for i, v in enumerate([summary["pop_precision"], summary["pop_recall"]]):
        ax.text(i + 0.18, v, f"{v:.3f}", ha="center", va="bottom", fontsize=10)
    ax.legend()
    plt.tight_layout()
    plt.savefig(REPORTS / "recommender_eval.png", dpi=150)
    plt.close()
    print(f"\n✅ 已保存：{REPORTS / 'recommender_eval.csv'}、recommender_eval.png")


if __name__ == "__main__":
    main()

"""用户路径分析：pv → fav/cart → buy 的流转路径 + 桑基图。

对应 plan.md 深化方向 #2。口径为「用户-商品级」（与现有漏斗分析一致）：
对每个 (user_id, item_id) 对，若首个行为是 pv，则按各行为的首次发生时间
归类路径（同一行为首次时间并列时按 pv < fav < cart < buy 的次序打破平局）：

    浏览 ──> 直接购买（buy 之前无 fav/cart）        ──> 购买
    浏览 ──> 先加购（cart 早于 fav 与 buy）         ──> 购买 / 未购买
    浏览 ──> 先收藏（fav 早于 cart 与 buy）         ──> 购买 / 未购买
    浏览 ──> 仅浏览（无后续行为）                    ──> 未购买

输出关键比例：「浏览后直接购买」vs「浏览后加购再购买」vs「浏览后收藏再购买」。

输入：cleaned_stratified_data.csv
输出：reports/path_summary.csv + reports/figures/path_sankey.html（交互式）
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from analysis import load_data
from config import FIG_DIR, REPORTS_DIR

BEHAVIOR_ORDER = {"pv": 0, "fav": 1, "cart": 2, "buy": 3}


# ---------- 路径归类 ----------
def classify_paths(df: pd.DataFrame) -> pd.DataFrame:
    """对每个用户-商品对归类主路径，返回带 path 列的 pair 级表。"""
    events = df[df["behavior_type"].isin(["pv", "fav", "cart", "buy"])].copy()

    # 同一 (user,item,behavior) 多条记录取首次；时间并列时按 pv<fav<cart<buy 次序
    tie_break = events["behavior_type"].map(BEHAVIOR_ORDER).astype(float) / 1e6
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

    # 结果列：直接购买/先加购/先收藏 → 是否最终购买
    pairs["outcome"] = "未购买"
    pairs.loc[pairs["buy"].notna(), "outcome"] = "购买"
    pairs.loc[pairs["path"] == "仅浏览", "outcome"] = "未购买"
    return pairs[["user_id", "item_id", "path", "outcome"]]


def path_summary(pairs: pd.DataFrame) -> pd.DataFrame:
    n = len(pairs)
    summary = pairs.groupby("path").agg(
        pairs=("item_id", "size"),
        purchased=("outcome", lambda s: (s == "购买").sum()),
    ).reset_index()
    summary["share_of_browsed"] = (summary["pairs"] / n).round(4)
    summary["purchase_rate"] = (summary["purchased"] / summary["pairs"]).round(4)
    return summary.sort_values("pairs", ascending=False).reset_index(drop=True)


# ---------- 桑基图 ----------
def plot_sankey(pairs: pd.DataFrame, fig_dir: Path):
    import plotly.graph_objects as go

    n = len(pairs)
    stage2 = pairs.groupby("path").size()
    stage2_to_outcome = pairs.groupby(["path", "outcome"]).size()

    labels = ["浏览 (pv)", *stage2.index.tolist(), "购买", "未购买"]
    node_index = {name: i for i, name in enumerate(labels)}
    colors = ["#636efa", "#ef553b", "#00cc96", "#ab63fa", "#ffa15a", "#2ca02c", "#7f7f7f"]

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
    out = fig_dir / "path_sankey.html"
    fig.write_html(str(out))
    return out


# ---------- 主入口 ----------
def main() -> None:
    parser = argparse.ArgumentParser(description="用户路径分析（用户-商品级三段桑基图）")
    parser.add_argument("--input", type=Path, default=None, help="Cleaned CSV path.")
    args = parser.parse_args()

    df = load_data(args.input) if args.input else load_data()

    print("\n正在归类用户-商品级路径……")
    pairs = classify_paths(df)
    summary = path_summary(pairs)

    print("\n===== 路径汇总 =====")
    print(summary.to_string(index=False))

    direct = summary.loc[summary["path"] == "直接购买", "share_of_browsed"].iloc[0]
    via_cart = summary.loc[summary["path"] == "先加购", "share_of_browsed"].iloc[0]
    via_fav = summary.loc[summary["path"] == "先收藏", "share_of_browsed"].iloc[0]
    print(f"\n浏览后直接购买：{direct:.2%}，浏览后加购（再购买或未买）：{via_cart:.2%}，"
          f"浏览后收藏：{via_fav:.2%}")

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    out_path = REPORTS_DIR / "path_summary.csv"
    summary.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"\n✅ 结果已保存：{out_path}")

    sankey_path = plot_sankey(pairs, FIG_DIR)
    print(f"✅ 交互式桑基图已保存：{sankey_path}")


if __name__ == "__main__":
    main()

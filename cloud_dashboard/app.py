"""淘宝用户行为分析 Dashboard —— 云部署版（Streamlit Community Cloud）。

与本地版（python/dashboard/app.py）的区别：
- 数据来自预聚合的 data/cloud_data.json（68KB，无任何用户/商品明细），
  不需要 222MB 清洗 CSV，也不依赖 src/ 分析代码
- 转化漏斗、用户分层、类目 TOP10 为全窗口静态口径；
  行为分布 / 用户趋势 / 小时分布支持日期与行为类型筛选（聚合粒度精确）

本地预览：
    streamlit run cloud_dashboard/app.py

云端部署：见 cloud_dashboard/README.md（推送到 GitHub 后在
share.streamlit.io 选择本仓库的本分支与本文件即可）。
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

DATA_FILE = Path(__file__).resolve().parent / "data" / "cloud_data.json"

COLORS = {"pv": "#4C9BE8", "cart": "#7B68EE", "fav": "#F5A623", "buy": "#E94E4E"}
ALL_BEHAVIORS = ["pv", "cart", "fav", "buy"]

st.set_page_config(
    page_title="淘宝用户行为分析",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================
# 数据加载（缓存）
# ============================================================
@st.cache_data(show_spinner="加载预聚合数据中……")
def load_payload() -> dict:
    return json.loads(DATA_FILE.read_text(encoding="utf-8"))


def to_frames(payload: dict):
    daily_behavior = pd.DataFrame(payload["daily_behavior"])
    daily_users = pd.DataFrame(payload["daily_users"])
    hourly = pd.DataFrame(payload["hourly_behavior"])
    daily_users["date"] = pd.to_datetime(daily_users["date"])
    daily_behavior["date"] = pd.to_datetime(daily_behavior["date"])
    hourly["date"] = pd.to_datetime(hourly["date"])
    return daily_behavior, daily_users, hourly


# ============================================================
# 筛选器
# ============================================================
def render_filters(daily_behavior: pd.DataFrame):
    st.sidebar.markdown("## 🔍 筛选器")
    dates = sorted(daily_behavior["date"].unique())
    date_range = st.sidebar.date_input(
        "日期范围",
        value=(dates[0], dates[-1]),
        min_value=dates[0],
        max_value=dates[-1],
    )
    behaviors = st.sidebar.multiselect(
        "行为类型", options=ALL_BEHAVIORS, default=ALL_BEHAVIORS
    )

    st.sidebar.markdown("---")
    meta = load_payload()["meta"]
    st.sidebar.markdown(
        f"""
        **数据说明**
- {meta["sampling"]}
- 数据窗口：{meta["window"]}
- {meta["validation"]}
- {meta["privacy"]}
        """
    )

    start, end = (date_range if isinstance(date_range, tuple) else (dates[0], dates[-1]))[:2]
    return start, end, behaviors


# ============================================================
# KPI
# ============================================================
def render_kpis(summary: dict, filtered: pd.DataFrame, daily_users: pd.DataFrame):
    in_range = daily_users[
        (daily_users["date"] >= filtered["date"].min())
        & (daily_users["date"] <= filtered["date"].max())
    ]
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("行为数（筛选后）", f"{int(filtered['count'].sum()):,}")
    col2.metric("独立用户数（全窗口）", f"{summary['uv']:,}")
    col3.metric("日均 DAU（筛选范围）", f"{int(in_range['dau'].mean()):,}" if len(in_range) else "—")
    col4.metric("商品数（全窗口）", f"{summary['item_count']:,}")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("复购率（全窗口）", f"{summary['repurchase_rate']:.2%}")
    col2.metric("购买用户数（全窗口）", f"{summary['total_buyers']:,}")
    col3.metric("浏览→购买转化率", f"{summary['pv_to_buy_rate']:.2%}"
                if "pv_to_buy_rate" in summary else "—")
    col4.metric("类目数（全窗口）", f"{summary['category_count']:,}")
    st.caption("带「全窗口」标注的指标不随筛选变化（预聚合口径，见侧栏说明）")


# ============================================================
# Tabs
# ============================================================
def tab_behavior(filtered: pd.DataFrame):
    dist = filtered.groupby("behavior_type")["count"].sum().reset_index()
    dist = dist.set_index("behavior_type").reindex(ALL_BEHAVIORS, fill_value=0).reset_index()
    total = dist["count"].sum()

    col1, col2 = st.columns(2)
    with col1:
        fig = px.pie(
            dist, values="count", names="behavior_type",
            color="behavior_type", color_discrete_map=COLORS,
            title="行为类型占比", hole=0.4,
        )
        fig.update_traces(textposition="inside", textinfo="percent+label")
        fig.update_layout(height=400)
        st.plotly_chart(fig, use_container_width=True)
    with col2:
        fig = px.bar(
            dist, x="behavior_type", y="count",
            color="behavior_type", color_discrete_map=COLORS,
            title="行为类型绝对量",
        )
        fig.update_traces(texttemplate="%{y:,}", textposition="outside")
        fig.update_layout(height=400, showlegend=False, yaxis_title="行为数")
        st.plotly_chart(fig, use_container_width=True)
    st.caption(f"筛选范围内共 {total:,} 条行为")


def tab_funnel(payload: dict):
    f = payload["funnel"]
    fig = go.Figure(go.Funnel(
        y=["浏览 (pv)", "加购 (cart)", "购买 (buy)"],
        x=[f["viewed_pairs"], f["pv_to_cart_pairs"], f["pv_to_buy_pairs"]],
        textinfo="value+percent initial",
        marker={"color": ["#4C9BE8", "#7B68EE", "#E94E4E"]},
        connector={"line": {"color": "#ccc"}},
    ))
    fig.update_layout(title="用户-商品级漏斗", height=420)
    st.plotly_chart(fig, use_container_width=True)

    col1, col2, col3 = st.columns(3)
    col1.metric("pv→cart", f"{f['pv_to_cart_rate']:.2%}")
    col2.metric("pv→buy", f"{f['pv_to_buy_rate']:.2%}")
    col3.metric("cart→buy", f"{f['cart_to_buy_rate']:.2%}")
    st.caption("用户-商品级口径（同一用户同一商品的先后行为），反映真实转化效率；全窗口静态口径")


def tab_trend(filtered: pd.DataFrame, daily_users: pd.DataFrame):
    daily = filtered.pivot_table(index="date", columns="behavior_type",
                                 values="count", fill_value=0)
    for b in ALL_BEHAVIORS:
        if b not in daily.columns:
            daily[b] = 0
    trend = daily_users.merge(daily.reset_index(), on="date", how="left").fillna(0)

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=trend["date"], y=trend["dau"], mode="lines+markers",
                             name="DAU", line={"color": "#4C9BE8", "width": 2.5}))
    fig.add_trace(go.Scatter(x=trend["date"], y=trend["purchase_users"],
                             mode="lines+markers", name="购买用户数",
                             line={"color": "#7B68EE", "width": 2.5, "dash": "dash"},
                             yaxis="y2"))
    fig.add_trace(go.Scatter(x=trend["date"], y=trend["buy"], mode="lines+markers",
                             name="购买行为数",
                             line={"color": "#E94E4E", "width": 2.5, "dash": "dot"},
                             yaxis="y2"))
    fig.update_layout(
        title="用户趋势：DAU · 购买用户 · 购买行为",
        xaxis={"title": "日期"},
        yaxis={"title": "DAU"},
        yaxis2={"title": "购买", "overlaying": "y", "side": "right"},
        height=480, hovermode="x unified",
    )
    st.plotly_chart(fig, use_container_width=True)


def tab_hourly(filtered: pd.DataFrame):
    pivot = filtered.pivot_table(index="date", columns="hour", values="count",
                                 fill_value=0)
    fig = px.imshow(
        pivot,
        labels={"x": "小时", "y": "日期", "color": "行为数"},
        color_continuous_scale="YlOrRd", aspect="auto",
        title="日期 × 小时 行为热力图",
    )
    fig.update_layout(height=380)
    st.plotly_chart(fig, use_container_width=True)

    by_hour = filtered.groupby("hour")["count"].sum().reset_index()
    fig2 = px.bar(by_hour, x="hour", y="count", title="24 小时行为总量（筛选范围）")
    fig2.update_layout(height=350, xaxis={"dtick": 1}, showlegend=False,
                       yaxis_title="行为数")
    st.plotly_chart(fig2, use_container_width=True)


def tab_static(payload: dict):
    col1, col2 = st.columns(2)

    with col1:
        seg = pd.DataFrame(payload["segmentation"])
        pivot = seg.pivot_table(index="behavior_depth", columns="purchase_segment",
                                values="users", fill_value=0)
        fig = px.bar(
            pivot, barmode="stack", title="用户行为深度 × 购买分段",
            labels={"value": "用户数", "behavior_depth": "行为深度",
                    "purchase_segment": "购买分段"},
        )
        fig.update_layout(height=440)
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        top = pd.DataFrame(payload["top_categories"]).sort_values("purchase_count")
        fig = px.bar(
            top, x="purchase_count", y=top["category_id"].astype(str),
            orientation="h", title="购买量 TOP10 类目",
            labels={"x": "购买次数", "y": "类目 ID"},
            color_discrete_sequence=["#E94E4E"],
        )
        fig.update_traces(texttemplate="%{x:,}", textposition="outside")
        fig.update_layout(height=440, showlegend=False)
        st.plotly_chart(fig, use_container_width=True)

    st.caption("本页为全窗口静态口径，不随侧栏筛选变化")


# ============================================================
# 主入口
# ============================================================
def main():
    st.title("📊 淘宝用户行为分析 Dashboard")
    st.caption(
        "基于阿里天池「淘宝用户行为数据集」· 用户级分层等比例抽样 5% · "
        "DuckDB 全量交叉验证差异 < 0.1% · 云端版加载预聚合数据（无明细）"
    )

    payload = load_payload()
    daily_behavior, daily_users, hourly = to_frames(payload)

    start, end, behaviors = render_filters(daily_behavior)

    fb = daily_behavior[
        (daily_behavior["date"] >= pd.Timestamp(start))
        & (daily_behavior["date"] <= pd.Timestamp(end))
        & (daily_behavior["behavior_type"].isin(behaviors))
    ]
    fh = hourly[
        (hourly["date"] >= pd.Timestamp(start))
        & (hourly["date"] <= pd.Timestamp(end))
        & (hourly["behavior_type"].isin(behaviors))
    ]

    if fb.empty:
        st.warning("筛选后无数据，请调整筛选条件。")
        return

    st.info(
        f"当前筛选：{start} ~ {end} ｜ 行为类型：{', '.join(behaviors)} ｜ "
        f"{int(fb['count'].sum()):,} 条行为"
    )

    render_kpis(payload["summary"], fb, daily_users)
    st.markdown("---")

    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📊 行为分布", "🔻 转化漏斗", "📈 用户趋势", "⏰ 时间分布", "👥 分层与类目"
    ])
    with tab1:
        tab_behavior(fb)
    with tab2:
        tab_funnel(payload)
    with tab3:
        tab_trend(fb, daily_users)
    with tab4:
        tab_hourly(fh)
    with tab5:
        tab_static(payload)

    st.markdown("---")
    st.caption("💡 完整分析见项目 README ｜ 深化分析：显著性检验 · RFM · 留存 · 路径 · 关联规则")


if __name__ == "__main__":
    main()

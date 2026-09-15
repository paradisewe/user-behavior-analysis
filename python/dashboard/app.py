"""Streamlit 交互式 Dashboard。

用法：
    cd python
    streamlit run dashboard/app.py
"""

import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# 让脚本能 import src/ 里的分析函数
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT / "src"))

from analysis import (  # noqa: E402
    load_data,
    summarize_behavior_metrics,
    behavior_type_distribution,
    user_level_funnel,
    user_item_sequential_funnel,
    daily_active_users,
    daily_purchase_trend,
    hourly_activity,
    top_categories_by_purchase,
    user_segmentation,
    repurchase_analysis,
)
from config import CLEANED_FILE  # noqa: E402


# ============================================================
# 页面配置
# ============================================================
st.set_page_config(
    page_title="淘宝用户行为分析",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# 配色
COLORS = {
    "pv": "#4C9BE8",
    "cart": "#7B68EE",
    "fav": "#F5A623",
    "buy": "#E94E4E",
}


# ============================================================
# 数据加载（缓存）
# ============================================================
@st.cache_data(show_spinner="加载数据中...")
def get_data():
    """加载并缓存数据，只执行一次。"""
    df = load_data(CLEANED_FILE)
    # 二次过滤，去掉 12-04 的边界
    df = df[(df["timestamp"] >= "2017-11-25") & (df["timestamp"] < "2017-12-04")].copy()
    return df


# ============================================================
# 侧边栏筛选
# ============================================================
def render_sidebar(df: pd.DataFrame) -> pd.DataFrame:
    st.sidebar.markdown("## 🔍 筛选器")

    # 日期范围
    date_min = df["date"].min()
    date_max = df["date"].max()
    date_range = st.sidebar.date_input(
        "日期范围",
        value=(date_min, date_max),
        min_value=date_min,
        max_value=date_max,
    )

    # 行为类型
    all_behaviors = ["pv", "cart", "fav", "buy"]
    selected_behaviors = st.sidebar.multiselect(
        "行为类型",
        options=all_behaviors,
        default=all_behaviors,
    )

    st.sidebar.markdown("---")
    st.sidebar.markdown(
        """
        **数据说明**
        - 抽样方案：用户级分层等比例 5%
        - 数据窗口：2017-11-25 ~ 2017-12-03
        - 全量验证：DuckDB 交叉验证，差异 < 0.1%
        """
    )

    # 应用筛选
    if isinstance(date_range, tuple) and len(date_range) == 2:
        start, end = date_range
        df = df[(df["date"] >= start) & (df["date"] <= end)]
    df = df[df["behavior_type"].isin(selected_behaviors)]

    return df


# ============================================================
# KPI 卡片
# ============================================================
def render_kpis(df: pd.DataFrame, metrics: dict, repurchase: dict):
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("总行为数", f"{metrics['total_behaviors']:,}")
    col2.metric("独立用户数 (UV)", f"{metrics['uv']:,}")
    col3.metric("商品数", f"{metrics['item_count']:,}")
    col4.metric("类目数", f"{metrics['category_count']:,}")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric(
        "浏览→购买转化率",
        f"{repurchase.get('total_buyers', 0) / max(metrics['uv'], 1):.2%}"
        if repurchase else "—",
    )
    col2.metric("复购率", f"{repurchase['repurchase_rate']:.2%}")
    col3.metric("日均 DAU", f"{int(df.groupby('date')['user_id'].nunique().mean()):,}")
    col4.metric("购买用户数", f"{repurchase['total_buyers']:,}")


# ============================================================
# 图 1：行为分布
# ============================================================
def chart_behavior_distribution(df: pd.DataFrame):
    dist = behavior_type_distribution(df)

    col1, col2 = st.columns(2)

    with col1:
        fig = px.pie(
            dist,
            values="behavior_count",
            names="behavior_type",
            color="behavior_type",
            color_discrete_map=COLORS,
            title="行为类型占比",
            hole=0.4,
        )
        fig.update_traces(textposition="inside", textinfo="percent+label")
        fig.update_layout(height=400)
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        fig = px.bar(
            dist,
            x="behavior_type",
            y="behavior_count",
            color="behavior_type",
            color_discrete_map=COLORS,
            title="行为类型绝对量",
            text="behavior_count",
        )
        fig.update_traces(texttemplate="%{text:,.0f}", textposition="outside")
        fig.update_layout(height=400, showlegend=False)
        st.plotly_chart(fig, use_container_width=True)


# ============================================================
# 图 2：转化漏斗
# ============================================================
def chart_funnel(df: pd.DataFrame):
    item_funnel = user_item_sequential_funnel(df)

    stages = ["浏览 (pv)", "加购 (cart)", "购买 (buy)"]
    counts = [
        item_funnel["viewed_pairs"],
        item_funnel["pv_to_cart_pairs"],
        item_funnel["pv_to_buy_pairs"],
    ]
    rates = [
        1.0,
        item_funnel["pv_to_cart_rate"],
        item_funnel["pv_to_buy_rate"],
    ]

    # 漏斗图
    fig = go.Figure(go.Funnel(
        y=stages,
        x=counts,
        textinfo="value+percent initial",
        marker={"color": ["#4C9BE8", "#7B68EE", "#E94E4E"]},
        connector={"line": {"color": "#ccc"}},
    ))
    fig.update_layout(title="用户-商品级漏斗", height=400)
    st.plotly_chart(fig, use_container_width=True)

    st.caption("说明：以「同一用户在同一商品上的先后行为」为口径，反映真实商品转化效率")


# ============================================================
# 图 3：用户趋势
# ============================================================
def chart_user_trend(df: pd.DataFrame):
    dau = daily_active_users(df)
    purchase = daily_purchase_trend(df)
    trend = dau.merge(purchase, on="date", how="left").fillna(0)

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=trend["date"], y=trend["dau"],
        mode="lines+markers",
        name="DAU",
        line={"color": "#4C9BE8", "width": 2.5},
    ))
    fig.add_trace(go.Scatter(
        x=trend["date"], y=trend["purchase_users"],
        mode="lines+markers",
        name="购买用户数",
        line={"color": "#7B68EE", "width": 2.5, "dash": "dash"},
        yaxis="y2",
    ))
    fig.add_trace(go.Scatter(
        x=trend["date"], y=trend["purchase_count"],
        mode="lines+markers",
        name="购买行为数",
        line={"color": "#E94E4E", "width": 2.5, "dash": "dot"},
        yaxis="y2",
    ))

    fig.update_layout(
        title="用户趋势：DAU · 购买用户 · 购买行为",
        xaxis={"title": "日期"},
        yaxis={"title": "DAU", "titlefont": {"color": "#4C9BE8"}},
        yaxis2={
            "title": "购买",
            "titlefont": {"color": "#E94E4E"},
            "overlaying": "y",
            "side": "right",
        },
        height=500,
        hovermode="x unified",
    )
    st.plotly_chart(fig, use_container_width=True)


# ============================================================
# 图 4：时间分布
# ============================================================
def chart_hourly(df: pd.DataFrame):
    hourly = hourly_activity(df)
    pivot = hourly.pivot_table(
        index="hour", columns="behavior_type",
        values="behavior_count", fill_value=0,
    )

    # 按行为归一化
    normalized = pivot.div(pivot.sum(axis=0), axis=1)

    fig = px.imshow(
        normalized.T,
        labels={"x": "小时", "y": "行为类型", "color": "占比"},
        color_continuous_scale="YlOrRd",
        aspect="auto",
        title="用户行为的小时分布（按行为归一化）",
    )
    fig.update_layout(height=350)
    st.plotly_chart(fig, use_container_width=True)

    # 折线图（绝对值）
    fig2 = go.Figure()
    for behavior in ["pv", "cart", "fav", "buy"]:
        if behavior in pivot.columns:
            fig2.add_trace(go.Scatter(
                x=pivot.index, y=pivot[behavior],
                mode="lines+markers",
                name=behavior,
                line={"color": COLORS[behavior], "width": 2},
            ))
    fig2.update_layout(
        title="24 小时行为分布（绝对值）",
        xaxis={"title": "小时", "dtick": 1},
        yaxis={"title": "行为数"},
        height=400,
        hovermode="x unified",
    )
    st.plotly_chart(fig2, use_container_width=True)


# ============================================================
# 图 5：用户分层
# ============================================================
def chart_segmentation(df: pd.DataFrame):
    seg = user_segmentation(df)
    pivot = seg.pivot_table(
        index="behavior_depth", columns="purchase_segment",
        values="users", fill_value=0, observed=True,
    )

    fig = px.bar(
        pivot,
        barmode="stack",
        title="用户行为深度 × 购买分段",
        labels={"value": "用户数", "behavior_depth": "行为深度", "purchase_segment": "购买分段"},
    )
    fig.update_layout(height=450)
    st.plotly_chart(fig, use_container_width=True)


# ============================================================
# 图 6：类目 TOP10
# ============================================================
def chart_top_categories(df: pd.DataFrame):
    top = top_categories_by_purchase(df, top_n=10).sort_values("purchase_count")

    fig = px.bar(
        top,
        x="purchase_count",
        y=top["category_id"].astype(str),
        orientation="h",
        title="购买量 TOP10 类目",
        labels={"x": "购买次数", "y": "类目 ID"},
        text="purchase_count",
        color_discrete_sequence=["#E94E4E"],
    )
    fig.update_traces(texttemplate="%{text:,}", textposition="outside")
    fig.update_layout(height=450, showlegend=False)
    st.plotly_chart(fig, use_container_width=True)


# ============================================================
# 主入口
# ============================================================
def main():
    # 页面标题
    st.title("📊 淘宝用户行为分析 Dashboard")
    st.caption(
        "基于阿里天池「淘宝用户行为数据集」· 用户级分层等比例抽样 5% · "
        "DuckDB 全量交叉验证，核心指标差异 < 0.1%"
    )

    # 加载数据
    df_full = get_data()

    # 侧边栏筛选
    df = render_sidebar(df_full)

    if df.empty:
        st.warning("筛选后无数据，请调整筛选条件。")
        return

    # 重新计算指标（基于筛选后的数据）
    metrics = summarize_behavior_metrics(df)
    repurchase = repurchase_analysis(df)

    # 显示数据范围提示
    st.info(
        f"当前筛选：{df['timestamp'].min()} ~ {df['timestamp'].max()}  |  "
        f"{len(df):,} 条行为  |  {df['user_id'].nunique():,} 名用户"
    )

    # KPI 卡片
    render_kpis(df, metrics, repurchase)

    st.markdown("---")

    # Tabs
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📊 行为分布", "🔻 转化漏斗", "📈 用户趋势", "⏰ 时间分布", "👥 用户分层"
    ])

    with tab1:
        chart_behavior_distribution(df)

    with tab2:
        chart_funnel(df)

    with tab3:
        chart_user_trend(df)

    with tab4:
        chart_hourly(df)

    with tab5:
        col1, col2 = st.columns(2)
        with col1:
            chart_segmentation(df)
        with col2:
            chart_top_categories(df)

    # 页脚
    st.markdown("---")
    st.caption(
        "💡 完整分析见项目 [README](../README.md) ｜ "
        "Excel 版 Dashboard 见 `reports/dashboard.xlsx`"
    )


if __name__ == "__main__":
    main()
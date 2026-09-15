"""生成 Excel Dashboard。

用法：
    cd python
    python dashboard/build_dashboard.py
"""

import sys
from pathlib import Path

import pandas as pd
import xlsxwriter

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
from config import CLEANED_FILE, PROJECT_ROOT as PY_ROOT  # noqa: E402


OUTPUT = PY_ROOT / "reports" / "dashboard.xlsx"


def build():
    print("加载数据...")
    df = load_data(CLEANED_FILE)

    # 保险：过滤掉时间范围外（< 11-25 或 >= 12-04）的边界数据
    #df = df[(df["timestamp"] >= "2017-11-25") & (df["timestamp"] < "2017-12-04")].copy()
    #print(f"过滤后：{len(df):,} 条")

    print("计算分析结果...")
    metrics = summarize_behavior_metrics(df)
    behavior_dist = behavior_type_distribution(df)
    user_funnel = user_level_funnel(df)
    item_funnel = user_item_sequential_funnel(df)
    dau = daily_active_users(df)
    purchase = daily_purchase_trend(df)
    hourly = hourly_activity(df)
    top_cat = top_categories_by_purchase(df, top_n=10)
    seg = user_segmentation(df)
    repurchase = repurchase_analysis(df)

    # 漏斗阶段（Sheet 1 和 Sheet 3 共用）
    funnel_rows = [
        ("浏览 (pv)", int(item_funnel["viewed_pairs"]), 1.0),
        ("加购 (cart)", int(item_funnel["pv_to_cart_pairs"]), float(item_funnel["pv_to_cart_rate"])),
        ("购买 (buy)", int(item_funnel["pv_to_buy_pairs"]), float(item_funnel["pv_to_buy_rate"])),
    ]

    # 复购数据
    total_buyers = int(repurchase["total_buyers"])
    repurchase_users = int(repurchase["repurchase_users"])
    repurchase_rate = round(repurchase_users / total_buyers, 4) if total_buyers else 0.0

    print(f"写入 Excel：{OUTPUT}")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    workbook = xlsxwriter.Workbook(str(OUTPUT))

    # ---------- 全局样式 ----------
    fmt_title = workbook.add_format({
        "font_name": "微软雅黑", "font_size": 16, "bold": True,
        "font_color": "#1F4E79", "align": "left", "valign": "vcenter",
    })
    fmt_subtitle = workbook.add_format({
        "font_name": "微软雅黑", "font_size": 12, "bold": True,
        "font_color": "#333333",
    })
    fmt_header = workbook.add_format({
        "font_name": "微软雅黑", "font_size": 11, "bold": True,
        "bg_color": "#4C9BE8", "font_color": "white",
        "align": "center", "valign": "vcenter", "border": 1,
    })
    fmt_num = workbook.add_format({
        "font_name": "微软雅黑", "font_size": 11,
        "num_format": "#,##0", "align": "right",
    })
    fmt_pct = workbook.add_format({
        "font_name": "微软雅黑", "font_size": 11,
        "num_format": "0.00%", "align": "right",
    })
    fmt_text = workbook.add_format({
        "font_name": "微软雅黑", "font_size": 11,
    })

    # ============================================================
    # Sheet 1：概览
    # ============================================================
    ws = workbook.add_worksheet("概览")
    ws.hide_gridlines(2)
    ws.set_column("A:H", 14)

    # ---------- 概览页专属样式 ----------
    fmt_banner = workbook.add_format({
        "font_name": "微软雅黑", "font_size": 20, "bold": True,
        "font_color": "white", "bg_color": "#1F4E79",
        "align": "left", "valign": "vcenter", "indent": 1,
    })
    fmt_banner_sub = workbook.add_format({
        "font_name": "微软雅黑", "font_size": 10,
        "font_color": "#D0E0F0", "bg_color": "#1F4E79",
        "align": "left", "valign": "vcenter", "indent": 1,
    })
    fmt_section = workbook.add_format({
        "font_name": "微软雅黑", "font_size": 12, "bold": True,
        "font_color": "#1F4E79", "align": "left", "valign": "vcenter",
        "bottom": 2, "bottom_color": "#4C9BE8", "indent": 1,
    })
    fmt_card_label = workbook.add_format({
        "font_name": "微软雅黑", "font_size": 10,
        "font_color": "#666666", "align": "center", "valign": "vcenter",
        "bg_color": "#F2F7FC", "border": 1, "border_color": "#D0E0F0",
    })
    fmt_card_value = workbook.add_format({
        "font_name": "微软雅黑", "font_size": 22, "bold": True,
        "font_color": "#1F4E79", "align": "center", "valign": "vcenter",
        "bg_color": "#F2F7FC", "num_format": "#,##0",
        "border": 1, "border_color": "#D0E0F0",
    })
    fmt_card_value_pct = workbook.add_format({
        "font_name": "微软雅黑", "font_size": 22, "bold": True,
        "font_color": "#E94E4E", "align": "center", "valign": "vcenter",
        "bg_color": "#FDF2F2", "num_format": "0.00%",
        "border": 1, "border_color": "#F5C6C6",
    })
    fmt_card_label_pct = workbook.add_format({
        "font_name": "微软雅黑", "font_size": 10,
        "font_color": "#666666", "align": "center", "valign": "vcenter",
        "bg_color": "#FDF2F2", "border": 1, "border_color": "#F5C6C6",
    })
    fmt_footer = workbook.add_format({
        "font_name": "微软雅黑", "font_size": 9,
        "font_color": "#999999", "align": "left", "indent": 1,
    })

    # ---------- 顶部 Banner ----------
    ws.set_row(0, 45)
    ws.merge_range("A1:H1", "淘宝用户行为分析 Dashboard", fmt_banner)
    ws.set_row(1, 22)
    ws.merge_range(
        "A2:H2",
        f"数据窗口：2017-11-25 ~ 2017-12-03（9 天）  |  "
        f"抽样方案：用户级分层等比例 5%  |  "
        f"分析记录：{int(metrics['total_behaviors']):,} 条",
        fmt_banner_sub,
    )

    # ---------- Section 1：数据规模 ----------
    ws.set_row(4, 25)
    ws.merge_range("A5:H5", "  数据规模", fmt_section)

    kpis_scale = [
        ("总行为数", int(metrics["total_behaviors"])),
        ("独立用户数 (UV)", int(metrics["uv"])),
        ("商品数", int(metrics["item_count"])),
        ("类目数", int(metrics["category_count"])),
    ]
    ws.set_row(5, 25)
    ws.set_row(6, 40)
    for i, (label, value) in enumerate(kpis_scale):
        col = i * 2
        ws.merge_range(6, col, 6, col + 1, label, fmt_card_label)
        ws.merge_range(7, col, 7, col + 1, value, fmt_card_value)

    # ---------- Section 2：效率指标 ----------
    ws.set_row(9, 25)
    ws.merge_range("A10:H10", "  效率指标", fmt_section)

    metrics_eff = [
        ("浏览→购买转化率", float(item_funnel["pv_to_buy_rate"]), True),
        ("加购→购买转化率", float(item_funnel["cart_to_buy_rate"]), True),
        ("复购率", repurchase_rate, True),
        ("日均 DAU", int(dau["dau"].mean()), False),
    ]
    ws.set_row(10, 25)
    ws.set_row(11, 40)
    for i, (label, value, is_pct) in enumerate(metrics_eff):
        col = i * 2
        if is_pct:
            ws.merge_range(11, col, 11, col + 1, label, fmt_card_label_pct)
            ws.merge_range(12, col, 12, col + 1, value, fmt_card_value_pct)
        else:
            ws.merge_range(11, col, 11, col + 1, label, fmt_card_label)
            ws.merge_range(12, col, 12, col + 1, value, fmt_card_value)

    # ---------- Section 3：行为分布 + 漏斗 ----------
    ws.set_row(14, 25)
    ws.merge_range("A15:D15", "  行为分布", fmt_section)
    ws.merge_range("E15:H15", "  用户-商品级漏斗", fmt_section)

    ws.set_row(15, 22)
    ws.write(16, 0, "行为", fmt_header)
    ws.write(16, 1, "数量", fmt_header)
    ws.write(16, 2, "占比", fmt_header)
    ws.write(16, 3, "", fmt_header)
    for i, row in behavior_dist.iterrows():
        ws.write(17 + i, 0, row["behavior_type"], fmt_text)
        ws.write(17 + i, 1, int(row["behavior_count"]), fmt_num)
        ws.write(17 + i, 2, float(row["behavior_share"]), fmt_pct)
        ws.write(17 + i, 3, "", fmt_text)

    ws.write(16, 4, "阶段", fmt_header)
    ws.write(16, 5, "数量", fmt_header)
    ws.write(16, 6, "转化率", fmt_header)
    ws.write(16, 7, "", fmt_header)
    for i, (name, cnt, rate) in enumerate(funnel_rows):
        ws.write(17 + i, 4, name, fmt_text)
        ws.write(17 + i, 5, cnt, fmt_num)
        ws.write(17 + i, 6, rate, fmt_pct)
        ws.write(17 + i, 7, "", fmt_text)

    # ---------- Section 4：趋势预览 ----------
    ws.set_row(22, 25)
    ws.merge_range("A23:H23", "  趋势预览（9 天）", fmt_section)

    trend = dau.merge(purchase, on="date", how="left").fillna(0)

    ws.set_row(23, 22)
    ws.write(24, 0, "指标", fmt_header)
    ws.write(24, 1, "趋势", fmt_header)
    ws.write(24, 2, "最低", fmt_header)
    ws.write(24, 3, "最高", fmt_header)
    ws.write(24, 4, "平均", fmt_header)
    ws.write(24, 5, "峰值日期", fmt_header)
    ws.write(24, 6, "", fmt_header)
    ws.write(24, 7, "", fmt_header)

    # 隐藏 sheet 存趋势数据（供 sparkline 使用）
    ws_trend = workbook.add_worksheet("_trend_data")
    ws_trend.hide()
    ws_trend.write_row(0, 0, ["date", "dau", "purchase_users", "purchase_count"])
    for i, row in trend.iterrows():
        ws_trend.write(i + 1, 0, str(row["date"]))
        ws_trend.write(i + 1, 1, int(row["dau"]))
        ws_trend.write(i + 1, 2, int(row["purchase_users"]))
        ws_trend.write(i + 1, 3, int(row["purchase_count"]))
    n_trend = len(trend)

    trend_items = [
        ("DAU（活跃用户）", "dau", "B", "#4C9BE8"),
        ("购买用户数", "purchase_users", "C", "#7B68EE"),
        ("购买行为数", "purchase_count", "D", "#E94E4E"),
    ]
    for i, (label, col_name, spark_col, color) in enumerate(trend_items):
        row = 25 + i
        ws.write(row, 0, label, fmt_text)

        ws.add_sparkline(row, 1, {
            "range": f"_trend_data!{spark_col}2:{spark_col}{n_trend + 1}",
            "type": "line",
            "markers": True,
            "series_color": color,
        })

        values = trend[col_name].values
        min_v = int(values.min())
        max_v = int(values.max())
        avg_v = int(values.mean())
        peak_idx = int(values.argmax())
        peak_date = str(trend.iloc[peak_idx]["date"])

        ws.write(row, 2, min_v, fmt_num)
        ws.write(row, 3, max_v, fmt_num)
        ws.write(row, 4, avg_v, fmt_num)
        ws.write(row, 5, peak_date, fmt_text)
        ws.write(row, 6, "", fmt_text)
        ws.write(row, 7, "", fmt_text)

    # ---------- 底部说明 ----------
    ws.set_row(29, 20)
    ws.merge_range(
        "A30:H30",
        "说明：所有汇总指标基于用户级分层等比例抽样（5%），"
        "经 DuckDB 全量验证，核心指标差异 < 0.1%。"
        "详见 sql/ 目录的交叉验证结果。",
        fmt_footer,
    )

    # ============================================================
    # Sheet 2：行为分布
    # ============================================================
    ws = workbook.add_worksheet("行为分布")
    ws.set_column("A:D", 16)
    ws.write(0, 0, "行为类型分布", fmt_title)

    ws.write(2, 0, "行为", fmt_header)
    ws.write(2, 1, "数量", fmt_header)
    ws.write(2, 2, "占比", fmt_header)
    for i, row in behavior_dist.iterrows():
        ws.write(3 + i, 0, row["behavior_type"], fmt_text)
        ws.write(3 + i, 1, int(row["behavior_count"]), fmt_num)
        ws.write(3 + i, 2, float(row["behavior_share"]), fmt_pct)

    pie = workbook.add_chart({"type": "pie"})
    pie.add_series({
        "name": "行为占比",
        "categories": ["行为分布", 3, 0, 3 + len(behavior_dist) - 1, 0],
        "values": ["行为分布", 3, 2, 3 + len(behavior_dist) - 1, 2],
        "data_labels": {"percentage": True, "font": {"name": "微软雅黑"}},
    })
    pie.set_title({"name": "行为类型占比"})
    pie.set_size({"width": 480, "height": 300})
    ws.insert_chart("E2", pie)

    bar = workbook.add_chart({"type": "column"})
    bar.add_series({
        "name": "行为数量",
        "categories": ["行为分布", 3, 0, 3 + len(behavior_dist) - 1, 0],
        "values": ["行为分布", 3, 1, 3 + len(behavior_dist) - 1, 1],
        "fill": {"color": "#4C9BE8"},
        "data_labels": {"value": True, "font": {"name": "微软雅黑"}},
    })
    bar.set_title({"name": "行为类型绝对量"})
    bar.set_size({"width": 480, "height": 300})
    ws.insert_chart("E20", bar)

    # ============================================================
    # Sheet 3：转化漏斗
    # ============================================================
    ws = workbook.add_worksheet("转化漏斗")
    ws.set_column("A:D", 18)
    ws.write(0, 0, "用户-商品级漏斗（真实转化效率）", fmt_title)

    ws.write(2, 0, "阶段", fmt_header)
    ws.write(2, 1, "数量", fmt_header)
    ws.write(2, 2, "真实比例", fmt_header)
    for i, (name, cnt, rate) in enumerate(funnel_rows):
        ws.write(3 + i, 0, name, fmt_text)
        ws.write(3 + i, 1, cnt, fmt_num)
        ws.write(3 + i, 2, rate, fmt_pct)

    funnel_chart = workbook.add_chart({"type": "bar"})
    funnel_chart.add_series({
        "name": "数量",
        "categories": ["转化漏斗", 3, 0, 3 + len(funnel_rows) - 1, 0],
        "values": ["转化漏斗", 3, 1, 3 + len(funnel_rows) - 1, 1],
        "fill": {"color": "#E94E4E"},
        "data_labels": {"value": True, "font": {"name": "微软雅黑"}},
    })
    funnel_chart.set_title({"name": "漏斗阶段对比"})
    funnel_chart.set_size({"width": 600, "height": 350})
    ws.insert_chart("E2", funnel_chart)

    # ============================================================
    # Sheet 4：用户趋势
    # ============================================================
    ws = workbook.add_worksheet("用户趋势")
    ws.set_column("A:D", 16)
    ws.write(0, 0, "用户趋势", fmt_title)

    ws.write(2, 0, "日期", fmt_header)
    ws.write(2, 1, "DAU", fmt_header)
    ws.write(2, 2, "购买用户数", fmt_header)
    ws.write(2, 3, "购买行为数", fmt_header)
    for i, row in trend.iterrows():
        ws.write(3 + i, 0, str(row["date"]), fmt_text)
        ws.write(3 + i, 1, int(row["dau"]), fmt_num)
        ws.write(3 + i, 2, int(row["purchase_users"]), fmt_num)
        ws.write(3 + i, 3, int(row["purchase_count"]), fmt_num)

    line = workbook.add_chart({"type": "line"})
    line.add_series({
        "name": "DAU",
        "categories": ["用户趋势", 3, 0, 3 + len(trend) - 1, 0],
        "values": ["用户趋势", 3, 1, 3 + len(trend) - 1, 1],
        "line": {"color": "#4C9BE8", "width": 2.5},
        "marker": {"type": "circle", "size": 6},
    })
    line.add_series({
        "name": "购买用户数",
        "categories": ["用户趋势", 3, 0, 3 + len(trend) - 1, 0],
        "values": ["用户趋势", 3, 2, 3 + len(trend) - 1, 2],
        "line": {"color": "#7B68EE", "width": 2.5, "dash_type": "dash"},
        "marker": {"type": "square", "size": 6},
    })
    line.add_series({
        "name": "购买行为数",
        "categories": ["用户趋势", 3, 0, 3 + len(trend) - 1, 0],
        "values": ["用户趋势", 3, 3, 3 + len(trend) - 1, 3],
        "line": {"color": "#E94E4E", "width": 2.5, "dash_type": "dot"},
        "marker": {"type": "triangle", "size": 6},
    })
    line.set_title({"name": "用户趋势：DAU · 购买用户 · 购买行为"})
    line.set_size({"width": 900, "height": 400})
    ws.insert_chart("E2", line)

    # ============================================================
    # Sheet 5：时间分布
    # ============================================================
    ws = workbook.add_worksheet("时间分布")
    ws.set_column("A:F", 12)
    ws.write(0, 0, "小时活跃度（按行为类型）", fmt_title)

    pivot = hourly.pivot_table(
        index="hour", columns="behavior_type",
        values="behavior_count", fill_value=0,
    ).reset_index()

    ws.write(2, 0, "小时", fmt_header)
    for j, col in enumerate(["pv", "cart", "fav", "buy"]):
        ws.write(2, 1 + j, col, fmt_header)
    for i, row in pivot.iterrows():
        ws.write(3 + i, 0, int(row["hour"]), fmt_text)
        for j, col in enumerate(["pv", "cart", "fav", "buy"]):
            val = row.get(col, 0)
            ws.write(3 + i, 1 + j, int(val) if pd.notna(val) else 0, fmt_num)

    line2 = workbook.add_chart({"type": "line"})
    for j, col in enumerate(["pv", "cart", "fav", "buy"]):
        color = {"pv": "#4C9BE8", "cart": "#7B68EE", "fav": "#F5A623", "buy": "#E94E4E"}[col]
        line2.add_series({
            "name": col,
            "categories": ["时间分布", 3, 0, 3 + len(pivot) - 1, 0],
            "values": ["时间分布", 3, 1 + j, 3 + len(pivot) - 1, 1 + j],
            "line": {"color": color, "width": 2.5},
        })
    line2.set_title({"name": "24 小时行为分布"})
    line2.set_size({"width": 900, "height": 400})
    ws.insert_chart("G2", line2)

    # ============================================================
    # Sheet 6：用户分层
    # ============================================================
    ws = workbook.add_worksheet("用户分层")
    ws.set_column("A:D", 16)
    ws.write(0, 0, "用户行为深度 × 购买分段", fmt_title)

    seg_pivot = seg.pivot_table(
        index="behavior_depth", columns="purchase_segment",
        values="users", fill_value=0, observed=True,
    ).reset_index()

    ws.write(2, 0, "行为深度", fmt_header)
    for j, col in enumerate(seg_pivot.columns[1:]):
        ws.write(2, 1 + j, str(col), fmt_header)
    for i, row in seg_pivot.iterrows():
        ws.write(3 + i, 0, row["behavior_depth"], fmt_text)
        for j, col in enumerate(seg_pivot.columns[1:]):
            ws.write(3 + i, 1 + j, int(row[col]), fmt_num)

    stack = workbook.add_chart({"type": "column", "subtype": "stacked"})
    for j, col in enumerate(seg_pivot.columns[1:]):
        stack.add_series({
            "name": str(col),
            "categories": ["用户分层", 3, 0, 3 + len(seg_pivot) - 1, 0],
            "values": ["用户分层", 3, 1 + j, 3 + len(seg_pivot) - 1, 1 + j],
        })
    stack.set_title({"name": "用户分层结构"})
    stack.set_size({"width": 700, "height": 400})
    ws.insert_chart("G2", stack)

    # ============================================================
    # Sheet 7：类目 TOP10
    # ============================================================
    ws = workbook.add_worksheet("类目TOP10")
    ws.set_column("A:C", 18)
    ws.write(0, 0, "购买量 TOP10 类目", fmt_title)

    ws.write(2, 0, "类目 ID", fmt_header)
    ws.write(2, 1, "购买次数", fmt_header)
    ws.write(2, 2, "购买用户数", fmt_header)
    for i, row in top_cat.iterrows():
        ws.write(3 + i, 0, f"类目 {int(row['category_id'])}", fmt_text)
        ws.write(3 + i, 1, int(row["purchase_count"]), fmt_num)
        ws.write(3 + i, 2, int(row["buyer_count"]), fmt_num)

    bar2 = workbook.add_chart({"type": "bar"})
    bar2.add_series({
        "name": "购买次数",
        "categories": ["类目TOP10", 3, 0, 3 + len(top_cat) - 1, 0],
        "values": ["类目TOP10", 3, 1, 3 + len(top_cat) - 1, 1],
        "fill": {"color": "#E94E4E"},
        "data_labels": {"value": True, "font": {"name": "微软雅黑"}},
    })
    bar2.set_title({"name": "购买量 TOP10 类目"})
    bar2.set_size({"width": 700, "height": 400})
    ws.insert_chart("E2", bar2)

    workbook.close()
    print(f"完成：{OUTPUT}")
    print(f"打开方式：双击 {OUTPUT}")


if __name__ == "__main__":
    build()
# 项目总览：淘宝用户行为与转化漏斗分析

## 项目定位

基于阿里天池「淘宝用户行为数据集」的用户行为分析与转化漏斗研究。这是一个**个人数据分析作品集项目**，用于展示数据管道设计、统计抽样、SQL 交叉验证、可视化和 AI 应用产品化的完整能力。

## 数据来源

| 项目 | 内容 |
|------|------|
| 数据集 | 阿里天池「淘宝用户行为数据集」（UserBehavior.csv） |
| 原始规模 | 100,150,807 行、987,994 名用户 |
| 原始大小 | 约 3.42 GB（无表头 CSV） |
| 时间窗口 | 2017-11-25 ~ 2017-12-03（9 天，北京时间） |
| 字段 | user_id、item_id、category_id、behavior_type、timestamp |
| 行为类型 | pv（浏览）、fav（收藏）、cart（加购）、buy（购买） |

## 技术栈

| 层 | 技术 |
|----|------|
| 数据处理 | Python 3.13 + pandas + numpy + pyarrow |
| 存储优化 | Parquet（snappy 压缩） |
| SQL 分析 | DuckDB（零安装、直接读 Parquet） |
| 可视化 | matplotlib + seaborn + Plotly |
| Dashboard | Excel（xlsxwriter）+ Streamlit |
| AI 应用 | Dify + 本地 LLM（Qwen）+ 本地 Embedding（BGE-M3） |

## 项目结构
User_behavier_analysis/
├── python/ # Python 分析项目
│ ├── src/ # 5 个阶段：侦察 → 抽样 → 清洗 → 分析 → 可视化
│ ├── dashboard/ # Excel + Streamlit 双 Dashboard
│ ├── data/ # 数据（被 gitignore 排除）
│ ├── reports/ # 9 张图表 + Excel 看板
│ └── README.md
├── sql/ # DuckDB 全量分析方案
│ ├── queries/ # 8 个 SQL 查询
│ ├── results/ # 查询结果 CSV
│ └── README.md
└── dify_knowledge/ # AI 问答助手的知识库文档

## 核心方法论

1. **环境约束**：本地 4-6 GB 内存，pandas 处理上限约 500 万行
2. **抽样方案**：用户级分层等比例抽样，每层抽 5% 用户，保留其全部行为
3. **抽样结果**：约 49,400 名用户、约 500 万条行为记录
4. **数据清洗**：去重、去空、行为规范化、时间戳转北京时间、时间范围过滤
5. **交叉验证**：用 DuckDB 在全量 1 亿行上跑 SQL，与 Python 抽样结果对比

## 核心结论

- **加购用户的购买转化率（5.98%）是普通浏览用户（1.41%）的 4 倍**
- DAU 在 2017-12-02（周六）出现峰值，较前 7 天均值上涨约 30%
- 周末深夜（凌晨 2-4 点）存在明显的购买高峰
- 抽样方案与全量 SQL 验证，核心指标差异均 < 0.1%

## 项目边界

- 本项目为**个人作品集**，基于公开数据集
- 不代表任何企业内部生产数据
- 不代表淘宝平台全量经营结论
- 仅用于展示数据分析与 AI 应用的产品化能力
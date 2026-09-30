# 淘宝用户行为与转化漏斗分析

基于阿里天池「淘宝用户行为数据集」（1 亿条真实行为记录）的用户行为分析与转化漏斗研究，
并在主体分析之上完成**三层拓展**：数据分析深化、业务应用、AI 集成。

**核心产出**：从 1 亿行原始数据出发，通过用户级分层等比例抽样与 SQL 全量交叉验证，还原平台级
用户行为规律，识别转化瓶颈与高价值用户画像；拓展层补齐统计检验、经典分析框架，并构建了
接入本地大模型的智能问答助手。

---

## 📂 项目结构

```
├── python/                 主体：Python 分析管道 + 分析 + 可视化 + 本地看板
├── sql/                    主体：DuckDB 全量 SQL 分析（1 亿行，零安装）
├── expands/                拓展层（四个独立模块，见 expands/README.md）
│   ├── ab_test/            A/B 测试框架（历史数据模拟：功效分析+SRM+AA校准）
│   ├── recommender/        轻量推荐原型（类目CF + 时间切分评估，诚实负结果）
│   ├── ai_assistant/       AI 助手：SQL工具服务 + Dify 整合 Chatflow + 知识库
│   └── cloud_dashboard/    Streamlit 云部署版看板（自包含，68KB 预聚合数据）
├── plan.md                 深化方向选型与剩余工作清单
└── 拓展.md                 三层拓展全景：实现步骤、关键结果、踩坑记录
```

`python/` 与 `sql/` 是平级子项目，用不同工具完成同一份数据分析；
`expands/` 是在两者结论之上的拓展层。

---

## 🎯 项目亮点

- **数据规模**：原始数据 100,150,807 行、987,994 名用户（2017-11-25 ~ 12-03）
- **抽样设计**：用户级分层等比例抽样（每层抽 5% 用户，保留其全部行为），内存约束下处理约 500 万行
- **交叉验证**：DuckDB 全量 SQL 与 Python 抽样结果对比，核心指标差异 < 1%（多项 < 0.1%）
- **统计严谨性**：核心结论通过两比例 z 检验与置信区间验证（加购 vs 未加购 +14.81pp，p<0.001）
- **经典框架**：RFM 分层、次日留存、用户路径桑基图、类目关联规则
- **AI 工程**：本地 Dify 整合 Chatflow——NL2SQL 查全量数据、知识库 RAG、Agent 调用本地工具

---

## 📊 核心发现

| 结论 | 数字 |
|------|------|
| 加购是转化关键杠杆 | 已加购→购买 5.98%，浏览直购仅 1.41%（4 倍差距，p<0.001） |
| 周末深夜存在购买高峰 | 工作日购买分散，周末凌晨 2~4 点、早 6 点冲高 |
| 12-02 DAU 异常峰值 | 较基线 +35.2%，次日留存跳升至 98.3%（老用户回流+新用户涌入） |
| 决策链路 | 93.4% 浏览无后续；先加购路径购买率 9.44% > 先收藏 7.99% |

完整指标与图表见 [`python/README.md`](python/README.md)。

---

## 🚀 快速开始

### 环境准备

```bash
pip install pandas numpy pyarrow matplotlib seaborn duckdb scipy plotly
```

### 数据准备

从[阿里天池](https://tianchi.aliyun.com/dataset/649)下载 `UserBehavior.csv`，放到：

```
raw_users_behavier_date/UserBehavior.csv
```

### 一键运行

```bash
# 主体分析（Python 5% 抽样管道）
cd python && python run_all.py

# 全量 SQL 交叉验证
cd ../sql && python run_sql.py

# 拓展模块（各自独立，详见 expands/README.md）
cd ../expands/ab_test && python ab_design.py && python ab_simulation.py
cd ../recommender && python recommender.py
cd ../ai_assistant && python check_services.py && python test_sql_tool.py
```

AI 助手完整搭建（Dify 对接、知识库同步）见
[`expands/ai_assistant/README.md`](expands/ai_assistant/README.md)。

---

## 📖 文档索引

| 文档 | 内容 |
|------|------|
| [`python/README.md`](python/README.md) | 主体分析方法论 + 深化分析章节 + 交叉验证明细 |
| [`sql/README.md`](sql/README.md) | SQL 方案与全量指标 |
| [`expands/README.md`](expands/README.md) | 四个拓展模块简介与入口 |
| [`拓展.md`](拓展.md) | 拓展层实现步骤全景 + 踩坑记录 |
| [`plan.md`](plan.md) | 剩余工作清单与已淘汰方向 |
| [`expands/ai_assistant/dify/`](expands/ai_assistant/dify/) | Dify 配置指南（NL2SQL/Agent/RAG/整合版） |

---

## 🙏 致谢

本项目的**初始项目结构和分析框架**参考了 GitHub 用户 [@bluesblue320-hue](https://github.com/bluesblue320-hue)
的 [Taobao-User-Behavior-Conversion-Analysis](https://github.com/bluesblue320-hue/Taobao-User-Behavior-Conversion-Analysis) 仓库。

主要改进：用户级分层等比例抽样、DuckDB 全量交叉验证、统计检验、RFM/留存/路径/关联规则深化、
A/B 测试框架、推荐原型、接入本地 Dify 的 AI 助手。

> ⚠️ **声明**：本项目为个人学习项目，基于开源仓库修改，非商业用途。原仓库未声明 License，
> 如原作者有异议请联系删除。

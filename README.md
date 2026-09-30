# 淘宝用户行为分析：从数据管道到 AI 智能问答

基于阿里天池「淘宝用户行为数据集」（**1 亿行**真实行为、约 100 万用户、2017-11-25 ~ 12-03 共 9 天）
构建的完整数据分析作品集：一条**经全量交叉验证的 Python 分析管道**，一套**统计深化 + 业务模拟**的
拓展研究，以及一个**接入本地大模型的 AI 智能问答助手**。

---

## 项目结构

```
User_behavier_analysis/
├── python/                       ① 主体分析管道（pandas）
│   ├── src/                      抽样 → 清洗 → 分析（18 个分析模块）→ 可视化（15 张图表）
│   ├── dashboard/                Streamlit 交互式看板（5 个 Tab）
│   └── reports/                  结果表、图表、Excel 看板
├── sql/                          ①′ 全量 SQL 分析（DuckDB，1 亿行，与 Python 交叉验证）
├── expands/                      ② 拓展层（四个独立模块）
│   ├── ab_test/                  A/B 测试框架（历史数据模拟）
│   ├── recommender/              类目协同过滤推荐原型
│   ├── ai_assistant/             AI 智能问答（本地 Dify + SQL 工具服务）
│   └── cloud_dashboard/          可公开访问的云部署看板
├── plan.md                       剩余工作清单
└── 拓展.md                       拓展层全景：实现步骤、结果、踩坑记录
```

---

## 一、数据工程：让 1 亿行数据在单机上可分析

| 问题 | 方案 |
|------|------|
| 1 亿行超出单机内存 | **用户级分层等比例抽样**：按活跃度分四层，每层抽 5% 用户并保留其全部行为（区别于破坏行为序列的行级随机抽样），得到 498 万行、49,326 用户 |
| 分析可复用性 | CSV → **Parquet 缓存**，处理速度提升 5~10 倍 |
| 结果可信度 | 同一份数据用 **Python（抽样）与 DuckDB（全量 1 亿行）双工具交叉验证**：所有核心指标差异 < 1%，行为分布与 pv→cart 转化率差异 < 0.1% |

---

## 二、分析结论

**转化漏斗**（用户-商品级，真实转化口径）：

| 路径 | 转化率 |
|------|--------|
| 浏览 → 购买 | 1.41% |
| 加购 → 购买 | **5.98%**（4 倍杠杆，z 检验 p<0.001） |

**其他核心发现**：

- **93.4%** 的浏览无任何后续行为；先加购路径购买率 **9.44%** > 先收藏 7.99%（用户路径桑基图）
- **RFM 分层**：重要价值客户占 19.4%（平均购买 5.1 次），未购买用户 32.3%
- **次日留存**：基线约 78%，活跃 6~9 天用户 88% vs 2~3 天用户 29.5%
- **12-02 DAU 异常**：较基线 +35.2%，次日留存跳升至 98.3%（老用户回流 + 新用户涌入）
- **类目关联规则**：高支持度规则 lift 最高 5.19（20,970 个有效购物篮）
- **统计严谨性**：加购 vs 未加购购买率差 +14.81pp（z=30.8，p<0.001）；SQL 全量值全部落在抽样 95% 置信区间内

---

## 三、拓展层（expands/）

| 模块 | 做了什么 | 结果 |
|------|---------|------|
| **ab_test** | A/B 测试框架全流程：功效分析 → 随机分组+SRM → 效应注入 → z 检验 → AA 校准 | 现有总体 MDE=2.27pp；200 次 AA 假阳性 4.5%≈理论 5%，框架自洽 |
| **recommender** | 类目协同过滤 + 时间切分评估 vs 热门基线 | 诚实负结果：CF 仅达基线 0.48 倍（9 天窗口共现信号不足），已定位原因 |
| **ai_assistant** | AI 智能问答系统（见下） | 四条分支全部跑通 |
| **cloud_dashboard** | 自包含云部署看板：预聚合 68KB 数据（无用户明细），Streamlit Cloud 一键部署 | 本地/云端双版本 |

## 四、AI 智能问答系统（ai_assistant + 本地 Dify）

用自然语言即可完成「查数据」和「问项目」：

```
用户提问
   ▼
问题分类器（意图路由）
   ├─ 查数据 ──→ LLM 生成 SQL ──→ 本地 SQL 工具服务 ──→ LLM 解读结果
   ├─ 问项目 ──→ 知识库检索（RAG，7 篇项目文档）──→ 引用作答
   ├─ 组合分析 → Agent 自主调用 query_sql / get_schema 工具
   └─ 其他 ────→ 兜底引导
```

- **SQL 工具服务**（`sql_tool_service.py`，宿主机 :5057）：进程内 DuckDB 只读查询全量
  1 亿行 parquet；四道安全闸（单语句白名单 / 关键字黑名单 / LIMIT 封顶 / 30s 超时中断）
  + 宽容解析（兼容模型输出的 JSON、代码块、双层包裹等五种形态）。**模型只有出题权，
  执行权与数据都在本地**——问"12-02 的 DAU"，3 秒返回全量精确值 970,401
- **模型栈**：云端阿里百炼 qwen3.8-flash（推理主力）+ 本地 llama.cpp（可离线降级）+
  bge-m3 嵌入；Rerank（gte-rerank-v2）与按节点模型分配见 plan
- **知识库**：7 篇项目文档（方法/结论/面试指南），优化分段 + 混合检索，
  `dify_sync.py` 一条命令同步

---

## 快速开始

```bash
pip install pandas numpy pyarrow matplotlib seaborn duckdb scipy plotly streamlit
```

从[阿里天池](https://tianchi.aliyun.com/dataset/649)下载 `UserBehavior.csv` 放入
`raw_users_behavier_date/`，然后：

```bash
# ① 主体管道（抽样→清洗→分析→可视化）
cd python && python run_all.py

# ② 全量 SQL 交叉验证
cd ../sql && python run_sql.py

# ③ 拓展模块（各自独立运行）
cd ../expands/ab_test && python ab_design.py && python ab_simulation.py
cd ../recommender && python recommender.py
cd ../ai_assistant && python test_sql_tool.py && python sql_tool_service.py

# ④ 本地看板
streamlit run python/dashboard/app.py
```

AI 助手完整搭建（Dify 对接 / 知识库同步 / 工具导入）见
[`expands/ai_assistant/README.md`](expands/ai_assistant/README.md)。

---

## 技术栈

`pandas` · `DuckDB` · `scipy` · `plotly / matplotlib / seaborn` · `Streamlit` ·
`Dify（Docker 自部署）` · `llama.cpp（本地模型）` · `阿里百炼 qwen` · `bge-m3 嵌入`

## 文档地图

| 想了解 | 去哪 |
|--------|------|
| 分析方法论与全部图表 | [python/README.md](python/README.md) |
| SQL 全量方案 | [sql/README.md](sql/README.md) |
| 拓展层怎么实现的（含踩坑记录） | [拓展.md](拓展.md) |
| 四个拓展模块各自详情 | [expands/README.md](expands/README.md) 及各模块内 README |
| AI 助手搭建与配置 | [expands/ai_assistant/README.md](expands/ai_assistant/README.md) |
| 还剩什么没做 | [plan.md](plan.md) |

---

## 🙏 致谢

本项目的**初始项目结构和分析框架**参考了 GitHub 用户 [@bluesblue320-hue](https://github.com/bluesblue320-hue)
的 [Taobao-User-Behavior-Conversion-Analysis](https://github.com/bluesblue320-hue/Taobao-User-Behavior-Conversion-Analysis) 仓库。
主要改进（抽样设计 / 双工具交叉验证 / 统计检验 / 深化分析 / A/B 与推荐 / AI 问答）的
逐项对比见 [`python/README.md`](python/README.md) 致谢章节。

> ⚠️ **声明**：本项目为个人学习项目，基于开源仓库修改，非商业用途。原仓库未声明 License，
> 如原作者有异议请联系删除。

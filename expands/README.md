# expands/ —— 拓展层

在主体分析（[`../python/`](../python/)、[`../sql/`](../sql/)）结论之上的四个独立拓展模块。
每个模块自带 README 与报告产物，可独立运行；共同的依赖是
`../python/data/cleaned_stratified_data.csv`（主体管道的清洗产出）。

实现步骤、设计决策与踩坑记录的完整版见仓库根目录的 [`../Expands.md`](../Expands.md)。

## 模块一览

| 模块 | 一句话简介 | 详细文档 |
|------|-----------|---------|
| [`ab_test/`](ab_test/) | A/B 测试框架：历史数据模拟实验——功效分析（MDE=2.27pp）、随机分组+SRM、两比例 z 检验、200 次 AA 校准（假阳性 4.5%≈理论 5%） | [ab_test/README.md](ab_test/README.md) |
| [`recommender/`](recommender/) | 轻量推荐原型：类目级协同过滤 + 时间切分离线评估，对比热门基线（诚实负结果：短窗口数据 CF 仅达基线 0.48 倍） | [recommender/README.md](recommender/README.md) |
| [`ai_assistant/`](ai_assistant/) | AI 助手：本地 SQL 工具服务（DuckDB 只读查 1 亿行 + 安全守卫）+ Dify 整合 Chatflow（NL2SQL / 知识库 RAG / Agent 三分支）+ 知识库同步 | [ai_assistant/README.md](ai_assistant/README.md) |
| [`cloud_dashboard/`](cloud_dashboard/) | Streamlit 云部署版看板：自包含应用 + 68KB 预聚合数据（无用户明细，可公开），Streamlit Community Cloud 一键部署 | [cloud_dashboard/README.md](cloud_dashboard/README.md) |

## 运行入口

```bash
# A/B 测试框架（约 2 分钟）
cd ab_test && python ab_design.py && python ab_simulation.py

# 推荐原型（约 2 分钟）
cd ../recommender && python recommender.py

# AI 助手（先体检，SQL 工具可独立自测）
cd ../ai_assistant
python check_services.py        # Dify/LLM/Embedding/SQL工具 四服务体检
python test_sql_tool.py         # 守卫单测 + 接口实测（不依赖 Dify）
python sql_tool_service.py      # 常驻 :5057（Dify 工具调用的后端）

# 云看板（本地预览）
cd ../cloud_dashboard && streamlit run app.py
```

## 说明

- 各模块脚本通过相对路径引用 `python/data/` 下的数据与 parquet，**请在仓库内保持当前目录结构**
- `ai_assistant` 的 Dify 对接部分需要本地 Docker Dify 与模型服务在线，
  离线可用的部分（SQL 工具服务与自测）不依赖任何外部服务
- 知识库文档在 `ai_assistant/dify_knowledge/`（7 篇），更新后用
  `ai_assistant/dify_sync.py` 同步到 Dify 数据集

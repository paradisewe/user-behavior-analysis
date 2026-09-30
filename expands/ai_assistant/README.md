# AI 助手集成（本地 Dify 栈）

对接**本地 Docker 部署的 Dify** + 本地 llama.cpp 模型服务 / 阿里百炼云 API，
覆盖深化计划的三个方向：NL2SQL（#10）、RAG 调优（#11）、Agent 化（#12）。
原仓库顶层 `dify/` 知识库已并入本模块（`dify_knowledge/`）。

## 架构

```
浏览器 → Dify（Docker，:80）
           │
           ├─ Chatflow「NL2SQL」：LLM 节点生成 SQL → HTTP 节点 → sql_tool_service
           ├─ Agent 应用 / Agent 节点：自定义工具（openapi_sql_tool.yaml）→ query_sql / get_schema
           └─ 知识库（dify_knowledge/ 7 篇）：嵌入 + 混合检索
                    │
                    └─ dify_sync.py 同步文档与检索配置

sql_tool_service.py（:5057）：DuckDB 只读查全量 parquet（1 亿行）
本地模型：llama.cpp Qwen2.5-0.5B@:8080（OpenAI 兼容）、bge-m3@:8081（Embedding）
云模型：阿里百炼（通义千问插件，qwen3.8-flash 等）
```

容器内访问宿主机一律用 `host.docker.internal`。

## 目录结构

| 文件/目录 | 说明 |
|-----------|------|
| `sql_tool_service.py` | SQL 工具服务（标准库实现）：/query /schema /health，只读守卫 + 超时中断 + 宽容解析 |
| `test_sql_tool.py` | 自测：守卫单测 + 服务接口实测（**不依赖 Dify，现在就能跑**） |
| `check_services.py` | 一键体检整个集成栈 |
| `openapi_sql_tool.yaml` | Dify 自定义工具导入用的 OpenAPI schema（3 个端点） |
| `dify_sync.py` | 知识库同步：优化分段 + 混合检索设置（dry-run 默认） |
| `dify/` | 四份配置指南：`integrated_chatflow.md`（**整合版，推荐**）、`nl2sql_workflow.md`、`agent_app.md`、`rag_tuning.md` |
| `dify_knowledge/` | Dify 知识库文档源（7 篇：项目总览/方法论/分析结果/SQL验证/Dashboard/数据质量/面试指南） |

## 快速开始

```bash
# 1. 就绪检查（Dify/模型服务未启动时会给出启动顺序）
python check_services.py

# 2. 启动 SQL 工具服务（先自测再常驻）
python test_sql_tool.py        # 守卫 + 接口自测
python sql_tool_service.py     # 常驻 :5057

# 3. 按 dify/ 四份指南在 Dify 控制台配置
# 4. 知识库同步（先 dry-run）
python dify_sync.py
DIFY_DATASET_API_KEY=dataset-xxx python dify_sync.py --apply --dataset-id <id>
```

## 关键设计决策（诚实声明）

- **守卫在服务端而不是提示词里**：LLM 生成的 SQL 一律经过单语句白名单、关键字黑名单、
  LIMIT 封顶（500 行）、30s 超时中断四道闸，提示词再差也危险不到数据
- **视图即清洗口径**：原始 parquet 含时间窗（11-25~12-03）之外的脏行，服务端视图统一
  过滤并派生 `behavior_date`。全量 DAU 与抽样 5% 交叉验证吻合
  （如 12-02：97.04 万 ≈ 48,484 ÷ 5%）
- **宽容解析**：/query 接口兼容标准 JSON、模型自输出的 JSON、纯 SQL、``` 代码块、
  双层包裹垃圾体五种形态——实测修复了 HTTP 节点 `Failed to parse JSON` 问题
- **模型分工**：分类器/轻节点可用本地小模型或 qwen-turbo（省额度），
  SQL 生成与 Agent 用强模型且必须支持 tool calls（qwen3.8-flash 实测四分支全通）
- **Rerank**：百炼通义供应商自带 gte-rerank-v2 可直接启用；本地 llama.cpp 栈
  配不进 rerank 类型，用权重混合检索替代

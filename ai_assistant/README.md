# AI 助手集成（本地 Dify 栈）

对接**本地 Docker 部署的 Dify** + 本地 llama.cpp 模型服务，覆盖 plan.md
第四部分三个方向：NL2SQL（#10）、RAG 调优（#11）、Agent 化（#12）。

## 架构

```
浏览器 → Dify（Docker，:80）
           │
           ├─ Chatflow「NL2SQL」：LLM 节点生成 SQL → HTTP 节点 → sql_tool_service
           ├─ Agent 应用：自定义工具（openapi_sql_tool.yaml）→ query_sql / get_schema
           └─ 知识库（dify_knowledge）：bge-m3 嵌入 + 混合检索
                    │
                    └─ dify_sync.py 同步文档与检索配置

sql_tool_service.py（:5057）：DuckDB 只读查全量 parquet（1 亿行）
llm service/qwen2.5_0.5b.bat（:8080）：LLM
emd_service/bge-m3-Q8_0.bat（:8081）：Embedding
```

容器内访问宿主机一律用 `host.docker.internal`。

## 文件地图

| 文件 | 说明 |
|------|------|
| `sql_tool_service.py` | SQL 工具服务（标准库实现）：/query /schema /health，只读守卫 + 超时中断 |
| `test_sql_tool.py` | 自测：守卫单测 + 服务接口实测（**不依赖 Dify，现在就能跑**） |
| `check_services.py` | 一键体检整个集成栈 |
| `openapi_sql_tool.yaml` | Dify 自定义工具导入用的 OpenAPI schema |
| `dify_sync.py` | 知识库同步：优化分段 + 混合检索设置（dry-run 默认） |
| `dify/nl2sql_workflow.md` | NL2SQL Chatflow 搭建指南（节点级配置） |
| `dify/agent_app.md` | Agent 应用指南（工具导入 + 验收用例） |
| `dify/rag_tuning.md` | 知识库 RAG 调优指南（分段/混合检索/rerank 路线） |

## 快速开始

```bash
# 1. 就绪检查（Dify/模型服务未启动时会给出启动顺序）
python check_services.py

# 2. 启动 SQL 工具服务（先自测再常驻）
python test_sql_tool.py        # 守卫 + 接口自测
python sql_tool_service.py     # 常驻 :5057

# 3. 按 dify/*.md 三份指南在 Dify 控制台配置
# 4. 知识库同步（先 dry-run）
python dify_sync.py
DIFY_DATASET_API_KEY=dataset-xxx python dify_sync.py --apply --dataset-id <id>
```

## 关键设计决策（诚实声明）

- **守卫在服务端而不是提示词里**：LLM 生成的 SQL 一律经过单语句白名单、
  关键字黑名单、LIMIT 封顶（500 行）、30s 超时中断四道闸，提示词再差也危险不到数据。
- **视图即清洗口径**：原始 parquet 含时间窗（11-25~12-03）之外的脏行，
  服务端视图统一过滤并派生 `behavior_date`，LLM 和分析者都不用重复处理。
  全量 DAU 与抽样 5% 交叉验证吻合（如 12-02：97.04 万 ≈ 48,484 ÷ 5%）。
- **Qwen2.5-0.5B 的能力边界**：简单聚合类 NL2SQL 可用；function calling
  不可靠，Agent 应用建议换 7B 以上 GGUF（`dify/agent_app.md` 有说明）。
- **Rerank 暂不启用**：llama.cpp 支持 `--rerank`，但 Dify OpenAI 兼容供应商
  不暴露 rerank 类型；当前用权重混合检索（语义 0.7/关键词 0.3）替代，
  Chatflow HTTP 二次排序是后续扩展点。

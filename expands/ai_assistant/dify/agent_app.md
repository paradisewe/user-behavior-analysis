# Dify Agent 应用指南（工具调用）

目标：让 AI 助手能**自主调用工具**——查数据库、生成图表、导出报告，
而不是被动等固定流程。

## 与 NL2SQL Chatflow 的区别

| | Chatflow（nl2sql_workflow.md） | Agent |
|---|---|---|
| 流程 | 固定：LLM→HTTP→LLM | 模型自主决定调哪个工具、调几次 |
| 模型要求 | 普通 LLM 即可 | **需要 function-calling 能力可靠的模型** |
| 适合演示 | 单一问答 | 「查一下 DAU 趋势并画图导出报告」这类组合任务 |

> ⚠️ 诚实声明：Qwen2.5-**0.5B** 的 function calling 不可靠（漏参数、编造工具名），
> Agent 应用建议换 **Qwen2.5-7B-Instruct 或以上**的 GGUF（llama.cpp 同端口载入，
> Dify 供应商配置不变）。0.5B 上硬调，工具名与参数经常错。

## 工具导入（自定义工具）

Dify 控制台 → 工具 → 自定义 → 导入 `ai_assistant/openapi_sql_tool.yaml`
（servers 已指向 `host.docker.internal:5057`，无需鉴权）。

导入后可用工具：
- `query_sql`：执行只读 SQL（核心）
- `get_schema`：取表结构与指标口径（Agent 第一步常用它自省）
- `health_check`：探活

## Agent 应用配置

创建应用 → Agent → Function Calling：

- 模型：Qwen2.5-7B-Instruct（OpenAI-API-compatible 供应商，指向 llama.cpp）
- 工具：勾选上述三个
- 指令（SYSTEM）：

```
你是淘宝用户行为数据的分析助手，拥有 SQL 查询工具。

工作方式：
1. 先看表结构（get_schema），确认字段与口径再动手
2. 查数用 query_sql；用户问"趋势/画图/报告"时，
   先查数据，再把 JSON 结果整理进 Markdown 表格
3. 数字一律用千分位；日期范围只有 2017-11-25 ~ 12-03
4. 查询失败时如实转述 error 字段，不要编造数据
```

## 组合任务的验收用例

| 任务 | 期望工具调用序列 |
|------|-----------------|
| 12-02 的 DAU 是多少 | get_schema（可选）→ query_sql → 回答 |
| 对比周末和工作日的购买用户数 | query_sql（按 is_weekend 分组或两天对比）→ 回答 |
| 给我一份 9 天 DAU 趋势报告 | query_sql（逐日 DAU）→ 在回答中输出 Markdown 表格 + 趋势解读 |

## 扩展：画图 / 导报告工具

`openapi_sql_tool.yaml` 目前只含查数。要支持「生成图表文件」，在
`ai_assistant/sql_tool_service.py` 里加一个 POST /plot 端点（matplotlib 渲染
PNG 存到 reports/figures/，返回文件路径），再往 OpenAPI schema 里加一个
/plot path 即可——仓库刻意保持最小可用集，扩展点已留好。

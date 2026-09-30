# RAG 调优指南（本地 Dify + bge-m3）

对应 plan.md 深化方向 #11 的**可执行部分**：针对本项目 7 个知识文档的
检索质量调优。完整在线评测需要 Dify 运行中；本指南 + `dify_sync.py`
构成落地路径。

## 现状问题

`dify/dify_knowledge/*.md`（7 个文档，60~76 行/篇）如果用 Dify 默认
分段（自动模式），会出现：

1. **段落切断**：默认按 token 数硬切，把「指标口径表」切成两半，答案跨段丢失
2. **纯向量检索**：脱敏 ID、专有名词（DAU、RFM、pv→buy）在向量空间区分度低，
   关键词命中的文档排不到前面
3. **top_k 默认 2~3**：答案分散在 02_methodology 和 03_analysis_results 时召回不全

## 调优方案（按投入产出排序）

### 1. 优化分段（收益最大，dify_sync.py 已内置）

- 分段方式：自定义，分隔符 `\n\n`（文档本身按标题/空行组织）
- max_tokens=800、chunk_overlap=100：一个完整小节基本落在一个 chunk 内

```bash
DIFY_DATASET_API_KEY=dataset-xxx python dify_sync.py --apply --dataset-id <id>
```

### 2. 混合检索（向量 + 全文关键词）

`dify_sync.py --apply` 会把数据集检索设置切换为：

| 参数 | 值 | 理由 |
|------|-----|------|
| search_method | hybrid_search | 专有名词靠关键词，语义变体靠向量 |
| weights | 语义 0.7 / 关键词 0.3 | 术语匹配为主、语义兜底 |
| top_k | 6 | 覆盖跨文档答案 |
| rerank | 关闭 | 见下 |

### 3. 嵌入模型确认

Dify → 设置 → 模型供应商 → OpenAI-API-compatible 再加一个：

| 字段 | 值 |
|------|-----|
| 模型类型 | Text Embedding |
| Base URL | `http://host.docker.internal:8081/v1`（bge-m3，llama.cpp） |
| API Key | 任意 |

知识库设置里把嵌入模型切到 bge-m3（重新索引）。

### 4. Rerank（✅ 用阿里百炼 API 时可启用）

通义千问供应商插件自带重排模型 `gte-rerank-v2`。启用方式：
知识库 → 检索设置 → 混合检索 → Rerank 设置选 gte-rerank-v2，
替代 weight 模式（重排一般优于固定权重）。

> 若仍用本地 llama.cpp 栈（OpenAI 兼容供应商不暴露 rerank 类型），
> 则维持权重混合（第 2 步），或参考 Chatflow HTTP 二次排序方案。

## 验证方法

1. `python dify_sync.py --apply` 同步后，到知识库「命中测试」页跑一组问题：

| 测试问题 | 期望命中 |
|---------|---------|
| 抽样是怎么做的，为什么不用行级随机 | 02_methodology |
| 12-02 DAU 为什么暴涨 | 03_analysis_results |
| SQL 和 Python 的结果差多少 | 04_sql_validation |
| 数据质量怎么样，有没有缺失 | 06_data_quality |
| 面试会问什么 | 07_interview_guide |
| Dashboard 怎么用 | 05_dashboard_guide |
| 这个项目的目标是什么 | 01_project_overview |

2. 调优前后各测一轮，记录「期望文档是否出现在 top3」——这是最朴素的
   Recall@3 评测；问答助手回答质量由此直接决定。
3. 注意：dify_knowledge 文档内容还**未覆盖深化分析**（RFM/留存/路径/关联规则/
   显著性检验），先补充文档内容再同步，避免助手口径停留在旧结论。

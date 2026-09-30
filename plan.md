# 项目剩余工作清单

> 已完成部分（数据分析深化、业务应用、AI 集成四分支）的实现与结果
> 见 [拓展.md](拓展.md)。本文档只保留**未完成**事项。

## 一、收尾（优先）

### 1. 恢复分类器路由并发布最终版
- 测试期为绕开 0.5B 分类器不稳定，将开始节点直连了四条支路
- 待做：删除 4 条临时直连边 → 恢复 开始 → 问题分类器 → 四分支 的原连线 → 重新发布
- 分类器四类配置完好未动，只需恢复连线

### 2. 导出 Dify 应用 DSL 备份进仓库
- 整合 Chatflow 目前只存在于 Dify 数据库
- 应用编辑页 → 更多操作 → 导出 DSL → 存入 `expands/ai_assistant/dify/`

### 3. 全量 push 与 Streamlit 上云
- 本地 main 领先远程 10+ 提交、feature/streamlit-cloud 1 个提交，均未推送
- push 后到 share.streamlit.io 以 `expands/cloud_dashboard/app.py` 为入口部署
  （步骤见 expands/cloud_dashboard/README.md）

## 二、质量提升

### 4. 知识库内容更新 + 同步
- `expands/ai_assistant/dify_knowledge/` 尚未覆盖深化分析新结论
  （显著性检验/RFM/留存/路径/关联规则）
- 补内容后：`dify_sync.py --apply` 同步（需知识库 API Key，按文档名幂等替换）

### 5. 知识检索启用 Rerank
- 百炼通义供应商自带 gte-rerank-v2，知识库召回设置切换即可（替代权重混合）

### 6. 按节点分配模型
- 分类器：qwen-turbo 或本地 Qwen2.5-1.5B（0.5B 输出 JSON 不稳已弃用）
- SQL 生成：可试 qwen-plus（比 flash 稳，该环节错了会断链路）
- 解读/重写/兜底：qwen-turbo 省成本

## 三、未来拓展（已评估，暂缓）

| 方向 | 说明 |
|------|------|
| Laya 本地意图路由 | 多语言 System-1 决策模型（~33ms），接入架构=HTTP+条件分支；先实测中文四分类准确率再决定 |
| /plot 端点 | sql_tool_service 加 matplotlib 渲染，Agent 获得"查数并出图"能力 |
| 单元测试 + CI | 合成 fixture 数据 + pytest + GitHub Actions（原始数据不入库，CI 只跑 fixture） |
| CUPED / 分层随机 | ab_test 框架的进阶模块，补齐后可做真实实验设计 |

## 四、不做（评估后淘汰，留档）

| 方向 | 原因 |
|------|------|
| 深度学习模型 | 数据没有标签，做不了 |
| 实时流处理 | 数据是离线的，硬做没意义 |
| 复杂推荐系统 | 短窗口数据上热门基线更强（recommender 已实测验证） |
| 换数据库（Hive/Spark） | 单机数据，没必要 |
| 数据管道自动化（Airflow/Prefect） | 数据一次性静态，无第二次调度 |
| 用户流失预警模型 | 9 天窗口定义不了流失标签 |
| 封装桌面 App | 成本高，对数据分析岗展示价值低 |

# Dify NL2SQL 工作流搭建指南（本地 Docker 部署）

目标：在本地 Dify 里搭一个 Chatflow，用自然语言查全量 1 亿行数据，
例：「12-02 的 DAU 是多少」「购买量 top5 的类目」。

```
用户问题 → LLM 节点（生成 SQL） → HTTP 请求节点（执行） → LLM 节点（解读结果） → 回答
                │                        │
                │                        └─ sql_tool_service（本仓库 ai_assistant/）
                └─ 模型：本地 llama.cpp Qwen2.5
```

## 0. 前置条件

| 服务 | 状态检查 | 说明 |
|------|---------|------|
| Docker Desktop + Dify 容器 | `python check_services.py` | nginx 默认 :80 |
| sql_tool_service | `python sql_tool_service.py` | 监听 127.0.0.1:5057 |
| 本地 LLM（可选调试用） | `llm service/qwen2.5_0.5b.bat` | llama.cpp :8080 |

## 1. 配置模型供应商（一次性）

Dify 控制台 → 设置 → 模型供应商 → 安装 **OpenAI-API-compatible**：

| 字段 | 值 |
|------|-----|
| 模型名称 | qwen2.5-0.5b-instruct |
| Base URL | `http://host.docker.internal:8080/v1` |
| API Key | `llamacpp`（llama.cpp 不校验，随便填） |
| 模型类型 | LLM |

> ⚠️ 容器内访问宿主机必须用 `host.docker.internal`，`localhost` 指向容器自己。

## 2. 创建 Chatflow

创建应用 → Chatflow，四个节点串成一条线：

### 节点 1：开始
- 添加输入变量 `question`（文本，必填）

### 节点 2：LLM（生成 SQL）
- 模型：qwen2.5-0.5b-instruct
- SYSTEM 提示词（要点，完整版可直接粘贴）：

```
你是 SQL 生成器。把用户问题翻译成一条 DuckDB SQL（只输出 SQL，不要解释）。

表 user_behavior，字段：
- user_id BIGINT, item_id BIGINT, category_id BIGINT
- behavior_type VARCHAR：pv/fav/cart/buy
- behavior_date DATE：行为日期（2017-11-25 ~ 2017-12-03）
- behavior_time TIMESTAMP

规则：
1. 只允许一条 SELECT/WITH 语句，必须带 LIMIT
2. DAU = COUNT(DISTINCT user_id) 按 behavior_date 分组
3. 转化率用用户级口径：有某行为的用户数之比

示例：
问：12-02 的 DAU 是多少
SQL：SELECT behavior_date, COUNT(DISTINCT user_id) AS dau
     FROM user_behavior WHERE behavior_date = DATE '2017-12-02'
     GROUP BY 1 LIMIT 10

问：购买量 top5 的类目
SQL：SELECT category_id, COUNT(*) AS buy_count FROM user_behavior
     WHERE behavior_type = 'buy' GROUP BY 1 ORDER BY buy_count DESC LIMIT 5
```

- USER 提示词：`{{#start.question#}}`

### 节点 3：HTTP 请求
- 方法 POST，URL `http://host.docker.internal:5057/query`
- Body（JSON）：

```json
{"sql": "{{#llm.text#}}"}
```

- 输出变量：`body`（JSON 字符串，含 columns/rows/error）

### 节点 4：LLM（解读结果）→ 回答
- SYSTEM：`你是数据分析助手。根据 SQL 查询结果用中文回答用户问题；若 body 含 error 字段，如实说明查询失败原因。数字用千分位。`
- USER：`问题：{{#start.question#}}\n查询结果：{{#http-request.body#}}`
- 回答节点引用该 LLM 输出。

## 3. 验收用例

| 问题 | 期望 |
|------|------|
| 12-02 的 DAU 是多少 | 970,401（全量口径） |
| 每天的购买用户数 | 9 行，12-03 最高 |
| 购买量 top5 的类目 | 返回 5 行 |

## 4. 故障排查

### HTTP 节点报 SSRF protection（常见）

报错形如 `Access to 'http://host.docker.internal:5057/query' was blocked by
SSRF protection`——新版 Dify 的 HTTP 节点默认拦截解析到私有/回环地址的目标，
而 `host.docker.internal` 正是内网 IP。修复：

1. 编辑 Dify 部署目录下 `docker/.env`：
   ```env
   SSRF_PROXY_ALLOW_PRIVATE_IPS=192.168.65.0/24,172.16.0.0/12,10.0.0.0/8
   ```
2. 重建容器（restart 不一定重读 .env）：
   ```bash
   docker compose down && docker compose up -d
   ```
3. 仍报错则改 squid ACL：`docker/ssrf_proxy/squid.conf.template` 在
   `http_access deny` 之前加：
   ```
   acl allowed_hosts dst 192.168.65.0/24 172.16.0.0/12 10.0.0.0/8
   http_access allow allowed_hosts
   ```
4. 精确定位要放行的网段：
   ```bash
   docker exec -it <api容器名> python -c "import socket; print(socket.gethostbyname('host.docker.internal'))"
   ```

安全提示：放行等于允许 Dify 访问对应内网段；办公网环境建议只放行
192.168.65.0/24（Docker Desktop 专用网段）。

### 其他

- 容器内访问宿主机必须用 `host.docker.internal`，`localhost` 指向容器自己
- sql_tool_service 窗口关闭 = Dify 查询报连接失败，演示时保持运行

## 5. 已知限制（诚实声明）

- **Qwen2.5-0.5B 生成复杂 SQL 的可靠性有限**。简单聚合（DAU/计数/占比）通常可用；
  多表思路、窗口函数类问题容易出错。升级路径：把 llama.cpp 换载
  Qwen2.5-7B-Instruct GGUF（同端口重启 bat 即可，提示词不变）。
- 守卫兜底：就算 LLM 生成危险/超时 SQL，sql_tool_service 会拦截或中断，
  错误信息会回流给解读节点如实转述。
- 抽样口径（python/ 分析用的 5%）与全量口径数字不同，
  本工作流查的是**全量**；对比时注意口径。

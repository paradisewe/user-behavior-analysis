"""本地 SQL 工具服务 —— Dify NL2SQL / Agent 的取数后端。

架构位置（Dify 本地 Docker 部署）：

    Dify Chatflow/Agent（容器内）
        │  HTTP 节点 / 自定义工具（host.docker.internal:5057）
        ▼
    sql_tool_service.py（本服务，标准库实现，零第三方 web 依赖）
        │  只读守卫 + DuckDB
        ▼
    python/data/UserBehavior.parquet（1 亿行全量）

接口：
    GET  /health  → 存活检查
    GET  /schema  → 表结构 + 指标口径说明（供 Dify LLM 节点做提示词）
    POST /query   {"sql": "..."} → 执行只读查询，返回 {columns, rows, ...}

安全守卫（防 LLM 生成危险 SQL）：
    - 仅允许单条 SELECT/WITH 语句
    - 关键字黑名单（INSERT/UPDATE/DROP/ATTACH/COPY/PRAGMA...）
    - 无 LIMIT 时自动追加，行数封顶
    - 查询超时中断（默认 30s）、只读模式打开数据库

启动：python sql_tool_service.py  （默认 127.0.0.1:5057）
注意：Dify 容器内访问本服务用 host.docker.internal，不是 localhost。
"""

from __future__ import annotations

import json
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import duckdb

REPO_ROOT = Path(__file__).resolve().parents[2]  # 仓库根（本模块在 expands/ 下）
PARQUET = REPO_ROOT / "python" / "data" / "UserBehavior.parquet"

HOST, PORT = "127.0.0.1", 5057
QUERY_TIMEOUT_S = 30
MAX_ROWS = 500

# 表名（SQL 中使用）：全量行为明细
TABLE_NAME = "user_behavior"

FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|create|attach|detach|copy|export|"
    r"import|pragma|call|set|install|load|checkpoint|vacuum|force)\b",
    re.IGNORECASE,
)

SCHEMA_INFO = {
    "table": TABLE_NAME,
    "note": "视图已按项目清洗口径过滤：仅保留 2017-11-25 ~ 12-03 的行为（原始 parquet 含窗口外脏行）",
    "columns": [
        ("user_id", "BIGINT", "用户 ID（脱敏）"),
        ("item_id", "BIGINT", "商品 ID（脱敏）"),
        ("category_id", "BIGINT", "类目 ID（脱敏）"),
        ("behavior_type", "VARCHAR", "行为类型：pv/fav/cart/buy"),
        ("behavior_time", "TIMESTAMP", "行为时间（北京时间）"),
        ("behavior_date", "DATE", "行为日期，按天聚合直接用它"),
    ],
    "metric_cookbook": [
        "DAU：SELECT behavior_date, COUNT(DISTINCT user_id) FROM user_behavior GROUP BY 1 ORDER BY 1",
        "行为占比：GROUP BY behavior_type",
        "购买用户数：behavior_type = 'buy' 的 COUNT(DISTINCT user_id)",
        "复购率：购买 ≥2 次的用户 / 购买用户",
    ],
}


# ---------- 守卫 ----------
def validate_sql(sql: str) -> str:
    """校验并规范化只读查询，返回可执行 SQL；不合法则抛 ValueError。"""
    if not sql or not sql.strip():
        raise ValueError("空查询")
    sql = sql.strip().rstrip(";").strip()
    if ";" in sql:
        raise ValueError("只允许单条语句")
    if not re.match(r"(?is)^\s*(select|with)\b", sql):
        raise ValueError("只允许 SELECT/WITH 查询")
    if FORBIDDEN.search(sql):
        raise ValueError("包含禁止的关键字")
    sql = re.sub(r"(?is)\blimit\s+\d+\s*;", "", sql)  # 去掉尾部旧 limit
    if not re.search(r"(?is)\blimit\s+\d+\s*$", sql):
        sql += f" LIMIT {MAX_ROWS}"
    else:
        m = re.search(r"(?is)\blimit\s+(\d+)\s*$", sql)
        if int(m.group(1)) > MAX_ROWS:
            sql = sql[: m.start(1)] + str(MAX_ROWS) + sql[m.end(1):]
    return sql


# ---------- 查询执行 ----------
class QueryEngine:
    def __init__(self, parquet: Path):
        if not parquet.exists():
            raise FileNotFoundError(f"数据文件不存在：{parquet}")
        self.parquet = parquet
        self.conn = duckdb.connect(database=":memory:")  # 只读性由 validate_sql 守卫保证
        self.lock = threading.Lock()

    def run(self, sql: str) -> dict:
        sql = validate_sql(sql)
        started = time.perf_counter()
        timed_out = threading.Event()
        timer = threading.Timer(QUERY_TIMEOUT_S, self.conn.interrupt)
        timer.daemon = True
        timer.start()
        try:
            with self.lock:
                # 视图即清洗口径：原始 parquet 含 2017-11-25 ~ 12-03 之外的脏行，
                # 统一在此过滤并派生 behavior_time / behavior_date，SQL 侧无需再处理
                self.conn.execute(
                    f"CREATE OR REPLACE VIEW {TABLE_NAME} AS "
                    f"SELECT user_id, item_id, category_id, behavior_type, "
                    f"       to_timestamp(timestamp) AS behavior_time, "
                    f"       CAST(to_timestamp(timestamp) AS DATE) AS behavior_date "
                    f"FROM read_parquet('{self.parquet.as_posix()}') "
                    f"WHERE to_timestamp(timestamp) >= TIMESTAMP '2017-11-25 00:00:00' "
                    f"  AND to_timestamp(timestamp) <  TIMESTAMP '2017-12-04 00:00:00'"
                )
                try:
                    rel = self.conn.execute(sql)
                    columns = [d[0] for d in rel.description]
                    rows = rel.fetchall()
                except duckdb.InterruptException:
                    timed_out.set()
                    raise ValueError(f"查询超时（>{QUERY_TIMEOUT_S}s）")
        finally:
            timer.cancel()

        return {
            "columns": columns,
            "rows": [[_to_jsonable(v) for v in row] for row in rows],
            "row_count": len(rows),
            "truncated": len(rows) >= MAX_ROWS,
            "elapsed_ms": round((time.perf_counter() - started) * 1000),
            "executed_sql": sql,
            "timeout": timed_out.is_set(),
        }


def _to_jsonable(v):
    from datetime import date, datetime
    if isinstance(v, (datetime, date)):
        return str(v)
    if hasattr(v, "item"):  # numpy 标量
        return v.item()
    return v


# ---------- HTTP 服务 ----------
def _extract_sql(raw: str) -> str:
    """宽容解析请求体：兼容三种形态——
    1. 标准 JSON {"sql": "..."}
    2. LLM 直接输出的 JSON（可能嵌在模板里产生的双层包裹）
    3. 纯 SQL 文本 / ```sql 代码块
    """
    raw = (raw or "").strip()
    if not raw:
        raise ValueError("请求体为空")

    # 形态 1/2：能按 JSON 解析时取 sql 字段；双层包裹时逐层剥壳
    candidate = raw
    for _ in range(3):
        try:
            payload = json.loads(candidate)
        except Exception:
            break
        if isinstance(payload, dict) and "sql" in payload:
            candidate = payload["sql"]
            if not isinstance(candidate, str):
                return json.dumps(candidate, ensure_ascii=False)
        else:
            break
    sql = candidate if isinstance(candidate, str) else str(candidate)

    # 形态 3：剥 markdown 代码块围栏
    sql = re.sub(r"^\s*```[a-zA-Z]*\s*|\s*```\s*$", "", sql.strip()).strip()

    # 兜底：双层包裹等非法 JSON（如 {"sql": "{"sql": "..."}"}）整体解析失败时，
    # 从第一个 SELECT/WITH 截取，并修剪尾部的 }" 残渣
    if not re.match(r"(?is)^\s*(select|with)\b", sql):
        m = re.search(r"(?is)\b(select|with)\b.*", sql)
        if not m:
            raise ValueError('请求体需为 {"sql": "..."} 或纯 SQL 文本')
        sql = m.group(0)
    sql = re.sub(r"[\s;}\"']+$", "", sql).strip()
    if not sql:
        raise ValueError('请求体需为 {"sql": "..."} 或纯 SQL 文本')
    return sql


class Handler(BaseHTTPRequestHandler):
    engine: QueryEngine = None  # 类属性，main() 注入

    def _send(self, code: int, payload: dict):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            self._send(200, {"status": "ok", "table": TABLE_NAME,
                             "parquet": self.engine.parquet.name})
        elif self.path == "/schema":
            self._send(200, SCHEMA_INFO)
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/query":
            self._send(404, {"error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length).decode("utf-8", "ignore")
            sql = _extract_sql(raw)
            result = self.engine.run(sql)
            self._send(200, result)
        except ValueError as exc:
            self._send(400, {"error": str(exc)})
        except Exception as exc:  # noqa: BLE001
            self._send(500, {"error": f"执行失败：{exc}"})

    def log_message(self, fmt, *args):  # 安静模式
        pass


def main() -> None:
    Handler.engine = QueryEngine(PARQUET)
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"SQL 工具服务已启动：http://{HOST}:{PORT}")
    print(f"数据：{PARQUET.name}（只读）")
    print("Dify 容器内请使用：http://host.docker.internal:5057")
    server.serve_forever()


if __name__ == "__main__":
    main()

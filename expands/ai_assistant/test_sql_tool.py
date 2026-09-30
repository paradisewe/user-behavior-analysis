"""sql_tool_service 的自测：守卫单测 + 起服务实测接口（不依赖 Dify）。"""

from __future__ import annotations

import json
import threading
import urllib.request
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sql_tool_service import Handler, QueryEngine, PARQUET, validate_sql
from http.server import ThreadingHTTPServer


# ---------- 守卫单测 ----------
def test_guard():
    good = [
        "SELECT COUNT(*) FROM user_behavior",
        "SELECT CAST(timestamp AS DATE) d, COUNT(DISTINCT user_id) dau "
        "FROM user_behavior GROUP BY d ORDER BY d",
        "WITH t AS (SELECT 1 AS x) SELECT x FROM t",
        "SELECT behavior_type, COUNT(*) FROM user_behavior GROUP BY behavior_type LIMIT 10;",
    ]
    for sql in good:
        validate_sql(sql)
    print(f"✅ 合法查询放行 {len(good)} 条")

    bad = [
        ("", "空"),
        ("DROP TABLE x", "DROP"),
        ("SELECT 1; SELECT 2", "多语句"),
        ("INSERT INTO x VALUES (1)", "INSERT"),
        ("ATTACH 'x.db' AS y", "ATTACH"),
        ("COPY (SELECT 1) TO 'out.csv'", "COPY"),
        ("SELECT * FROM user_behavior WHERE 1=1; DELETE FROM t", "夹带 DELETE"),
        ("PRAGMA database_list", "PRAGMA"),
        ("SET threads = 1", "SET"),
    ]
    for sql, label in bad:
        try:
            validate_sql(sql)
            raise AssertionError(f"应被拒绝但放行了：{label}")
        except ValueError:
            pass
    print(f"✅ 危险查询全部拦截 {len(bad)} 条")

    forced = validate_sql("SELECT user_id FROM user_behavior")
    assert forced.upper().endswith("LIMIT 500"), forced
    over = validate_sql("SELECT 1 LIMIT 999999")
    assert over == "SELECT 1 LIMIT 500", over
    print("✅ LIMIT 自动追加与封顶生效")


# ---------- 服务实测 ----------
def http(method: str, url: str, payload: dict = None) -> tuple[int, dict]:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def test_service():
    engine = QueryEngine(PARQUET)
    Handler.engine = engine
    server = ThreadingHTTPServer(("127.0.0.1", 5058), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = "http://127.0.0.1:5058"

    code, body = http("GET", f"{base}/health")
    assert code == 200 and body["status"] == "ok", body
    print("✅ /health 正常")

    code, body = http("GET", f"{base}/schema")
    assert code == 200 and body["table"] == "user_behavior"
    print("✅ /schema 正常（LLM 节点的表结构来源）")

    # 全量 1 亿行的真实查询
    code, body = http("POST", f"{base}/query", {"sql":
        "SELECT behavior_date AS d, COUNT(DISTINCT user_id) AS dau "
        "FROM user_behavior GROUP BY d ORDER BY d"})
    assert code == 200, body
    print(f"✅ 全量 DAU 查询 {body['elapsed_ms']}ms，{body['row_count']} 天，"
          f"末 3 天：{[r for r in body['rows'][-3:]]}")

    code, body = http("POST", f"{base}/query", {"sql": "DROP TABLE user_behavior"})
    assert code == 400, body
    print(f"✅ 危险 SQL 经 HTTP 被拒：{body['error']}")

    server.shutdown()
    print("\n全部自测通过 ✅")


if __name__ == "__main__":
    test_guard()
    test_service()

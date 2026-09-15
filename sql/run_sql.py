"""DuckDB 执行器：读取 queries/ 下的 SQL，执行并保存结果到 results/。

用法：
    python run_sql.py                           # 跑所有 SQL
    python run_sql.py queries/02_user_funnel.sql  # 只跑一个
"""

import sys
import time
from pathlib import Path

import duckdb
import pandas as pd


# 路径配置
SQL_ROOT = Path(__file__).resolve().parent
QUERY_DIR = SQL_ROOT / "queries"
RESULT_DIR = SQL_ROOT / "results"
RESULT_DIR.mkdir(exist_ok=True)

# 数据源：Python 阶段生成的 Parquet（全量 1 亿行）
PARQUET_PATH = SQL_ROOT.parent / "python" / "data" / "UserBehavior.parquet"

# 时间范围（和 Python 保持一致）
TS_MIN = 1509494400   # 2017-11-01
TS_MAX = 1514764800   # 2018-01-01


def get_connection() -> duckdb.DuckDBPyConnection:
    """建立 DuckDB 连接，注册数据视图。"""
    if not PARQUET_PATH.exists():
        raise FileNotFoundError(
            f"Parquet 数据不存在：{PARQUET_PATH}\n"
            "请先运行：cd ../python && python src/data_prepare.py"
        )

    con = duckdb.connect()
    # 把 Parquet 注册成视图，后续 SQL 里直接 SELECT FROM user_behavior
    con.execute(f"""
        CREATE VIEW user_behavior AS
        SELECT *
        FROM read_parquet('{PARQUET_PATH.as_posix()}')
        WHERE behavior_type IN ('pv', 'fav', 'cart', 'buy')
          AND timestamp BETWEEN {TS_MIN} AND {TS_MAX}
    """)
    return con


def run_one(con: duckdb.DuckDBPyConnection, sql_path: Path) -> pd.DataFrame:
    """执行单个 SQL 文件。"""
    sql = sql_path.read_text(encoding="utf-8")
    print(f"\n{'=' * 70}")
    print(f"执行：{sql_path.name}")
    print("=" * 70)

    t0 = time.time()
    df = con.execute(sql).df()
    elapsed = time.time() - t0

    # 打印前 20 行
    with pd.option_context("display.max_rows", 20, "display.width", 200):
        print(df.head(20))
    if len(df) > 20:
        print(f"... (共 {len(df):,} 行)")
    print(f"耗时 {elapsed:.2f} 秒")

    # 保存（utf-8-sig 让 Excel 打开不乱码）
    out_path = RESULT_DIR / f"{sql_path.stem}.csv"
    df.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"已保存：{out_path.name}")
    return df


def main():
    con = get_connection()
    print(f"数据源：{PARQUET_PATH}")

    if len(sys.argv) > 1:
        targets = [Path(sys.argv[1])]
    else:
        targets = sorted(QUERY_DIR.glob("*.sql"))

    print(f" 共 {len(targets)} 个查询\n")

    for sql_path in targets:
        try:
            run_one(con, sql_path)
        except Exception as e:
            print(f"{sql_path.name} 执行失败：{e}")

    con.close()
    print(f"\n{'=' * 70}")
    print(f"全部完成，结果在：{RESULT_DIR}")
    print("=" * 70)


if __name__ == "__main__":
    main()
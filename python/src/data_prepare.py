"""分层等比例抽样：每层按相同比例抽用户，保留用户全部行为。

内存约束 4-6 GB → 目标 500 万行
分层等比例抽样 → 所有用户权重相同
"""

import random
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq


REQUIRED_COLUMNS = ["user_id", "item_id", "category_id", "behavior_type", "timestamp"]
VALID_BEHAVIORS = {"pv", "fav", "cart", "buy"}

TS_MIN = 1509494400
TS_MAX = 1514764800

CHUNK_SIZE = 2_000_000
TARGET_ROWS = 5_000_000


def clean_chunk(chunk: pd.DataFrame) -> pd.DataFrame:
    """向量化清洗一个 chunk。"""
    existing_cols = [c for c in REQUIRED_COLUMNS if c in chunk.columns]
    chunk = chunk.dropna(subset=existing_cols)

    chunk["behavior_type"] = (
        chunk["behavior_type"].astype(str).str.lower().str.strip()
    )
    chunk = chunk[chunk["behavior_type"].isin(VALID_BEHAVIORS)]

    chunk["timestamp"] = pd.to_numeric(chunk["timestamp"], errors="coerce")
    chunk = chunk.dropna(subset=["timestamp"])
    chunk["timestamp"] = chunk["timestamp"].astype("int64")
    chunk = chunk[(chunk["timestamp"] >= TS_MIN) & (chunk["timestamp"] <= TS_MAX)]
    return chunk


def csv_to_parquet(csv_path: str, parquet_path: str, encoding: str = "utf-8"):
    """把原始 CSV 清洗后转成 Parquet（一次性操作）。"""
    parquet_file = Path(parquet_path)
    if parquet_file.exists():
        print(f"Parquet 缓存已存在：{parquet_file}")
        return

    print("正在把 CSV 转成 Parquet...")
    writer = None
    total_rows = 0

    try:
        for chunk in pd.read_csv(
            csv_path, header=None, names=REQUIRED_COLUMNS,
            dtype=str, chunksize=CHUNK_SIZE, encoding=encoding,
            on_bad_lines="skip",
        ):
            chunk = clean_chunk(chunk)
            if chunk.empty:
                continue

            chunk["user_id"] = chunk["user_id"].astype("int64")
            chunk["item_id"] = chunk["item_id"].astype("int64")
            chunk["category_id"] = chunk["category_id"].astype("int64")
            chunk["timestamp"] = chunk["timestamp"].astype("int64")

            table = pa.Table.from_pandas(chunk, preserve_index=False)
            if writer is None:
                writer = pq.ParquetWriter(
                    str(parquet_file), table.schema, compression="snappy",
                )
            writer.write_table(table)
            total_rows += len(chunk)
    finally:
        if writer is not None:
            writer.close()

    print(f"Parquet 生成完成，共 {total_rows:,} 行")


def load_chunks(source_path, columns=None):
    """统一读取：Parquet 用 read_parquet，其他用 read_csv。"""
    if str(source_path).endswith(".parquet"):
        df = pd.read_parquet(source_path, columns=columns)
        for i in range(0, len(df), CHUNK_SIZE):
            yield df.iloc[i:i + CHUNK_SIZE]
    else:
        for chunk in pd.read_csv(
            source_path, header=None, names=REQUIRED_COLUMNS,
            dtype=str, chunksize=CHUNK_SIZE, encoding="utf-8",
            on_bad_lines="skip",
        ):
            yield chunk


def scan_user_activity(source_path) -> dict:
    """第一遍扫描：统计每个用户的行为总次数。"""
    print("第一遍扫描：统计用户活跃度...")
    total_valid = 0
    counters = []

    for chunk in load_chunks(
        source_path, columns=["user_id", "behavior_type", "timestamp"],
    ):
        chunk = clean_chunk(chunk)
        if chunk.empty:
            continue
        total_valid += len(chunk)
        counters.append(chunk["user_id"].value_counts())

    all_counts = pd.concat(counters)
    user_counts = all_counts.groupby(level=0).sum().to_dict()

    print(f"有效行数：{total_valid:,}")
    print(f"独立用户数：{len(user_counts):,}")
    return user_counts


def compute_tier_func(user_counts: dict):
    """用 q10/q50/q90 分位数切分四层。"""
    counts = np.array(list(user_counts.values()))
    q10, q50, q90 = np.percentile(counts, [10, 50, 90])
    print(f"分位数：q10={q10:.0f}  q50={q50:.0f}  q90={q90:.0f}")

    def tier_func(user_id):
        c = user_counts.get(user_id, 0)
        if c >= q90:
            return "high"
        elif c >= q50:
            return "mid"
        elif c >= q10:
            return "low"
        return "silent"

    return tier_func


def aggregate_by_tier(user_counts: dict, tier_func):
    """按层聚合用户列表和原始行数。"""
    tier_users = defaultdict(list)
    tier_rows = defaultdict(int)
    for uid, cnt in user_counts.items():
        t = tier_func(uid)
        tier_users[t].append(uid)
        tier_rows[t] += cnt
    return dict(tier_users), dict(tier_rows)


def compute_sampling_ratio(tier_rows: dict, target_rows: int) -> float:
    """等比例抽样的统一比例 p = 目标行数 / 原始总行数。"""
    total_rows = sum(tier_rows.values())
    return min(1.0, target_rows / total_rows)


def compute_quotas(tier_users: dict, p: float) -> dict:
    """按比例 p 计算每层要抽多少用户。"""
    return {t: int(round(len(users) * p)) for t, users in tier_users.items()}


def print_allocation(tier_users, tier_rows, quotas, p):
    print(f"\n分层等比例抽样方案 p={p:.4%}")
    print(f"{'层级':<8} {'用户数':>10} {'原始行数':>14} {'抽样用户':>10} {'抽样行数':>14}")
    for t in ["high", "mid", "low", "silent"]:
        n_users = len(tier_users.get(t, []))
        n_rows = tier_rows.get(t, 0)
        q = quotas.get(t, 0)
        avg = n_rows / n_users if n_users > 0 else 0
        print(f"{t:<8} {n_users:>10,} {n_rows:>14,} {q:>10,} {int(q * avg):>14,}")
    total_q = sum(quotas.values())
    total_rows = sum(tier_rows.values())
    total_users = sum(len(u) for u in tier_users.values())
    print(f"{'合计':<8} {total_users:>10,} {total_rows:>14,} "
          f"{total_q:>10,} {int(total_q * total_rows / total_users):>14,}")
    print(f"权重：{1/p:.2f}")


def stratified_sample(source_path, output_path, tier_users, quotas, p, seed=42):
    """第二遍扫描：按配额从每层抽用户，保留其全部行为。"""
    print("\n第二遍扫描：分层等比例抽样中...")
    random.seed(seed)

    sampled_users = set()
    weight = 1.0 / p

    for tier, users in tier_users.items():
        quota = quotas.get(tier, 0)
        if quota <= 0:
            continue
        picked = random.sample(users, min(quota, len(users)))
        sampled_users.update(picked)
        print(f"{tier}: 抽 {len(picked):,} / {len(users):,} 用户")

    print(f"合计被抽中：{len(sampled_users):,} 用户，统一权重 {weight:.2f}")

    samples = []
    for chunk in load_chunks(source_path):
        chunk = clean_chunk(chunk)
        if chunk.empty:
            continue
        chunk = chunk[chunk["user_id"].isin(sampled_users)]
        if not chunk.empty:
            chunk = chunk.copy()
            chunk["weight"] = weight
            samples.append(chunk[REQUIRED_COLUMNS + ["weight"]])

    result = pd.concat(samples, ignore_index=True) if samples else pd.DataFrame(
        columns=REQUIRED_COLUMNS + ["weight"]
    )

    print(f"共抽样 {len(result):,} 条，涉及 {result['user_id'].nunique():,} 个用户")
    print(f"平均每用户行为数：{len(result) / max(result['user_id'].nunique(), 1):.1f}")

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(output, index=False)
    print(f"已保存到：{output}")

    return result


def run(file_path, output_path, parquet_cache=None, target_rows=TARGET_ROWS, seed=42):
    if parquet_cache:
        if not Path(parquet_cache).exists():
            csv_to_parquet(file_path, parquet_cache)
        source = parquet_cache
    else:
        source = file_path

    user_counts = scan_user_activity(source)
    tier_func = compute_tier_func(user_counts)
    tier_users, tier_rows = aggregate_by_tier(user_counts, tier_func)

    p = compute_sampling_ratio(tier_rows, target_rows)
    quotas = compute_quotas(tier_users, p)
    print_allocation(tier_users, tier_rows, quotas, p)

    return stratified_sample(source, output_path, tier_users, quotas, p, seed=seed)


if __name__ == "__main__":
    from config import RAW_DATA, STRATIFIED_FILE, PARQUET_CACHE

    run(
        file_path=str(RAW_DATA),
        output_path=str(STRATIFIED_FILE),
        parquet_cache=str(PARQUET_CACHE),
        target_rows=5_000_000,
        seed=42,
    )
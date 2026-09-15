"""分层抽样：幂分配（p=0.5）+ 保底，带 Parquet 缓存加速。

功能：
  1. 一次性把原始 CSV 转成 Parquet（缓存）
  2. 第一遍扫描：统计每个用户的行为总次数
  3. 按分位数把用户分成 high/mid/low/silent 四层
  4. 幂分配 + 保底，计算每层配额和抽样比例
  5. 第二遍扫描：按比例分层抽样
  6. 输出 stratified_data.csv
"""

import random
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

import pyarrow as pa
import pyarrow.parquet as pq

# ============================================================
# 常量配置
# ============================================================
REQUIRED_COLUMNS = ["user_id", "item_id", "category_id", "behavior_type", "timestamp"]
VALID_BEHAVIORS = {"pv", "fav", "cart", "buy"}

# 天池数据合法时间窗口（Unix 秒）
TS_MIN = 1509494400   # 2017-11-01 00:00:00 UTC
TS_MAX = 1514764800   # 2018-01-01 00:00:00 UTC

# 分块读取大小
CHUNK_SIZE = 2_000_000

# 抽样配置
TARGET_SAMPLE = 100_000   # 目标样本量
POWER_P = 0.5             # 幂分配指数
MIN_QUOTA = 5_000         # 每层保底配额

# 用户级抽样比例（注意：这是"抽用户"的比例，不是"抽行"的比例）
# 用户级抽样比例（非等概率：小层比例高，大层比例低）
USER_SAMPLE_RATIOS = {
    "high":   0.0005,   # 0.05%  → 约 50 用户
    "mid":    0.001,    # 0.1%   → 约 400 用户
    "low":    0.002,    # 0.2%   → 约 800 用户
    "silent": 0.008,    # 0.8%   → 约 750 用户 ⭐
}

# ============================================================
# 清洗函数
# ============================================================
def clean_chunk(chunk: pd.DataFrame) -> pd.DataFrame:
    """
    向量化清洗一个 chunk：
      - 只对存在的列去空
      - 行为类型规范化（小写、去空格、过滤非法值）
      - 时间戳转 int，并过滤到合法时间窗口内
    """
    # 只对当前 chunk 里实际存在的列做去空
    existing_cols = [c for c in REQUIRED_COLUMNS if c in chunk.columns]
    chunk = chunk.dropna(subset=existing_cols)

    # 行为类型规范化
    chunk["behavior_type"] = (
        chunk["behavior_type"].astype(str).str.lower().str.strip()
    )
    chunk = chunk[chunk["behavior_type"].isin(VALID_BEHAVIORS)]

    # 时间戳转 int
    chunk["timestamp"] = pd.to_numeric(chunk["timestamp"], errors="coerce")
    chunk = chunk.dropna(subset=["timestamp"])
    chunk["timestamp"] = chunk["timestamp"].astype("int64")

    # 时间范围过滤
    chunk = chunk[(chunk["timestamp"] >= TS_MIN) & (chunk["timestamp"] <= TS_MAX)]

    return chunk


# ============================================================
# CSV → Parquet 一次性转换
# ============================================================

def csv_to_parquet(csv_path: str, parquet_path: str, encoding: str = "utf-8"):
    """把原始 CSV 清洗后转成 Parquet（一次性操作，用 pyarrow 原生接口分块追加）。"""
    parquet_file = Path(parquet_path)
    if parquet_file.exists():
        print(f"✅ Parquet 缓存已存在：{parquet_file}")
        return

    print("📦 正在把 CSV 转成 Parquet（一次性操作，可能需要几分钟）...")
    writer = None
    total_rows = 0

    try:
        for chunk in pd.read_csv(
            csv_path,
            header=None,
            names=REQUIRED_COLUMNS,
            dtype=str,
            chunksize=CHUNK_SIZE,
            encoding=encoding,
            on_bad_lines="skip",
        ):
            chunk = clean_chunk(chunk)
            if chunk.empty:
                continue

            # 类型规范化
            chunk["user_id"] = chunk["user_id"].astype("int64")
            chunk["item_id"] = chunk["item_id"].astype("int64")
            chunk["category_id"] = chunk["category_id"].astype("int64")
            chunk["timestamp"] = chunk["timestamp"].astype("int64")

            # 转成 pyarrow Table
            table = pa.Table.from_pandas(chunk, preserve_index=False)

            # 第一块时初始化 writer，之后一直复用
            if writer is None:
                writer = pq.ParquetWriter(
                    str(parquet_file),
                    table.schema,
                    compression="snappy",
                )

            writer.write_table(table)
            total_rows += len(chunk)
            print(f"   已写入 {total_rows:,} 行...")

    finally:
        if writer is not None:
            writer.close()

    print(f"✅ Parquet 已生成：{parquet_file}")
    print(f"   总行数：{total_rows:,}")

# ============================================================
# 统一读取接口
# ============================================================
def load_chunks(source_path, columns=None):
    """
    统一读取接口：
      - .parquet 用 read_parquet（可指定 columns 裁剪列）
      - 其他用 read_csv 分块
    """
    if str(source_path).endswith(".parquet"):
        df = pd.read_parquet(source_path, columns=columns)
        for i in range(0, len(df), CHUNK_SIZE):
            yield df.iloc[i:i + CHUNK_SIZE]
    else:
        for chunk in pd.read_csv(
            source_path,
            header=None,
            names=REQUIRED_COLUMNS,
            dtype=str,
            chunksize=CHUNK_SIZE,
            encoding="utf-8",
            on_bad_lines="skip",
        ):
            yield chunk


# ============================================================
# 第一遍：统计用户活跃度
# ============================================================
def scan_user_activity(source_path, encoding: str = "utf-8") -> dict:
    """第一遍扫描：统计每个用户的行为总次数。"""
    print("📊 第一遍扫描：统计用户活跃度...")
    total_valid = 0
    counters = []

    # 只读 3 列，减少 I/O
    for chunk in load_chunks(
        source_path,
        columns=["user_id", "behavior_type", "timestamp"],
    ):
        chunk = clean_chunk(chunk)
        if chunk.empty:
            continue
        total_valid += len(chunk)
        counters.append(chunk["user_id"].value_counts())

    print("   合并用户计数...")
    all_counts = pd.concat(counters)
    user_counts = all_counts.groupby(level=0).sum().to_dict()

    print(f"   有效行数：{total_valid:,}")
    print(f"   独立用户数：{len(user_counts):,}")
    return user_counts


# ============================================================
# 分层边界
# ============================================================
def compute_tier_func(user_counts: dict):
    """用 q10/q50/q90 分位数切分四层，返回 tier_func。"""
    counts = np.array(list(user_counts.values()))
    q10, q50, q90 = np.percentile(counts, [10, 50, 90])
    print(f"\n📐 分位数：q10={q10:.0f}  q50={q50:.0f}  q90={q90:.0f}")

    def tier_func(user_id: str) -> str:
        c = user_counts.get(user_id, 0)
        if c >= q90:
            return "high"
        elif c >= q50:
            return "mid"
        elif c >= q10:
            return "low"
        return "silent"

    return tier_func


def compute_tier_rows(user_counts: dict, tier_func):
    """按层聚合原始行数和用户数。"""
    tier_rows = defaultdict(int)
    tier_users = defaultdict(int)
    for uid, cnt in user_counts.items():
        t = tier_func(uid)
        tier_rows[t] += cnt
        tier_users[t] += 1
    return dict(tier_rows), dict(tier_users)


# ============================================================
# 幂分配 + 保底
# ============================================================
def compute_quotas(tier_rows: dict,
                   total: int = TARGET_SAMPLE,
                   p: float = POWER_P,
                   min_quota: int = MIN_QUOTA) -> dict:
    """
    幂分配 + 保底：
      Step 1: 幂分配   n_h ∝ N_h^p
      Step 2: 每层保底 min_quota
      Step 3: 归一化（保底后超了从大层按比例扣）
    """
    # Step 1: 幂分配
    weights = {t: tier_rows[t] ** p for t in tier_rows}
    total_weight = sum(weights.values())
    quotas = {t: total * w / total_weight for t, w in weights.items()}

    # Step 2: 保底
    for t in quotas:
        quotas[t] = max(quotas[t], min_quota)

    # Step 3: 迭代归一化
    for _ in range(3):
        total_quota = sum(quotas.values())
        if total_quota <= total:
            break
        excess = total_quota - total
        for t in quotas:
            quotas[t] -= excess * quotas[t] / total_quota
        for t in quotas:
            quotas[t] = max(quotas[t], min_quota)

    return {t: int(round(v)) for t, v in quotas.items()}


def print_allocation(tier_rows, tier_users, quotas, ratios):
    """打印配额分配方案。"""
    print("\n" + "=" * 70)
    print("📋 幂分配方案（p=0.5 + 保底 5000）")
    print("=" * 70)
    print(f"{'层级':<8} {'用户数':>10} {'原始行数':>14} {'配额':>10} {'抽样比例':>12}")
    print("-" * 70)
    for t in ["high", "mid", "low", "silent"]:
        if t not in quotas:
            continue
        print(f"{t:<8} {tier_users.get(t, 0):>10,} {tier_rows.get(t, 0):>14,} "
              f"{quotas[t]:>10,} {ratios[t]:>12.6f}")
    print("-" * 70)
    print(f"{'合计':<8} {sum(tier_users.values()):>10,} "
          f"{sum(tier_rows.values()):>14,} {sum(quotas.values()):>10,}")
    print("=" * 70)


# ============================================================
# 第二遍：分层抽样
# ============================================================
def stratified_sample(source_path, output_path, user_counts, tier_func,
                      user_sample_ratios, seed=42, encoding="utf-8"):
    """第二遍：用户级分层抽样（保留被抽中用户的全部行为）。"""
    print(f"\n🎯 第二遍扫描：用户级分层抽样中...")

    random.seed(seed)
    np.random.seed(seed)

    # 构建 user_id → tier 映射
    print("   构建用户层级映射...")
    uid_to_tier = pd.Series(
        {uid: tier_func(uid) for uid in user_counts},
        name="tier",
    )
    uid_to_tier.index.name = "user_id"

    # ★ 关键：预先决定每个用户是否被抽中，并记录权重
    print("   决定哪些用户被抽中...")
    sampled_users = {}
    uid_to_weight = {}
    for uid, tier in uid_to_tier.items():
        ratio = user_sample_ratios.get(tier, 0.0)
        sampled_users[uid] = random.random() < ratio
        uid_to_weight[uid] = 1.0 / ratio if ratio > 0 else 0.0

    n_sampled = sum(sampled_users.values())
    print(f"   被抽中的用户数：{n_sampled:,}")
    print(f"   占全部用户比例：{n_sampled / len(sampled_users):.4%}")

    samples = []
    original_stats = defaultdict(lambda: defaultdict(int))
    sampled_stats = defaultdict(lambda: defaultdict(int))

    for chunk in load_chunks(source_path):
        chunk = clean_chunk(chunk)
        if chunk.empty:
            continue

        chunk["tier"] = chunk["user_id"].map(uid_to_tier)
        chunk["date_str"] = (
            pd.to_datetime(chunk["timestamp"], unit="s")
            .dt.strftime("%Y-%m-%d")
        )

        # 统计原始量
        for (d, t), cnt in chunk.groupby(["date_str", "tier"]).size().items():
            original_stats[d][t] += cnt

        # ★ 关键：按用户是否被抽中过滤，并给每行打上权重
        chunk["keep"] = chunk["user_id"].map(sampled_users).fillna(False)
        chunk["weight"] = chunk["user_id"].map(uid_to_weight).fillna(0.0)
        sampled = chunk[chunk["keep"]]

        # 统计抽样量
        for (d, t), cnt in sampled.groupby(["date_str", "tier"]).size().items():
            sampled_stats[d][t] += cnt

        samples.append(sampled[REQUIRED_COLUMNS + ["weight"]])

        result = pd.concat(samples, ignore_index=True) if samples else pd.DataFrame(columns=REQUIRED_COLUMNS + ["weight"])
    print(f"\n✅ 共抽样 {len(result):,} 条，涉及 {result['user_id'].nunique():,} 个用户")
    print(f"   平均每用户行为数：{len(result) / max(result['user_id'].nunique(), 1):.1f}")

    # 打印分层统计
    print("\n📊 分层抽样统计（按天 × 层级）：")
    for d in sorted(original_stats.keys()):
        orig = original_stats[d]
        samp = sampled_stats[d]
        line = f"   {d}:  "
        for t in ["high", "mid", "low", "silent"]:
            line += f"{t}={samp.get(t, 0):,}/{orig.get(t, 0):,}  "
        print(line)

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(output, index=False)
    print(f"\n💾 已保存到：{output}")

    return result
# ============================================================
# 总入口
# ============================================================
def run_stratified_sampling(file_path, output_path,
                            parquet_cache=None,
                            seed: int = 42,
                            encoding: str = "utf-8"):
    """一站式运行：转 Parquet → 第一遍 → 分层 → 分配 → 第二遍。"""
    # 步骤 0：准备数据源
    if parquet_cache:
        if not Path(parquet_cache).exists():
            csv_to_parquet(file_path, parquet_cache, encoding)
        source = parquet_cache
    else:
        source = file_path

    # 第一遍：扫描
    user_counts = scan_user_activity(source, encoding)

    # 分层：计算边界、聚合
    tier_func = compute_tier_func(user_counts)
    tier_rows, tier_users = compute_tier_rows(user_counts, tier_func)

    print("\n👥 各层级原始数据：")
    for t in ["high", "mid", "low", "silent"]:
        print(f"   {t}: 用户 {tier_users.get(t, 0):,}  行数 {tier_rows.get(t, 0):,}")

    # 用户级等概率抽样（直接用常量）
    print("\n👥 各层级用户级抽样比例：")
    for t in ["high", "mid", "low", "silent"]:
        print(f"   {t}: {USER_SAMPLE_RATIOS.get(t, 0):.4%}")

    # 第二遍：用户级抽样
    return stratified_sample(
        source, output_path, user_counts, tier_func,
        user_sample_ratios=USER_SAMPLE_RATIOS,
        seed=seed, encoding=encoding,
    )

# ============================================================
# 使用入口
# ============================================================
if __name__ == "__main__":
    from config import RAW_DATA, STRATIFIED_FILE, PARQUET_CACHE

    run_stratified_sampling(
        file_path=str(RAW_DATA),
        output_path=str(STRATIFIED_FILE),
        parquet_cache=str(PARQUET_CACHE),
        seed=42,
        encoding="utf-8",
    )
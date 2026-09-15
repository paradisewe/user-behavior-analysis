"""正式清洗：把抽样数据整理成分析友好的格式。

输入：data/stratified_data.csv      （分层抽样结果，约 10 万条）
输出：data/cleaned_stratified_data.csv （清洗后数据）
"""

from pathlib import Path

import pandas as pd


# 天池数据的合法时间范围
VALID_START = pd.Timestamp("2017-11-25")
VALID_END = pd.Timestamp("2017-12-04")  # 不含 12-04 当天，用于左闭右开

VALID_BEHAVIORS = {"pv", "fav", "cart", "buy"}
REQUIRED_COLUMNS = ["user_id", "item_id", "category_id", "behavior_type", "timestamp"]
WEIGHT_COLUMN = "weight"


def load_data(input_path: str) -> pd.DataFrame:
    print(f"📥 读取：{input_path}")
    df = pd.read_csv(input_path)
    missing = set(REQUIRED_COLUMNS) - set(df.columns)
    if missing:
        raise ValueError(f"缺少必要的列：{missing}")
    if WEIGHT_COLUMN not in df.columns:
        raise ValueError(f"缺少权重列：{WEIGHT_COLUMN}")
    print(f"   原始行数：{len(df):,}")
    print(f"   权重列存在 ✅")
    return df


def drop_duplicates(df: pd.DataFrame) -> pd.DataFrame:
    """去重：同一行完全相同的记录只保留一条。"""
    before = len(df)
    df = df.drop_duplicates()
    print(f"去重：{before:,} → {len(df):,}  （删除 {before - len(df):,} 条）")
    return df


def drop_missing(df: pd.DataFrame) -> pd.DataFrame:
    """去空：关键列不能为空。"""
    before = len(df)
    df = df.dropna(subset=REQUIRED_COLUMNS)
    print(f"去空：{before:,} → {len(df):,}  （删除 {before - len(df):,} 条）")
    return df


def normalize_behavior(df: pd.DataFrame) -> pd.DataFrame:
    """规范化行为类型：统一小写、去空格、只保留合法值。"""
    before = len(df)
    df["behavior_type"] = df["behavior_type"].astype(str).str.lower().str.strip()
    df = df[df["behavior_type"].isin(VALID_BEHAVIORS)]
    print(f" 行为规范化：{before:,} → {len(df):,}  （删除 {before - len(df):,} 条）")
    return df


def convert_timestamp(df: pd.DataFrame) -> pd.DataFrame:
    """时间戳转换：Unix 秒 → datetime。"""
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="s")
    print(f" 时间戳转换完成，范围：{df['timestamp'].min()} ~ {df['timestamp'].max()}")
    return df


def filter_time_range(df: pd.DataFrame) -> pd.DataFrame:
    """过滤越界时间：只保留合法时间窗口内的数据。"""
    before = len(df)
    df = df[(df["timestamp"] >= VALID_START) & (df["timestamp"] < VALID_END)]
    print(f"🧹 时间过滤：{before:,} → {len(df):,}  （删除 {before - len(df):,} 条）")
    return df


def convert_dtypes(df: pd.DataFrame) -> pd.DataFrame:
    """类型规范化：ID 转 int64，行为转 category，节省内存。"""
    df["user_id"] = df["user_id"].astype("int64")
    df["item_id"] = df["item_id"].astype("int64")
    df["category_id"] = df["category_id"].astype("int64")
    df["behavior_type"] = df["behavior_type"].astype("category")
    print(f"类型规范化完成")
    return df


def save_data(df: pd.DataFrame, output_path: str) -> None:
    """保存清洗后的数据。"""
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output, index=False)
    print(f" 已保存：{output}")


def clean(input_path: str, output_path: str) -> pd.DataFrame:
    """正式清洗总入口：按顺序执行所有清洗步骤。"""
    print("=" * 60)
    print(f" 输入：{input_path}")
    print(f" 输出：{output_path}")
    print("=" * 60)

    df = load_data(input_path)
    df = drop_duplicates(df)
    df = drop_missing(df)
    df = normalize_behavior(df)
    df = convert_timestamp(df)
    df = filter_time_range(df)
    df = convert_dtypes(df)
    save_data(df, output_path)

    print("\n" + "=" * 60)
    print(f" 清洗完成，最终行数：{len(df):,}")
    print("=" * 60)
    return df


# ---------- 使用入口 ----------
if __name__ == "__main__":
    from config import STRATIFIED_FILE, CLEANED_FILE

    clean(
        input_path=str(STRATIFIED_FILE),
        output_path=str(CLEANED_FILE),
    )
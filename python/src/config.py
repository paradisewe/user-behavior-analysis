from pathlib import Path

# 项目根目录（src 的上一级，即 python/）
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# 数据目录
DATA_DIR = PROJECT_ROOT / "data"

# 原始数据（位于仓库根目录 raw_users_behavier_date/）
RAW_DATA = PROJECT_ROOT.parent / "raw_users_behavier_date" / "UserBehavior.csv"

# 数据文件
PARQUET_CACHE = DATA_DIR / "UserBehavior.parquet"
STRATIFIED_FILE = DATA_DIR / "stratified_data.csv"
CLEANED_FILE = DATA_DIR / "cleaned_stratified_data.csv"

# 报告目录
REPORTS_DIR = PROJECT_ROOT / "reports"
FIG_DIR = REPORTS_DIR / "figures"        # ← 新增

from pathlib import Path

# 项目根目录
PROJECT_ROOT = Path(r"D:\github offline\User_behavier_analysis\python")

# 数据目录
DATA_DIR = PROJECT_ROOT / "data"

# 原始数据
RAW_DATA = Path(r"D:\github offline\User_behavier_analysis\raw_users_behavier_date\UserBehavior.csv")

# 数据文件
PARQUET_CACHE = DATA_DIR / "UserBehavior.parquet"
STRATIFIED_FILE = DATA_DIR / "stratified_data.csv"
CLEANED_FILE = DATA_DIR / "cleaned_stratified_data.csv"

# 报告目录
REPORTS_DIR = PROJECT_ROOT / "reports"
FIG_DIR = REPORTS_DIR / "figures"        # ← 新增
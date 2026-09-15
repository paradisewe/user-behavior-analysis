
from pathlib import Path

# 原始数据路径
RAW_DATA = Path(r"D:\github offline\User_behavier_analysis\raw_users_behavier_date\UserBehavior.csv")

# 输出数据目录（用户改这里）
DATA_DIR = Path(r"D:\github offline\User_behavier_analysis\python\data")

#加速缓存
PARQUET_CACHE = DATA_DIR / "UserBehavior.parquet"

# 输出文件名
#分层抽样数据
STRATIFIED_FILE = DATA_DIR / "stratified_data.csv"
#完整清洗后的分层抽样数据
CLEANED_FILE = DATA_DIR / "cleaned_stratified_data.csv"
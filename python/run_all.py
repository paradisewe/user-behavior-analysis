"""一键运行完整数据管道：抽样 → 清洗 → 分析 → 可视化。

用法：
    cd python
    python run_all.py
"""

import subprocess
import sys
import time
from pathlib import Path


# 项目根目录（run_all.py 所在目录）
ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"

# 按顺序执行的脚本
STEPS = [
    ("文件侦察", SRC / "file_scout.py"),
    ("分层抽样", SRC / "data_prepare.py"),
    ("正式清洗", SRC / "data_cleaning.py"),
    ("核心分析", SRC / "analysis.py"),
    ("可视化",   SRC / "visualization.py"),
    ("显著性检验", SRC / "significance_test.py"),
    ("RFM 用户分层", SRC / "rfm_analysis.py"),
    ("次日留存分析", SRC / "retention_analysis.py"),
    ("用户路径分析", SRC / "path_analysis.py"),
    ("关联规则挖掘", SRC / "association_analysis.py"),
]


def run_step(name: str, script: Path):
    """运行单个脚本，失败则中断。"""
    print(f"\n{'=' * 60}")
    print(f"▶ {name}：{script.name}")
    print("=" * 60)

    t0 = time.time()
    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=ROOT,
    )
    elapsed = time.time() - t0

    if result.returncode != 0:
        print(f"\n❌ {name} 失败（exit code {result.returncode}）")
        sys.exit(1)

    print(f"\n✅ {name} 完成，耗时 {elapsed:.1f} 秒")


def main():
    print("=" * 60)
    print("淘宝用户行为分析 - 完整数据管道")
    print("=" * 60)
    print(f"Python：{sys.executable}")
    print(f"工作目录：{ROOT}")

    t_total = time.time()
    for name, script in STEPS:
        if not script.exists():
            print(f"\n⚠️ 脚本不存在，跳过：{script}")
            continue
        run_step(name, script)

    print(f"\n{'=' * 60}")
    print(f"✅ 全部完成，总耗时 {(time.time() - t_total) / 60:.1f} 分钟")
    print("=" * 60)


if __name__ == "__main__":
    main()
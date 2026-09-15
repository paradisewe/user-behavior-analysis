from pathlib import Path
import csv


# ---------- 1. 文件大小 ----------
def file_size(file_path: str):
    path = Path(file_path)
    size_bytes = path.stat().st_size
    units = ['B', 'KB', 'MB', 'GB', 'TB']
    size = float(size_bytes)
    for unit in units:
        if size < 1024.0:
            print(f"文件大小：{size:.2f} {unit}")
            return
        size /= 1024.0


# ---------- 2. 探测编码 ----------
def detect_encoding(file_path: str, encoding: str = None) -> str:
    if encoding is not None:
        print(f"指定编码：{encoding}")
        return encoding
    try:
        import chardet
        with open(file_path, 'rb') as f:
            raw = f.read(100_000)  # 读前 100KB 用于探测
        result = chardet.detect(raw)
        detected = result.get('encoding') or 'utf-8'
        confidence = result.get('confidence', 0)
        print(f"探测编码：{detected} (置信度: {confidence:.2%})")
        return detected
    except ImportError:
        print("未安装 chardet，默认使用 utf-8")
        return 'utf-8'
    except Exception as e:
        print(f"编码探测失败 ({e})，默认使用 utf-8")
        return 'utf-8'


# ---------- 3. 看前 n 行(默认5) ----------
def file_head(file_path: str, encoding: str, n: int = 5):
    try:
        with open(file_path, 'r', encoding=encoding) as f:
            for i in range(n):
                line = f.readline()
                if not line:
                    break
                print(f"  {i+1}: {line.rstrip()}")
    except UnicodeDecodeError as e:
        print(f"读取失败，编码错误：{e}")


# ---------- 4. 嗅探分隔符 ----------
def detect_delimiter(file_path: str, encoding: str):
    try:
        with open(file_path, 'r', encoding=encoding) as f:
            sample_text = f.read(5000)
        dialect = csv.Sniffer().sniff(sample_text)
        print(f"  推测分隔符：'{dialect.delimiter}'")
        print(f"  是否有表头：{csv.Sniffer().has_header(sample_text)}")
    except Exception as e:
        print(f"无法自动识别分隔符：{e}")


# ---------- 5. 检查换行符 ----------
def check_newline(file_path: str):
    print("\n行尾符检查：")
    with open(file_path, 'rb') as f:
        raw_head = f.read(1024)
    if b'\r\n' in raw_head:
        print("  检测到 Windows 换行符 (\\r\\n)")
    elif b'\n' in raw_head:
        print("  检测到 Unix 换行符 (\\n)")
    else:
        print("  未检测到常见换行符")


# ---------- 6. 数总行数 ----------
def count_lines(file_path: str, encoding: str) -> int:
    print("\n统计总行数（大文件可能需要几分钟）...")
    line_count = 0
    try:
        with open(file_path, 'r', encoding=encoding) as f:
            for _ in f:
                line_count += 1
        print(f"  总行数：{line_count:,}")
        return line_count
    except UnicodeDecodeError as e:
        print(f" 统计行数时编码错误：{e}")
        return 0


# ---------- 7. 检查文件结尾 ----------
def check_file_end(file_path: str, encoding: str):
    try:
        with open(file_path, 'rb') as f:
            f.seek(-200, 2)  # 跳到末尾前 200 字节
            tail = f.read().decode(encoding, errors='replace')
        last_line = tail.strip().splitlines()[-1][:100] if tail.strip() else "(空)"
        print(f"  最后一行（截取）：{last_line}")
    except Exception as e:
        print(f" 无法读取文件结尾：{e}")


# ---------- 8.总入口：一站式侦察 ----------
def scout_file(file_path: str, encoding: str = None):
    path = Path(file_path)

    # 0. 检查文件是否存在
    if not path.exists():
        print(f"文件不存在：{file_path}")
        return

    print("=" * 60)
    print(f"侦察目标：{path.name}")
    print("=" * 60)

    # 1. 文件大小
    file_size(file_path)

    # 2. 探测编码（结果传给后面所有函数用）
    encoding = detect_encoding(file_path, encoding)

    # 3. 前 5 行
    file_head(file_path, encoding)

    # 4. 分隔符
    detect_delimiter(file_path, encoding)

    # 5. 行尾符
    check_newline(file_path)

    # 6. 总行数
    count_lines(file_path, encoding)

    # 7. 文件结尾
    check_file_end(file_path, encoding)


# ---------- 使用入口 ----------
if __name__ == "__main__":
    from config import RAW_DATA
    scout_file(RAW_DATA)


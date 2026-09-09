"""基础解析工具：字符串/数值转换、图片位置推断、中文日期解析。无依赖。

to_str / safe_float 的唯一归属地，其他模块一律 from parsers import ...。
"""
import re as re_module
from datetime import date, timedelta
from pathlib import Path


def to_str(v):
    if v is None: return ""
    return str(v).strip()


def safe_float(v):
    try: return float(str(v))
    except: return 0.0


def parse_image_position(filename):
    """从文件名推断图片上传位置
    A / {款号}_A → belong=0 基础信息
    B / {款号}_B → belong=1 SKC详情
    C / C1 → belong=2 基础资料第三页
    C2+ → belong=3+ 工艺详情（每张独立槽位）
    """
    import re
    name = Path(filename).stem
    m = re.match(r'.+_(A|B|C\d*)$', name)
    suffix = m.group(1) if m else name

    if suffix == 'A':
        return '0'
    elif suffix == 'B':
        return '1'
    elif suffix == 'C':
        return '2'  # first process image = 基础资料第三页
    elif suffix.startswith('C') and suffix[1:].isdigit():
        n = int(suffix[1:])
        if n == 1:
            return '2'  # C1 → 基础资料第三页
        return str(1 + n)  # C2→3, C3→4, ...
    return '0'


def parse_chinese_date(text):
    """Convert Chinese date expressions to YYYY-MM-DD. Returns (date_str, warning) tuple."""
    text = str(text or "").strip()
    if not text:
        return "", None

    # Already standard format
    if re_module.match(r'^\d{4}-\d{2}-\d{2}$', text):
        return text, None

    today = date.today()

    # Map weekday names
    WEEKDAYS = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6}

    # 下周三, 下周一, 下周五...
    m = re_module.match(r'^下?周?([一二三四五六日])$', text)
    if m:
        target = WEEKDAYS[m.group(1)]
        days_ahead = target - today.weekday()
        if days_ahead <= 0:
            days_ahead += 7
        result = today + timedelta(days=days_ahead)
        return result.strftime("%Y-%m-%d"), f"'{text}' 已自动转换为 {result.strftime('%Y-%m-%d')}"

    # 下周三, 下周五 (explicit 下)
    m = re_module.match(r'^下周([一二三四五六日])$', text)
    if m:
        target = WEEKDAYS[m.group(1)]
        days_ahead = target - today.weekday() + 7
        result = today + timedelta(days=days_ahead)
        return result.strftime("%Y-%m-%d"), f"'{text}' 已自动转换为 {result.strftime('%Y-%m-%d')}"

    # 明天 / 后天 / 大后天
    offset_map = {"明天": 1, "后天": 2, "大后天": 3, "昨天": -1, "前天": -2}
    if text in offset_map:
        result = today + timedelta(days=offset_map[text])
        return result.strftime("%Y-%m-%d"), f"'{text}' 已自动转换为 {result.strftime('%Y-%m-%d')}"

    # 月底
    if text == "月底":
        if today.month == 12:
            result = date(today.year, 12, 31)
        else:
            result = date(today.year, today.month + 1, 1) - timedelta(days=1)
        return result.strftime("%Y-%m-%d"), f"'{text}' 已自动转换为 {result.strftime('%Y-%m-%d')}"

    # 下月初
    if text == "下月初":
        if today.month == 12:
            result = date(today.year + 1, 1, 1)
        else:
            result = date(today.year, today.month + 1, 1)
        return result.strftime("%Y-%m-%d"), f"'{text}' 已自动转换为 {result.strftime('%Y-%m-%d')}"

    # Can't convert
    return text, f"预计完成时间 '{text}' 不是标准日期格式，将原样提交（前端可能无法显示）"

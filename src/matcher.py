"""客户名称模糊匹配（拼音首字母 + 编辑距离）。无依赖。

注意：本模块原样搬迁 submit_excel.py 中的 find_best_customer/_pinyin_first/_edit_distance/_PINYIN_INITIAL，
刻意不整合 customer_matcher.py 的新算法，以保证零行为漂移。
"""
import re

# Simple pinyin first-letter mapping for common Chinese characters
_PINYIN_INITIAL = {
    '哭':'k','喊':'h','空':'k','漫':'m','威':'w','龙':'l','中':'z','心':'x',
    '鸿':'h','利':'l','制':'z','衣':'y','嘉':'j','谦':'q','纺':'f','织':'z',
    '失':'s','物':'w','招':'z','领':'l','四':'s','圈':'q','无':'w','商':'s',
    '标':'b','液':'y','氨':'a','专':'z','用':'y','东':'d','奥':'a','泽':'z',
    '渝':'y','拉':'l','链':'l','仁':'r','信':'x','凯':'k','南':'n','健':'j',
    '力':'l','大':'d','小':'x','新':'x','华':'h','天':'t','地':'d','上':'s',
    '下':'x','左':'z','右':'y','前':'q','后':'h','红':'h','蓝':'l','绿':'lv',
    '黑':'h','白':'b','黄':'h','紫':'z','青':'q','色':'s','金':'j','银':'y',
    '铜':'t','铁':'t','一':'y','二':'e','三':'s','五':'w','六':'l','七':'q',
    '八':'b','九':'j','十':'s','百':'b','千':'q','万':'w',
}


def _pinyin_first(s):
    return ''.join(_PINYIN_INITIAL.get(c, c) for c in s)


def _edit_distance(a, b):
    m, n = len(a), len(b)
    dp = [[0]*(n+1) for _ in range(m+1)]
    for i in range(m+1): dp[i][0] = i
    for j in range(n+1): dp[0][j] = j
    for i in range(1, m+1):
        for j in range(1, n+1):
            cost = 0 if a[i-1] == b[j-1] else 1
            dp[i][j] = min(dp[i-1][j]+1, dp[i][j-1]+1, dp[i-1][j-1]+cost)
    return dp[m][n]


def find_best_customer(input_name, cust_list):
    """Fuzzy match customer name using pinyin + edit distance + case-insensitive"""
    best = None
    best_score = 0
    input_lower = input_name.lower().strip()
    pinyin_input = re.sub(r'[^a-z]', '', _pinyin_first(input_name))

    for c in cust_list:
        cn = c.get("custAbbr", c.get("customerName", ""))
        if not cn:
            continue
        cn_lower = cn.lower().strip()

        # Exact match (case-insensitive)
        if input_lower == cn_lower:
            return {"customerName": cn, "customerCode": c.get("custCode", ""), "score": 1.0}

        # Substring match (case-insensitive)
        if input_lower in cn_lower or cn_lower in input_lower:
            score = 0.85
            if score > best_score:
                best_score = score
                best = {"customerName": cn, "customerCode": c.get("custCode", ""), "score": score}
            continue

        # Pinyin first-letter match
        pinyin_cn = re.sub(r'[^a-z]', '', _pinyin_first(cn))
        if pinyin_input and pinyin_cn and pinyin_input == pinyin_cn:
            score = 0.7
            if score > best_score:
                best_score = score
                best = {"customerName": cn, "customerCode": c.get("custCode", ""), "score": score}
            continue

        # Edit distance (case-insensitive for English names)
        ed = _edit_distance(input_lower, cn_lower)
        max_len = max(len(input_lower), len(cn_lower))
        score = 1.0 - ed / max_len if max_len > 0 else 0
        if score > best_score:
            best_score = score
            best = {"customerName": cn, "customerCode": c.get("custCode", ""), "score": score}

    return best

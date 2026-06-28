"""
客户名称模糊匹配器
- 拼音首字母匹配：处理"空喊中心"→"哭喊中心"这类同音异字变体
- 编辑距离匹配：处理缺字/多字/错字等变体
- 组合评分策略，返回匹配度排序的候选列表

设计理念：
  设计师口语/简称 → 客户库中正确的正式名称+编码
  如："空喊中心" → "哭喊中心 (C0005)"

使用方式:
  from customer_matcher import match_customers
  results = match_customers("空喊中心", customer_list)
  # results: [{"customerName": "哭喊中心", "customerCode": "C0005", "score": 0.92}, ...]
"""

import re
import difflib
from typing import List, Dict, Optional


# ====== 汉字拼音首字母映射表 ======
# 覆盖常见客户名称中可能出现的汉字
# 格式: {汉字: 拼音首字母}
_PINYIN_FIRST_MAP = {
    # A
    '阿': 'a', '爱': 'a', '安': 'a', '奥': 'a', '澳': 'a',
    # B
    '巴': 'b', '百': 'b', '柏': 'b', '版': 'b', '半': 'b', '包': 'b', '宝': 'b',
    '北': 'b', '贝': 'b', '本': 'b', '比': 'b', '必': 'b', '碧': 'b', '标': 'b',
    '博': 'b', '步': 'b', '不': 'b', '部': 'b',
    # C
    '财': 'c', '彩': 'c', '仓': 'c', '草': 'c', '产': 'c', '昌': 'c', '长': 'c',
    '常': 'c', '厂': 'c', '超': 'c', '朝': 'c', '潮': 'c', '车': 'c', '成': 'c',
    '城': 'c', '程': 'c', '诚': 'c', '出': 'c', '初': 'c', '创': 'c', '春': 'c',
    '纯': 'c', '此': 'c', '从': 'c', '翠': 'c', '存': 'c',
    # D
    '达': 'd', '大': 'd', '代': 'd', '单': 'd', '旦': 'd', '当': 'd', '道': 'd',
    '德': 'd', '的': 'd', '登': 'd', '迪': 'd', '地': 'd', '第': 'd', '典': 'd',
    '电': 'd', '调': 'd', '东': 'd', '动': 'd', '都': 'd', '独': 'd', '度': 'd',
    '端': 'd', '对': 'd', '多': 'd',
    # E
    '恩': 'e', '尔': 'e', '二': 'e',
    # F
    '发': 'f', '法': 'f', '凡': 'f', '方': 'f', '房': 'f', '纺': 'f', '飞': 'f',
    '菲': 'f', '分': 'f', '丰': 'f', '风': 'f', '封': 'f', '峰': 'f', '福': 'f',
    '服': 'f', '富': 'f', '复': 'f', '妇': 'f',
    # G
    '改': 'g', '干': 'g', '港': 'g', '高': 'g', '格': 'g', '个': 'g', '给': 'g',
    '工': 'g', '公': 'g', '共': 'g', '购': 'g', '谷': 'g', '故': 'g', '关': 'g',
    '观': 'g', '官': 'g', '管': 'g', '光': 'g', '广': 'g', '规': 'g', '贵': 'g',
    '国': 'g', '果': 'g', '过': 'g',
    # H
    '哈': 'h', '海': 'h', '韩': 'h', '汉': 'h', '行': 'h', '杭': 'h', '航': 'h',
    '好': 'h', '号': 'h', '合': 'h', '和': 'h', '河': 'h', '黑': 'h', '亨': 'h',
    '恒': 'h', '弘': 'h', '红': 'h', '宏': 'h', '洪': 'h', '鸿': 'h', '后': 'h',
    '呼': 'h', '湖': 'h', '互': 'h', '户': 'h', '花': 'h', '华': 'h', '化': 'h',
    '欢': 'h', '环': 'h', '皇': 'h', '黄': 'h', '回': 'h', '会': 'h', '惠': 'h',
    '活': 'h', '火': 'h', '货': 'h',
    # J
    '机': 'j', '基': 'j', '吉': 'j', '极': 'j', '集': 'j', '几': 'j', '计': 'j',
    '记': 'j', '技': 'j', '季': 'j', '济': 'j', '继': 'j', '加': 'j', '家': 'j',
    '嘉': 'j', '价': 'j', '建': 'j', '健': 'j', '江': 'j', '将': 'j', '交': 'j',
    '骄': 'j', '教': 'j', '街': 'j', '节': 'j', '杰': 'j', '捷': 'j', '界': 'j',
    '今': 'j', '金': 'j', '锦': 'j', '尽': 'j', '进': 'j', '近': 'j', '京': 'j',
    '经': 'j', '精': 'j', '景': 'j', '静': 'j', '九': 'j', '久': 'j', '酒': 'j',
    '旧': 'j', '居': 'j', '具': 'j', '聚': 'j', '绝': 'j', '军': 'j', '君': 'j',
    # K
    '卡': 'k', '开': 'k', '康': 'k', '科': 'k', '可': 'k', '克': 'k', '客': 'k',
    '空': 'k', '哭': 'k', '库': 'k', '酷': 'k', '快': 'k', '昆': 'k', '扩': 'k',
    # L
    '拉': 'l', '来': 'l', '兰': 'l', '蓝': 'l', '浪': 'l', '老': 'l', '乐': 'l',
    '雷': 'l', '类': 'l', '李': 'l', '里': 'l', '理': 'l', '力': 'l', '历': 'l',
    '立': 'l', '丽': 'l', '利': 'l', '例': 'l', '连': 'l', '联': 'l', '练': 'l',
    '良': 'l', '林': 'l', '零': 'l', '领': 'l', '流': 'l', '六': 'l', '龙': 'l',
    '楼': 'l', '路': 'l', '旅': 'l', '绿': 'l', '伦': 'l', '罗': 'l',
    # M
    '马': 'm', '买': 'm', '麦': 'm', '满': 'm', '曼': 'm', '毛': 'm', '贸': 'm',
    '美': 'm', '门': 'm', '蒙': 'm', '梦': 'm', '米': 'm', '面': 'm', '民': 'm',
    '名': 'm', '明': 'm', '木': 'm', '目': 'm',
    # N
    '纳': 'n', '南': 'n', '男': 'n', '内': 'n', '能': 'n', '你': 'n', '年': 'n',
    '宁': 'n', '牛': 'n', '农': 'n', '女': 'n', '诺': 'n',
    # O
    '欧': 'o',
    # P
    '拍': 'p', '排': 'p', '派': 'p', '盘': 'p', '培': 'p', '佩': 'p', '配': 'p',
    '朋': 'p', '批': 'p', '皮': 'p', '片': 'p', '品': 'p', '平': 'p', '普': 'p',
    # Q
    '七': 'q', '齐': 'q', '其': 'q', '奇': 'q', '企': 'q', '启': 'q', '气': 'q',
    '汽': 'q', '千': 'q', '前': 'q', '钱': 'q', '强': 'q', '桥': 'q', '青': 'q',
    '轻': 'q', '清': 'q', '情': 'q', '庆': 'q', '秋': 'q', '区': 'q', '趣': 'q',
    '全': 'q', '泉': 'q', '确': 'q', '群': 'q',
    # R
    '然': 'r', '让': 'r', '热': 'r', '人': 'r', '日': 'r', '荣': 'r', '如': 'r',
    '入': 'r', '软': 'r', '锐': 'r', '瑞': 'r', '润': 'r', '若': 'r',
    # S
    '三': 's', '色': 's', '森': 's', '沙': 's', '山': 's', '商': 's', '上': 's',
    '尚': 's', '少': 's', '设': 's', '社': 's', '申': 's', '深': 's', '神': 's',
    '生': 's', '声': 's', '省': 's', '圣': 's', '胜': 's', '盛': 's', '十': 's',
    '石': 's', '时': 's', '实': 's', '食': 's', '史': 's', '始': 's', '世': 's',
    '市': 's', '事': 's', '饰': 's', '试': 's', '是': 's', '收': 's', '手': 's',
    '首': 's', '书': 's', '数': 's', '双': 's', '水': 's', '顺': 's', '说': 's',
    '丝': 's', '思': 's', '斯': 's', '四': 's', '苏': 's', '速': 's', '塑': 's',
    '算': 's', '所': 's', '索': 's',
    # T
    '她': 't', '台': 't', '太': 't', '泰': 't', '唐': 't', '堂': 't', '特': 't',
    '提': 't', '体': 't', '天': 't', '田': 't', '铁': 't', '通': 't', '同': 't',
    '童': 't', '统': 't', '投': 't', '头': 't', '图': 't', '团': 't', '推': 't',
    # W
    '外': 'w', '完': 'w', '玩': 'w', '万': 'w', '王': 'w', '网': 'w', '旺': 'w',
    '威': 'w', '为': 'w', '维': 'w', '伟': 'w', '卫': 'w', '未': 'w', '文': 'w',
    '闻': 'w', '问': 'w', '我': 'w', '无': 'w', '五': 'w', '武': 'w', '物': 'w',
    # X
    '西': 'x', '希': 'x', '系': 'x', '细': 'x', '下': 'x', '先': 'x', '现': 'x',
    '线': 'x', '香': 'x', '想': 'x', '向': 'x', '项': 'x', '象': 'x', '消': 'x',
    '小': 'x', '校': 'x', '协': 'x', '写': 'x', '新': 'x', '信': 'x', '星': 'x',
    '行': 'x', '形': 'x', '性': 'x', '修': 'x', '秀': 'x', '需': 'x', '许': 'x',
    '序': 'x', '宣': 'x', '选': 'x', '学': 'x', '雪': 'x', '讯': 'x',
    # Y
    '雅': 'y', '亚': 'y', '延': 'y', '研': 'y', '颜': 'y', '眼': 'y', '演': 'y',
    '阳': 'y', '养': 'y', '样': 'y', '要': 'y', '药': 'y', '业': 'y', '一': 'y',
    '衣': 'y', '医': 'y', '依': 'y', '宜': 'y', '移': 'y', '已': 'y', '以': 'y',
    '义': 'y', '亿': 'y', '艺': 'y', '议': 'y', '易': 'y', '意': 'y', '因': 'y',
    '音': 'y', '银': 'y', '引': 'y', '饮': 'y', '印': 'y', '应': 'y', '英': 'y',
    '影': 'y', '硬': 'y', '永': 'y', '用': 'y', '优': 'y', '由': 'y', '邮': 'y',
    '油': 'y', '游': 'y', '友': 'y', '有': 'y', '又': 'y', '于': 'y', '鱼': 'y',
    '娱': 'y', '语': 'y', '玉': 'y', '预': 'y', '域': 'y', '元': 'y', '园': 'y',
    '原': 'y', '源': 'y', '远': 'y', '约': 'y', '月': 'y', '越': 'y', '云': 'y',
    '运': 'y',
    # Z
    '在': 'z', '再': 'z', '展': 'z', '战': 'z', '张': 'z', '章': 'z', '掌': 'z',
    '招': 'z', '找': 'z', '者': 'z', '这': 'z', '真': 'z', '整': 'z', '正': 'z',
    '证': 'z', '之': 'z', '支': 'z', '知': 'z', '织': 'z', '直': 'z', '职': 'z',
    '制': 'z', '质': 'z', '智': 'z', '中': 'z', '终': 'z', '众': 'z', '重': 'z',
    '周': 'z', '州': 'z', '主': 'z', '住': 'z', '注': 'z', '专': 'z', '转': 'z',
    '装': 'z', '资': 'z', '自': 'z', '总': 'z', '走': 'z', '组': 'z', '最': 'z',
    '尊': 'z', '作': 'z', '做': 'z', '座': 'z',
}


def _get_pinyin_first_letters(text: str) -> str:
    """
    获取中文文本的拼音首字母串
    例: "哭喊中心" → "khzx"
         "空喊中心" → "khzx"  (同音异字，首字母相同)
    """
    result = []
    for ch in text:
        if '\u4e00' <= ch <= '\u9fff':  # 中文字符范围
            result.append(_PINYIN_FIRST_MAP.get(ch, ch.lower()))
        elif ch.isalpha():
            result.append(ch.lower())
        # 忽略数字、符号、空格
    return ''.join(result)


def _normalize(text: str) -> str:
    """文本归一化：去除空格/标点，全角转半角，转小写"""
    if not text:
        return ""
    # 全角转半角
    result = []
    for ch in text:
        code = ord(ch)
        if 0xFF01 <= code <= 0xFF5E:
            result.append(chr(code - 0xFEE0))
        elif code == 0x3000:  # 全角空格
            result.append(' ')
        else:
            result.append(ch)
    text = ''.join(result)
    # 去除空格和标点
    text = re.sub(r'[\s\-\_\(\)\（\）\,\.\，\。\、\·]', '', text)
    return text.lower()


def _str_similarity(a: str, b: str) -> float:
    """计算两个字符串的编辑距离相似度 (0~1)"""
    return difflib.SequenceMatcher(None, a, b).ratio()


def _pinyin_match_score(input_name: str, candidate_name: str) -> float:
    """
    拼音首字母匹配得分 (0~1)
    - 完全匹配: 1.0
    - 一个为另一个的子串: 0.8
    - 部分重叠: 按比例
    - 无重叠: 0.0
    """
    inp_py = _get_pinyin_first_letters(input_name)
    cand_py = _get_pinyin_first_letters(candidate_name)

    if not inp_py or not cand_py:
        return 0.0

    if inp_py == cand_py:
        return 1.0

    if inp_py in cand_py or cand_py in inp_py:
        return 0.8

    # 计算最长公共子序列占比
    matcher = difflib.SequenceMatcher(None, inp_py, cand_py)
    return matcher.ratio()


def match_customers(
    input_name: str,
    customer_list: List[Dict],
    min_score: float = 0.4,
    max_results: int = 10
) -> List[Dict]:
    """
    模糊匹配客户名称

    参数:
        input_name: 设计师输入的客户名称（如 "空喊中心"）
        customer_list: API返回的客户列表，每项含 customerName/customerCode
        min_score: 最低匹配分数阈值（0~1），低于此值不返回
        max_results: 最多返回多少条结果

    返回:
        按匹配得分降序排列的匹配列表
        [{"customerName": "哭喊中心", "customerCode": "C0005", "score": 0.92}, ...]

    评分策略:
        - 编辑距离相似度 权重 40%
        - 拼音首字母匹配  权重 60%
        - 最终 score = similarity*0.4 + pinyin_score*0.6
    """
    if not input_name or not customer_list:
        return []

    norm_input = _normalize(input_name)

    results = []
    for c in customer_list:
        cn = c.get("customerName", c.get("name", ""))
        if not cn:
            continue

        norm_cn = _normalize(cn)

        # 编辑距离相似度
        sim_score = _str_similarity(norm_input, norm_cn)

        # 拼音首字母匹配
        py_score = _pinyin_match_score(input_name, cn)

        # 组合评分: 拼音首字母权重更高（处理同音异字）
        combined = sim_score * 0.4 + py_score * 0.6

        if combined >= min_score:
            results.append({
                "customerName": cn,
                "customerCode": c.get("customerCode", ""),
                "score": round(combined, 4),
                "raw": c,  # 保留原始数据
            })

    # 按分数降序
    results.sort(key=lambda x: x["score"], reverse=True)

    return results[:max_results]


def find_best_match(
    input_name: str,
    customer_list: List[Dict],
    min_score: float = 0.6
) -> Optional[Dict]:
    """
    找出最佳匹配（仅在得分足够高时返回单个结果）

    适用场景：提交阶段兜底匹配，不打扰用户
    返回: {"customerName": "哭喊中心", "customerCode": "C0005", "score": 0.92} 或 None
    """
    matches = match_customers(input_name, customer_list, min_score=min_score, max_results=1)
    return matches[0] if matches else None


def list_all_customers(customer_list: List[Dict]) -> List[Dict]:
    """
    列出所有客户（用于无匹配时展示）
    返回: [{"customerName": "哭喊中心", "customerCode": "C0005"}, ...]
    """
    return [
        {
            "customerName": c.get("customerName", c.get("name", "")),
            "customerCode": c.get("customerCode", ""),
        }
        for c in customer_list
        if c.get("customerName") or c.get("name")
    ]


# ====== 自测 ======
if __name__ == "__main__":
    # 模拟客户库
    test_customers = [
        {"customerName": "哭喊中心", "customerCode": "C0005"},
        {"customerName": "鸿利制衣", "customerCode": "C0006"},
        {"customerName": "嘉谦纺织", "customerCode": "C0001"},
        {"customerName": "空港服装有限公司", "customerCode": "C0012"},
        {"customerName": "测试客户", "customerCode": "C9999"},
    ]

    test_cases = [
        ("空喊中心", "同音异字: 空喊→哭喊"),
        ("哭喊中心", "精确匹配"),
        ("空喊", "简称"),
        ("鸿利", "部分匹配"),
        ("khzx", "拼音缩写输入"),
        ("不存在的客户", "无匹配"),
    ]

    print("=" * 60)
    print("客户名称模糊匹配测试")
    print("=" * 60)

    for inp, desc in test_cases:
        print(f"\n[测试] 输入: \"{inp}\" ({desc})")
        results = match_customers(inp, test_customers)
        if results:
            for r in results:
                bar = "█" * int(r["score"] * 20)
                print(f"  → {r['customerName']} ({r['customerCode']}) "
                      f"得分: {r['score']:.3f} {bar}")
        else:
            print(f"  → 无匹配结果 (阈值: 0.4)")

    print("\n" + "=" * 60)
    print("全部客户列表:")
    for c in list_all_customers(test_customers):
        print(f"  {c['customerName']} ({c['customerCode']})")

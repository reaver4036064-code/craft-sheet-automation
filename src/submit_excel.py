"""
Fixed parser for the actual test Excel template layout.
Columns: A=款号 B=value C=空 D=空 E=label F=value
"""
import time, json, requests
import re as re_module
from datetime import date, timedelta
import openpyxl
from pathlib import Path
import os, sys

BASE = "https://mctwo.fsjqfz.xyz/makeCloth"

# === Identity management (persisted to .identity.json) ===
SCRIPT_DIR = Path(__file__).resolve().parent
IDENTITY_FILE = SCRIPT_DIR / ".identity.json"

USERNAME = os.getenv("MC_USERNAME", "")
PASSWORD = os.getenv("MC_PASSWORD", "")
USER_REALNAME = None
USER_DESIGNER_ID = None

def load_identity():
    if IDENTITY_FILE.exists():
        try:
            return json.loads(IDENTITY_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return None

def save_identity(data):
    IDENTITY_FILE.parent.mkdir(parents=True, exist_ok=True)
    IDENTITY_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def ensure_identity():
    global USER_REALNAME, USER_DESIGNER_ID, USERNAME, PASSWORD
    saved = load_identity()
    if saved:
        USER_REALNAME = saved.get("realname")
        USER_DESIGNER_ID = saved.get("designer_id")
        USERNAME = saved.get("username", USERNAME)
        PASSWORD = saved.get("password", PASSWORD)
        if USER_REALNAME and USER_DESIGNER_ID:
            return True
    # First run: ask
    print("\n" + "="*50)
    print("首次使用 — 请提供身份信息（仅需一次）")
    print("="*50)
    try:
        name = input("请输入您的真实姓名: ").strip()
        sys_user = input("请输入嘉谦系统账号: ").strip()
        sys_pass = input("请输入嘉谦系统密码: ").strip()
    except (EOFError, KeyboardInterrupt):
        print("取消")
        return False
    if not name or not sys_user or not sys_pass:
        print("姓名、账号、密码不能为空")
        return False
    USERNAME = sys_user
    PASSWORD = sys_pass
    try:
        token = login()
    except Exception:
        print(f"账号 \"{sys_user}\" 登录失败")
        return False
    # Lookup userId
    try:
        r = requests.get(f"{BASE}/dept/getUserList/name",
            params={"deptName": "设计部"}, headers=api_headers(token))
        data = r.json()
        if data.get("success"):
            for u in data.get("data", {}).get("items", []):
                if u.get("userName") == name:
                    USER_REALNAME = name
                    USER_DESIGNER_ID = str(u["userId"])
                    save_identity({"realname": name, "designer_id": str(u["userId"]),
                        "username": USERNAME, "password": PASSWORD})
                    print(f"身份验证通过: {name} (ID={USER_DESIGNER_ID})")
                    return True
    except Exception as e:
        print(f"查询失败: {e}")
    print(f"设计师 \"{name}\" 未在系统中注册，请联系管理员")
    return False

def login():
    ts = int(time.time() * 1000)
    r = requests.post(f"{BASE}/colorimeter/index/login?time={ts}",
        json={"loginName": USERNAME, "password": PASSWORD, "deviceCode": None, "loginType": "erp-pc"},
        headers={"Content-Type": "application/json"})
    return r.json()["data"]["token"]

def api_headers(token):
    return {"Content-Type": "application/json;charset=UTF-8", "token": token, "Accept": "application/json, text/plain, */*"}

def upload_image(token, path):
    with open(path, "rb") as f:
        r = requests.post(f"{BASE}/business/upload/img",
            files={"img": ("craft.jpg", f, "image/jpeg")}, headers={"token": token})
    d = r.json()
    if d.get("success"):
        return d["data"]["url"]
    raise Exception(f"Upload failed: {d}")

def get_labels(token):
    r = requests.post(f"{BASE}/business/markLabel/select", json={}, headers=api_headers(token))
    return r.json().get("data", {}).get("list", [])

def get_fabrics(token):
    """Get all fabrics from the system for lookup"""
    r = requests.post(f"{BASE}/colorimeter/bFabric/selectFabricList", json={}, headers=api_headers(token))
    return r.json().get("data", {}).get("list", [])

def get_customers(token):
    r = requests.get(f"{BASE}/business/customer/public", headers=api_headers(token))
    return r.json().get("data", {}).get("list", [])

def to_str(v):
    if v is None: return ""
    return str(v).strip()

def safe_float(v):
    try: return float(str(v))
    except: return 0.0

# === Customer matching ===
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
import re

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

def parse_image_position(filename):
    """从文件名推断图片上传位置
    A / {款号}_A → belong=0 基础信息
    B / {款号}_B → belong=1 SKC详情
    C → belong=2, C1→belong=2, C2→belong=3, Cn→belong=n+1 工艺详情（每张一个belong）
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
        return '2'  # first process image
    elif suffix.startswith('C') and suffix[1:].isdigit():
        n = int(suffix[1:])
        return str(1 + n)  # C1→2, C2→3, C3→4...
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
    
    # 下周X
    m = re_module.match(r'^下?周?([一二三四五六日])$', text)
    
    # Can't convert
    return text, f"预计完成时间 '{text}' 不是标准日期格式，将原样提交（前端可能无法显示）"


def submit_one(excel_path, image_paths):
    # === Verify/collect designer identity (MUST be before login) ===
    if not ensure_identity():
        return {"success": False, "msg": "identity_not_verified"}

    token = login()
    print(f"[OK] Logged in")

    # Upload images with position mapping
    d_upload = []
    prev_belong = None
    for p in image_paths:
        url = upload_image(token, p)
        belong = parse_image_position(str(p))
        if belong == prev_belong:
            time.sleep(1.5)
        d_upload.append({"belong": belong, "type": str(len(d_upload)), "url": url})
        print(f"[OK] Image: {Path(p).name} -> belong={belong}: {url}")
        prev_belong = belong

    # Map belong to type (new API: 0=主图,1=基础资料,2=基础资料第三页,3=工艺详情,4=纸样文件,5=纸样png,6=绣花工艺图,7=印花工艺图)
    for u in d_upload:
        b = int(u["belong"])
        if b == 0:
            u["type"] = "0"   # 主图
        elif b == 1:
            u["type"] = "1"   # 基础资料图(SKC详情)
        else:
            u["type"] = "3"   # 工艺详情

    # Read Excel
    wb = openpyxl.load_workbook(excel_path, data_only=True)
    ws = wb.active

    # === Parse basic info ===
    # B6=款号, F6=需求类型, B7=衣服类型, F7=款式, B8=客户名称
    # B9=打版件数, F9=版型, B10=烫唛
    
    item_num = to_str(ws["B6"].value)      # 款号
    need_type = to_str(ws["F6"].value)     # ODM/ODM/OBM
    cloth_type = to_str(ws["B7"].value)     # T/W/J/K/...
    style = to_str(ws["F7"].value)          # 款式名
    customer_name = to_str(ws["B8"].value)  # 客户
    num_val = to_str(ws["B9"].value) or "1" # 打版件数
    layout = to_str(ws["F9"].value)         # 版型
    mark_name = to_str(ws["B10"].value)     # 烫唛
    
    design_name = USER_REALNAME
    finish_time_raw = to_str(ws["F10"].value) or ""
    finish_time, _date_warning = parse_chinese_date(finish_time_raw)

    print(f"  ItemNum: {item_num}, NeedType: {need_type}, ClothType: {cloth_type}")
    print(f"  Style: {style}, Customer: {customer_name}, Num: {num_val}")

    # Match customer using pinyin + edit distance fuzzy matching
    customer_code = ""
    matched_customer_name = customer_name  # may be corrected by match
    if customer_name:
        try:
            custs = get_customers(token)
            if custs:
                best = find_best_customer(customer_name, custs)
                if best and best["score"] >= 0.4:
                    # Use the system's official customer name (from dropdown)
                    matched_customer_name = best["customerName"]
                    customer_code = best["customerCode"] or ""
                    if matched_customer_name != customer_name:
                        print(f"  [CUSTOMER] Matched: '{customer_name}' -> '{matched_customer_name}' ({customer_code}) score={best['score']:.2f}")
                    else:
                        print(f"  [CUSTOMER] Exact match: '{matched_customer_name}' ({customer_code})")
                elif best and best["score"] < 0.4:
                    print(f"  [CUSTOMER] Low confidence match, fallback to manual input: '{customer_name}' (best='{best['customerName']}' score={best['score']:.2f})")
                else:
                    print(f"  [CUSTOMER] No match found, using manual input: '{customer_name}'")
        except Exception as e:
            print(f"  [CUSTOMER] Matching failed: {e}")
        except: pass

    # Match label
    mark_id = ""
    labels = get_labels(token)
    for l in labels:
        if mark_name and mark_name in l.get("name", ""):
            mark_id = str(l["id"])
            break

    # === Parse fabrics ===
    # Detect "SKU编号" header row to find section start (handles variant Excel layouts)
    fabric_db = get_fabrics(token)
    
    sku_groups = {}
    sku_info = {}
    
    # Find SKU section start and build column map from header row
    sku_header_row = 21
    col_map = {}  # header_name -> col_index (1-based)
    for r in range(20, 30):
        if to_str(ws.cell(r, 1).value) == "SKU编号":
            sku_header_row = r
            # Scan header row to map column positions
            for c in range(1, 30):
                h = to_str(ws.cell(r, c).value)
                if h:
                    col_map[h] = c
            break
    
    for r in range(sku_header_row + 1, sku_header_row + 60):
        sku_raw = ws.cell(r, 1).value  # A col = SKU编号
        color = to_str(ws.cell(r, col_map.get("颜色", 2)).value)
        size = to_str(ws.cell(r, col_map.get("尺码", 3)).value)
        qty = to_str(ws.cell(r, col_map.get("件数", 4)).value)
        cloth = to_str(ws.cell(r, col_map.get("布类", 5)).value)
        pn = to_str(ws.cell(r, col_map.get("面料编号", 6)).value)
        cc = to_str(ws.cell(r, col_map.get("色号", 7)).value)
        cn = to_str(ws.cell(r, col_map.get("颜色名", 8)).value)
        # New v6 fields (cols 9-18; 是否使用库存 removed)
        is_rib = to_str(ws.cell(r, col_map.get("是否罗纹", 9)).value)
        width = to_str(ws.cell(r, col_map.get("幅宽/CM", 10)).value or ws.cell(r, col_map.get("幅宽", 99)).value)
        weight = to_str(ws.cell(r, col_map.get("克重", 11)).value)
        supplier = to_str(ws.cell(r, col_map.get("供应商", 12)).value)
        component = to_str(ws.cell(r, col_map.get("成分", 13)).value)
        product_name = to_str(ws.cell(r, col_map.get("品名", 14)).value)
        meter_len = to_str(ws.cell(r, col_map.get("采购米长", 15)).value)
        meter_price = to_str(ws.cell(r, col_map.get("采购金额", 16)).value)
        buyer = to_str(ws.cell(r, col_map.get("采购人", 17)).value)
        arrive_time = to_str(ws.cell(r, col_map.get("要求到货时间", 18)).value)
        
        # Skip header/non-data rows
        sku = to_str(sku_raw)
        # Stop at section boundary (empty row after data, or next section header)
        if sku.startswith("▼"):
            break  # next section, stop parsing SKU
        if not sku:
            if not pn or not cloth:
                continue  # empty row, skip
            # Continuation row: use last SKU
        elif not sku.isdigit():
            if pn and cloth:
                continue  # Probably header like "SKU编号"
            continue  # Non-numeric, non-data
        
        if sku.isdigit():
            sn = sku
            if sn not in sku_groups:
                sku_groups[sn] = []
            sku_info[sn] = {"color": color, "size": size, "qty": qty or sku_info.get(sn, {}).get("qty", "1")}
        elif not sku:
            sn = list(sku_groups.keys())[-1] if sku_groups else "1"
        else:
            continue
        
        if pn and cloth:
            if sn not in sku_groups:
                sku_groups[sn] = []
                sku_info[sn] = {"color": color, "size": size, "qty": qty}
            sku_groups[sn].append({
                "clothType": cloth, "productNo": pn, "color": cc, "colorName": cn,
                "width": width, "weight": weight, "supplier": supplier,
                "component": component, "productName": product_name or "",
                "meterLen": meter_len, "meterPrice": meter_price,
                "buyer": buyer, "arriveTime": arrive_time,
                "isRib": is_rib,
            })

    # Build designColors - one SKC per SKU, all fabrics in one SKC
    design_colors = []
    for sn in sorted(sku_groups.keys()):
        info = sku_info.get(sn, {})
        fabrics = sku_groups[sn]
        if not fabrics:
            continue
        
        fabric_list = []
        for f_raw in fabrics:
            # Look up fabric details from API
            pn = f_raw["productNo"]
            detail = {}
            for fd in fabric_db:
                if fd.get("productNo") == pn:
                    detail = fd
                    break
            
            fabric_list.append({
                "productNo": pn,
                "color": f_raw["color"],
                "colorName": f_raw.get("colorName", ""),
                "clothType": f_raw["clothType"],
                "cgBy": f_raw.get("buyer") or USER_REALNAME,
                "supName": f_raw.get("supplier") or detail.get("supName", ""),
                "buffon": f_raw.get("width") or detail.get("buffon", ""),
                "grem": f_raw.get("weight") or detail.get("grem", ""),
                "component": f_raw.get("component") or detail.get("component", ""),
                "productName": f_raw.get("productName") or detail.get("productName", ""),
                "thread": "0",
                "isUsed": "0",
                "price": safe_float(f_raw.get("meterPrice", 0)),
                "arrivedTime": f_raw.get("arriveTime", ""),
                "type": "",                                          # [NEW]
                "colorTypeVOS": [{                                   # [NEW]
                    "color": f_raw["color"],
                    "colorName": f_raw.get("colorName", ""),
                }],
            })

        color_val = info.get("color", "")
        size_val = info.get("size", "L")
        design_colors.append({
            "color": color_val,
            "sku": f"{color_val}_{size_val}",  # unique SKU identifier
            "skuName": f"SKU{sn}",
            "size": size_val,
            "num": info.get("qty", "1"),
            "fabricList": fabric_list,
        })

    print(f"  Fabrics: {len(design_colors)} SKU(s), total {sum(len(dc['fabricList']) for dc in design_colors)} fabrics")

    # === Parse works/process ===
    # Scan rows 14-21 for process data (flexible positioning)
    works = []
    for r in range(14, 30):
        name = to_str(ws.cell(r, 2).value)
        if name and not name.startswith("▼"):
            works.append({"cate": "0", "status": "0", "name": name, "sort": len(works)})

    print(f"  Works: {len(works)} processes")

    # === Parse auxiliaries ===
    auxiliaries = []
    # Find "辅料名称" header row and build column map
    aux_start = 32
    aux_col = {}  # header -> col index
    for r in range(30, 45):
        if to_str(ws.cell(r, 2).value) == "辅料名称":
            aux_start = r + 1
            # Map columns from header row
            for c in range(1, 30):
                h = to_str(ws.cell(r, c).value)
                if h:
                    aux_col[h] = c
            break
    
    for r in range(aux_start, aux_start + 30):
        name = to_str(ws.cell(r, aux_col.get("辅料名称", 2)).value)
        if not name:
            continue
        auxiliaries.append({
            "name": name,
            "type": to_str(ws.cell(r, aux_col.get("规格型号", 3)).value),
            "unit": to_str(ws.cell(r, aux_col.get("单位", 6)).value) or "个",
            "usageAct": to_str(ws.cell(r, aux_col.get("用量", 5)).value),
            "price": safe_float(ws.cell(r, aux_col.get("采购单价", 7)).value),
            "supName": to_str(ws.cell(r, aux_col.get("供应商", 8)).value),
            "phone": to_str(ws.cell(r, aux_col.get("联系方式", 9)).value),
            "cgBy": to_str(ws.cell(r, aux_col.get("采购人", 11)).value) or USER_REALNAME,
            "color": to_str(ws.cell(r, aux_col.get("颜色", 4)).value),
            "arrivedTime": "",
            "isUsed": 0,
            "fCode": "",
            "supListVOS": [{                                    # [NEW]
                "supName": to_str(ws.cell(r, aux_col.get("供应商", 8)).value),
                "price": safe_float(ws.cell(r, aux_col.get("采购单价", 7)).value),
            }],
        })

    print(f"  Auxiliaries: {len(auxiliaries)}")

    # === Build payload ===
    payload = {
        "code": "", "vNumber": "",
        "itemNum": item_num,
        "needType": need_type,
        "customerName": matched_customer_name,
        "customerCode": customer_code,
        "customerLogo": "",                                     # [NEW]
        "clothType": cloth_type,
        "style": style,
        "layout": layout,
        "designName": design_name,
        "finishTime": finish_time,
        "version": "",
        "userId": USER_DESIGNER_ID,
        "num": num_val,
        "markName": mark_name,
        "markId": mark_id,
        "sewing": "",
        "outProcess": "",                                       # [NEW]
        "postProcess": "",                                      # [NEW]
        "sewingProcess": "",                                    # [NEW]
        "patternBy": "",                                        # [NEW]
        "cutBy": "",                                            # [NEW]
        "sewingBy": "",                                         # [NEW]
        "patternTime": "",                                      # [NEW]
        "cutTime": "",                                          # [NEW]
        "sewingTime": "",                                       # [NEW]
        "status": 0,                                            # [NEW]
        "dUploadUrls": d_upload,
        "designColors": design_colors,
        "works": works,
        "auxiliaries": auxiliaries,
        "modifications": [],
    }

    print(f"\n[DEBUG] dUploadUrls: {len(d_upload)} images (types: {[u['type'] for u in d_upload]}, belongs: {[u['belong'] for u in d_upload]})")

    # === Pre-submit validation ===
    errors = []    # blocking: must fix before submit
    warnings = []  # non-blocking: user can skip

    # Date format warning (from parse_chinese_date earlier)
    if _date_warning:
        warnings.append(_date_warning)

    # Rule 1: 打版件数 = total SKU quantities
    total_qty = sum(int(sku_info.get(sn, {}).get("qty", 0) or 0) for sn in sku_groups)
    expected_qty = int(num_val or 0)
    if expected_qty > 0 and total_qty != expected_qty:
        errors.append(f"打版件数({expected_qty}件)与SKU件数总和({total_qty}件)不一致，必须修正")

    # Rule 2 & 3: Check each fabric row
    for sn in sku_groups:
        for f in sku_groups[sn]:
            pn = f.get("productNo", "")
            cc = f.get("color", "")
            cn = f.get("colorName", "")
            if pn and (not cc or not cn):
                errors.append(f"SKU{sn} 面料编号 {pn} 缺少色号/颜色名（必须填写）")

            # Rule 3: fabric not in API database → check manual fields
            if pn:
                found_in_db = any(fd.get("productNo") == pn for fd in fabric_db)
                if not found_in_db:
                    missing_fields = []
                    if not f.get("isRib"):
                        missing_fields.append("是否罗纹")
                    if not f.get("width"):
                        missing_fields.append("幅宽/CM")
                    if not f.get("weight"):
                        missing_fields.append("克重")
                    if not f.get("supplier"):
                        missing_fields.append("供应商")
                    if missing_fields:
                        warnings.append(f"SKU{sn} 面料编号 {pn} 未在系统匹配到，请填写: {', '.join(missing_fields)}")

    if errors:
        print(f"\n{'='*50}")
        print(f"❌ 以下 {len(errors)} 项必须修正后才能提交：")
        for e in errors:
            print(f"  • {e}")
        print(f"{'='*50}")
        wb.close()
        return {"success": False, "msg": "validation_errors", "errors": errors}

    if warnings:
        print(f"\n{'='*50}")
        print(f"⚠️ 以下 {len(warnings)} 项需要确认：")
        for w in warnings:
            print(f"  • {w}")
        print(f"{'='*50}")
        try:
            ans = input("是否忽略以上警告继续提交？(y=继续 / n=取消): ").strip().lower()
            if ans != 'y':
                wb.close()
                return {"success": False, "msg": "user_cancelled"}
        except (EOFError, KeyboardInterrupt):
            wb.close()
            return {"success": False, "msg": "user_cancelled"}

    # === Submit ===
    r = requests.post(f"{BASE}/business/design/insertDesign", json=payload, headers=api_headers(token))
    result = r.json()
    
    if result.get("success"):
        info = result.get("data", {}).get("info", {})
        auto_num = info.get("itemNum") or info.get("code") or ""
        design_id = info.get("id", "")
        print(f"\n  [OK] Created! ID={design_id} itemNum={auto_num}")

        # Rename logic:
        # - item_num filled in Excel → use it, rename only short-named images (A.png, C1.png...)
        # - item_num empty → auto-generate from system, rename everything
        style_num = item_num or auto_num
        should_rename = bool(style_num)

        # Check if images need renaming (short names like A.png, C1.png without prefix)
        images_need_rename = False
        for p in image_paths:
            stem = Path(p).stem
            # Short names: A, B, C, C1, C2... (1-3 chars, no prefix)
            if len(stem) <= 3:
                images_need_rename = True
                break

        if should_rename and images_need_rename:
            print(f"  [RENAME] Style number: {style_num}")
            
            xls_p = Path(excel_path)
            folder_p = xls_p.parent
            
            # Always rename Excel to {style_num}.xlsx
            new_xls = xls_p.with_name(f"{style_num}.xlsx")
            if xls_p.name != new_xls.name:
                xls_p.rename(new_xls)
                print(f"  [RENAME] Excel: {xls_p.name} -> {new_xls.name}")
                result["renamed"] = True
            
            # Update Excel B6 if auto-generated
            if not item_num:
                wb2 = openpyxl.load_workbook(new_xls)
                ws2 = wb2.active
                ws2["B6"] = style_num
                wb2.save(new_xls)
                wb2.close()
                print(f"  [RENAME] Updated B6 in Excel: {style_num}")

            # Rename images to {style_num}_{label}.png
            for p in image_paths:
                ip = Path(p)
                belong = parse_image_position(str(p))
                if belong == '0':
                    label = 'A'
                elif belong == '1':
                    label = 'B'
                else:
                    import re
                    m = re.match(r'.*_?([A-Z]\d*)$', ip.stem)
                    label = m.group(1) if m else ip.stem
                new_name = f"{style_num}_{label}{ip.suffix}"
                if ip.name != new_name:
                    new_ip = ip.with_name(new_name)
                    ip.rename(new_ip)
                    print(f"  [RENAME] Image: {ip.name} -> {new_ip.name}")

            # Rename folder to {style_num}
            new_folder = folder_p.with_name(style_num)
            if folder_p.name != style_num:
                try:
                    folder_p.rename(new_folder)
                    print(f"  [RENAME] Folder: {folder_p.name} -> {new_folder.name}")
                except Exception as e:
                    print(f"  [RENAME] Folder rename failed: {e}")

            result["auto_style_number"] = style_num
    else:
        print(f"\n  [FAIL] {result.get('msg', '')[:300]}")

    wb.close()
    return result


if __name__ == "__main__":
    import sys
    TEST_DIR = Path(r"C:\Users\Administrator\Desktop\测试")
    results = []
    
    for child in sorted(TEST_DIR.iterdir()):
        if not child.is_dir():
            continue
        xls = list(child.glob("*.xlsx"))
        imgs = list(child.glob("*.png")) + list(child.glob("*.jpg"))
        if not xls or not imgs:
            continue
        
        print(f"\n{'='*60}")
        print(f"Processing: {child.name}")
        try:
            r = submit_one(xls[0], imgs)
            results.append({"folder": child.name, "success": r.get("success", False), "result": r})
        except Exception as e:
            print(f"[ERROR] {e}")
            import traceback
            traceback.print_exc()
            results.append({"folder": child.name, "success": False, "error": str(e)})
        time.sleep(2)

    print(f"\n{'='*60}")
    for r in results:
        s = "OK" if r.get("success") else "FAIL"
        print(f"  [{s}] {r['folder']}")

"""工艺单字段映射器 — 将对话填表数据 → insertDesign API 请求体"""

from typing import Dict, Any, List, Optional


def map_excel_to_api_payload(
    data: Dict[str, Any],
    image_urls: List[str],
    customer_code: str = "",
    customer_name: str = "",
    designer_id: str = "",
    designer_name: str = "",
    mark_id: str = "",
    mark_name: str = "",
    purchaser: str = "",            # 可选：工艺单指定的采购人，为空则用设计师
) -> Dict[str, Any]:
    """
    Excel 解析结果 → insertDesign API 请求体

    必填字段：itemNum, customerName, customerCode, clothType, style,
             userId, num, markName, markId, sewing, dUploadUrls, designColors

    采购人规则：purchaser 为空 → 默认同设计师；不为空 → 使用指定采购人
    """

    # 采购人：优先OCR指定的，否则默认同设计师
    cg_by = purchaser if purchaser else designer_name

    # --- 图片信息（必填） ---
    d_upload_urls = []
    for idx, url in enumerate(image_urls):
        d_upload_urls.append({
            "belong": "0",
            "type": "0" if idx == 0 else "1",   # 0=主图, 1=基础资料图
            "url": url,
        })

    # --- 面料信息 designColors（必填） ---
    # ★ 重要：一款衣服用多种面料 → 1个SKU + N种面料的fabricList
    design_colors = []
    fabrics = data.get("fabrics", [])
    sample_size = data.get("sample_size", "L")
    sample_quantity = data.get("sample_quantity", 1)

    # 所有有效面料汇总到一个SKU下
    all_fabrics = []
    for f in fabrics:
        if not f.get("name"):
            continue
        all_fabrics.append({
            "productNo": f.get("name", ""),
            "color": f.get("color", ""),
            "colorName": f.get("color", ""),
            "buffon": str(f.get("width", "")),
            "grem": str(f.get("weight", "")),
            "supName": "嘉谦纺织",
            "component": "",
            "productName": f.get("name", ""),
            "arrivedTime": "",
            "thread": "0",
            "isUsed": "0",
            "price": 0,
            "clothType": f.get("code", "A"),
            "cgBy": cg_by,
        })

    if all_fabrics:
        # 取第一个面料的颜色作为SKU颜色
        first_color = fabrics[0].get("color", "") if fabrics else ""
        design_colors.append({
            "color": first_color,
            "sku": data.get("style_number", ""),
            "size": sample_size,
            "num": str(sample_quantity),
            "fabricList": all_fabrics,   # ★ 所有面料在一个SKU下
        })
    else:
        design_colors.append({
            "color": "",
            "sku": "",
            "size": sample_size,
            "num": "1",
            "fabricList": [{
                "productNo": "", "color": "", "colorName": "",
                "buffon": "", "grem": "", "supName": "",
                "productName": "", "price": 0, "clothType": "A",
                "cgBy": cg_by,
            }],
        })

    # --- 工艺制作 works（必填） ---
    # ★ 所有工艺数据统一填入「工艺制作」栏 (cate=0)
    works = []
    process_notes = data.get("process_notes", "")

    if process_notes:
        lines = []
        raw = process_notes.strip()
        for line in raw.split("\n"):
            line = line.strip()
            if not line:
                continue
            if len(line) > 80:
                import re
                sub_lines = re.split(r'[；;，,]', line)
                for sl in sub_lines:
                    sl = sl.strip()
                    if sl:
                        lines.append(sl)
            else:
                lines.append(line)
        for i, name in enumerate(lines):
            works.append({
                "cate": "0",        # ★ 统一：工艺制作
                "status": "0",
                "name": name,
                "sort": i,
            })

    # ★ 车缝工艺 → 也合并到工艺制作 (cate=0)
    sewing_val = data.get("sewing_process", "")
    if sewing_val:
        works.append({
            "cate": "0",
            "status": "0",
            "name": sewing_val,
            "sort": len(works),
        })

    # ★ 成衣工艺 → 也合并到工艺制作 (cate=0)
    garment_val = data.get("garment_process", "")
    if garment_val:
        works.append({
            "cate": "0",
            "status": "0",
            "name": garment_val,
            "sort": len(works),
        })

    # --- 辅料信息 auxiliaries（选填） ---
    auxiliaries = []
    trims = data.get("trims", [])
    for t in trims:
        if not t.get("name"):
            continue
        # usageAct 必须是数字（BigDecimal）
        usage_val = t.get("usage", 1)
        try:
            usage_val = float(usage_val)
        except (ValueError, TypeError):
            usage_val = 1.0

        # 采购单价
        price_val = t.get("price", 0)
        try:
            price_val = float(price_val)
        except (ValueError, TypeError):
            price_val = 0.0

        auxiliaries.append({
            "name": t.get("name", ""),
            "supName": t.get("supplier", ""),
            "type": "",
            "arrivedTime": t.get("arrived_time", ""),
            "isUsed": 0,
            "price": price_val,
            "cgBy": cg_by,
            "fCode": t.get("spec", ""),
            "unit": t.get("unit", "个"),
            "color": t.get("color", ""),
            "usageAct": usage_val,
            "phone": t.get("phone", ""),
            "purchaseQty": t.get("purchase_qty", ""),
            "cgNum": t.get("purchase_qty", ""),
        })

    # --- 组装完整请求体 ---
    # 版次：数字类型，默认1
    version = data.get("version", 1)
    # 确保 version 是整数
    try:
        version = int(version)
    except (ValueError, TypeError):
        version = 1

    payload: Dict[str, Any] = {
        # 基础信息
        "code": "",                                 # 自动生成
        "vNumber": "",                              # 自动生成
        "itemNum": data.get("style_number", ""),  # 款号 ★必填
        "needType": data.get("requirement_type", "ODM"),
        "customerName": customer_name or data.get("customer", ""),  # ★必填
        "customerCode": customer_code,
        "clothType": data.get("garment_type", "T"),  # ★必填 T/W/J/K...
        "style": data.get("style_name", ""),          # ★必填
        "layout": "",
        "designName": designer_name,                # ★必填
        "finishTime": "",
        "version": version,
        "userId": designer_id,                      # ★必填 设计师ID
        "num": str(sample_quantity),                # ★必填 打版件数
        "markName": mark_name,                      # ★必填 唛头名称
        "markId": mark_id,                          # ★必填 唛头ID
        "sewing": "",                                             # 所有工艺数据统一在works中

        # 图片（必填）
        "dUploadUrls": d_upload_urls,

        # 面料（必填）
        "designColors": design_colors,

        # 工艺（必填）
        "works": works,

        # 辅料（选填）
        "auxiliaries": auxiliaries,

        # 修改说明
        "modifications": data.get("modifications", []),
    }

    return payload


def find_mark_label(
    brand_name: str, labels: List[Dict]
) -> tuple:
    """根据品牌名匹配唛头"""
    for label in labels:
        if brand_name and brand_name in label.get("name", ""):
            return (str(label["id"]), label["name"])
    return ("", "")


def find_designer(
    designer_name: str, designers: List[Dict]
) -> tuple:
    """根据制作者名匹配设计师"""
    # 工艺单上的制作者名（如"威"）→ 匹配设计师列表
    for d in designers:
        if designer_name and designer_name in d.get("username", ""):
            return (str(d.get("userId", "")), d.get("username", ""))
        if designer_name and designer_name in d.get("realName", ""):
            return (str(d.get("userId", "")), d.get("realName", ""))
    return ("", "")

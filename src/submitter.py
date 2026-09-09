"""提交与文件重命名：build_payload（纯函数）、do_submit、rename_files。依赖 api/parsers/matcher。"""
import re
import requests
import openpyxl
from pathlib import Path
from config import BASE
from api import api_headers
from parsers import safe_float, parse_image_position
from matcher import find_best_customer


def build_payload(parsed, d_upload, identity, fabric_db, customers, labels):
    """客户匹配 + 唛头匹配 + 面料DB回填 + 组装顶层 dict。

    identity: dict with keys "realname" / "designer_id"
    纯函数：所有外部数据（fabric_db/customers/labels/identity）均以参数注入。
    """
    realname = identity["realname"]
    designer_id = identity["designer_id"]

    # === Match customer using pinyin + edit distance fuzzy matching ===
    customer_name = parsed["customer_name"]
    customer_code = ""
    matched_customer_name = customer_name  # may be corrected by match
    if customer_name:
        try:
            custs = customers
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

    # === Match label ===
    mark_id = ""
    for l in labels:
        if parsed["mark_name"] and parsed["mark_name"] in l.get("name", ""):
            mark_id = str(l["id"])
            break

    # === Fabric DB backfill → design_colors ===
    # Build designColors - one SKC per SKU, all fabrics in one SKC
    sku_groups = parsed["sku_groups"]
    sku_info = parsed["sku_info"]
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
                "cgBy": f_raw.get("buyer") or realname,
                "supName": f_raw.get("supplier") or detail.get("supName", ""),
                "buffon": f_raw.get("width") or detail.get("buffon", ""),
                "grem": f_raw.get("weight") or detail.get("grem", ""),
                "component": f_raw.get("component") or detail.get("component", ""),
                "productName": f_raw.get("productName") or detail.get("productName", ""),
                "thread": "0",
                "isUsed": "0",
                "price": safe_float(f_raw.get("meterPrice", 0)),
                "arrivedTime": f_raw.get("arriveTime", ""),
            })

        color_val = info.get("color", "")
        size_val = info.get("size", "L")
        design_colors.append({
            "color": color_val,
            "sku": f"SKU{sn}",  # SKU标识：SKU1/SKU2...，禁止填颜色_尺码
            "skuName": f"SKU{sn}",
            "size": size_val,
            "num": info.get("qty", "1"),
            "fabricList": fabric_list,
        })

    print(f"  Fabrics: {len(design_colors)} SKU(s), total {sum(len(dc['fabricList']) for dc in design_colors)} fabrics")

    # === 辅料采购人(cgBy)兜底：Excel 空则用使用者姓名 ===
    for aux in parsed["auxiliaries"]:
        aux["cgBy"] = aux["cgBy"] or realname

    # === Build payload ===
    payload = {
        "code": "", "vNumber": "",
        "itemNum": parsed["item_num"],
        "needType": parsed["need_type"],
        "customerName": matched_customer_name,
        "customerCode": customer_code,
        "customerLogo": "",                                     # [NEW]
        "clothType": parsed["cloth_type"],
        "style": parsed["style"],
        "layout": parsed["layout"],
        "designName": realname,
        "finishTime": parsed["finish_time"],
        "version": "",
        "userId": designer_id,
        "num": parsed["num_val"],
        "markName": parsed["mark_name"],
        "markId": mark_id,
        "sewing": "",
        "patternBy": "",                                        # [NEW]
        "cutBy": "",                                            # [NEW]
        "sewingBy": "",                                         # [NEW]
        "patternTime": "",                                      # [NEW]
        "cutTime": "",                                          # [NEW]
        "sewingTime": "",                                       # [NEW]
        "status": 0,                                            # [NEW]
        "dUploadUrls": d_upload,
        "designColors": design_colors,
        "works": parsed["works"],
        "auxiliaries": parsed["auxiliaries"],
        "modifications": [],
    }
    return payload


def do_submit(token, payload):
    r = requests.post(f"{BASE}/business/design/insertDesign", json=payload, headers=api_headers(token))
    result = r.json()

    if result.get("success"):
        info = result.get("data", {}).get("info", {})
        auto_num = info.get("itemNum") or info.get("code") or ""
        design_id = info.get("id", "")
        print(f"\n  [OK] Created! ID={design_id} itemNum={auto_num}")
    else:
        print(f"\n  [FAIL] {result.get('msg', '')[:300]}")

    return result


def rename_files(result, excel_path, image_paths, item_num, realname):
    """提交成功后的文件重命名（Excel / 图片 / 文件夹）。"""
    info = result.get("data", {}).get("info", {})
    auto_num = info.get("itemNum") or info.get("code") or ""

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

        # Always rename Excel to {style_num}_{name}.xlsx
        new_xls = xls_p.with_name(f"{style_num}_{realname}.xlsx")
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
                m = re.match(r'.*_?([A-Z]\d*)$', ip.stem)
                label = m.group(1) if m else ip.stem
            new_name = f"{style_num}_{label}{ip.suffix}"
            if ip.name != new_name:
                new_ip = ip.with_name(new_name)
                ip.rename(new_ip)
                print(f"  [RENAME] Image: {ip.name} -> {new_ip.name}")

        # Rename folder to {style_num}_{name}
        new_folder = folder_p.with_name(f"{style_num}_{realname}")
        if folder_p.name != f"{style_num}_{realname}":
            try:
                folder_p.rename(new_folder)
                print(f"  [RENAME] Folder: {folder_p.name} -> {new_folder.name}")
            except Exception as e:
                print(f"  [RENAME] Folder rename failed: {e}")

        result["auto_style_number"] = style_num

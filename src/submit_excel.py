"""工艺单自动上传 — 入口薄壳。

保留 submit_one(excel_path, image_paths) 签名与 main 入口。
编排：identity → api → parsers → excel_parser → submitter → validator。
顶部 re-export 供 verify_sku_fix.py / tests/dump_golden.py 依赖：
    se._MODE / se.BASE / se.login / se.api_headers / se.requests / se.USER_DESIGNER_ID
"""
import time
from pathlib import Path

import requests
from config import BASE, _MODE
from api import login, api_headers, upload_image, get_customers, get_labels, get_fabrics
import identity
from identity import USER_REALNAME, USER_DESIGNER_ID
import excel_parser
import submitter
import validator
from parsers import parse_image_position


def submit_one(excel_path, image_paths):
    # === Verify/collect designer identity (MUST be before login) ===
    if not identity.ensure_identity():
        return {"success": False, "msg": "identity_not_verified"}

    # re-exported names must mirror identity module state (verify_sku_fix.py reads se.USER_DESIGNER_ID)
    global USER_REALNAME, USER_DESIGNER_ID
    USER_REALNAME = identity.USER_REALNAME
    USER_DESIGNER_ID = identity.USER_DESIGNER_ID

    token = login(identity.USERNAME, identity.PASSWORD)
    print(f"[OK] Logged in")

    # === Upload images with position mapping ===
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

    # Map belong to type:
    #   A(belong=0)→type=0(主图), B(belong=1)→type=1(SKC详情)
    #   C1(belong=2)→type=2(基础资料第三页), C2+(belong≥3)→type=9(工艺详情)
    for u in d_upload:
        b = int(u["belong"])
        if b == 0:
            u["type"] = "0"   # 主图
        elif b == 1:
            u["type"] = "1"   # SKC详情
        elif b == 2:
            u["type"] = "2"   # 基础资料第三页(C1)
        else:
            u["type"] = "9"   # 工艺详情(C2/C3...)

    # === Read Excel ===
    parsed = excel_parser.parse_excel(excel_path)
    print(f"  ItemNum: {parsed['item_num']}, NeedType: {parsed['need_type']}, ClothType: {parsed['cloth_type']}")
    print(f"  Style: {parsed['style']}, Customer: {parsed['customer_name']}, Num: {parsed['num_val']}")

    # === Fetch reference data ===
    customers = []
    if parsed["customer_name"]:
        try:
            customers = get_customers(token)
        except Exception as e:
            print(f"  [CUSTOMER] Matching failed: {e}")
        except: pass
    labels = get_labels(token)
    fabric_db = get_fabrics(token)

    # === Build payload ===
    identity_info = {"realname": identity.USER_REALNAME, "designer_id": identity.USER_DESIGNER_ID}
    payload = submitter.build_payload(parsed, d_upload, identity_info, fabric_db, customers, labels)

    works = parsed["works"]
    make_n = sum(1 for w in works if w['cate'] == '0')
    sew_n  = sum(1 for w in works if w['cate'] == '1')
    garm_n = sum(1 for w in works if w['cate'] == '2')
    print(f"  Works: {make_n}制作 + {sew_n}车缝 + {garm_n}成衣")
    print(f"  Auxiliaries: {len(parsed['auxiliaries'])}")

    print(f"\n[DEBUG] dUploadUrls: {len(d_upload)} images (types: {[u['type'] for u in d_upload]}, belongs: {[u['belong'] for u in d_upload]})")

    # === Pre-submit validation ===
    errors, warnings = validator.validate(parsed, parsed["num_val"], fabric_db)

    if errors:
        print(f"\n{'='*50}")
        print(f"❌ 以下 {len(errors)} 项必须修正后才能提交：")
        for e in errors:
            print(f"  • {e}")
        print(f"{'='*50}")
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
                return {"success": False, "msg": "user_cancelled"}
        except (EOFError, KeyboardInterrupt):
            return {"success": False, "msg": "user_cancelled"}

    # === Submit ===
    result = submitter.do_submit(token, payload)
    if result.get("success"):
        submitter.rename_files(result, excel_path, image_paths, parsed["item_num"], identity.USER_REALNAME)

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

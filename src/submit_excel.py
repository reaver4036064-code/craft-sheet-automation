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

    # === 无效行提醒（只报不改：不拦截提交）===
    for msg in parsed.get("_row_warnings", []):
        print(f"  [WARN] {msg}")

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


# === 以下为命令行入口（跨平台：Windows / macOS / Linux 通用） ===

_IMG_EXTS = ('.png', '.jpg', '.jpeg')


def _find_excel(folder):
    """在文件夹中找表格：排除 Excel 锁文件(~$开头)，优先含「工艺」「表单」的。"""
    xls = sorted(p for p in folder.iterdir()
                 if p.is_file()
                 and p.suffix.lower() == '.xlsx'
                 and not p.name.startswith('~$'))
    if not xls:
        return None
    for p in xls:
        if '工艺' in p.name or '表单' in p.name:
            return p
    return xls[0]


def _collect_images(folder):
    """收集文件夹内图片，按文件名排序（A/B/C1/C2...）。后缀大小写不敏感。"""
    return sorted(p for p in folder.iterdir()
                  if p.is_file() and p.suffix.lower() in _IMG_EXTS)


def _expand(targets):
    """若某文件夹自身没有表格、但子文件夹有，则视为批量父目录展开。"""
    out = []
    for t in targets:
        if _find_excel(t):
            out.append(t)
        else:
            subs = [c for c in sorted(t.iterdir())
                    if c.is_dir() and _find_excel(c)] if t.is_dir() else []
            out.extend(subs if subs else [t])
    return out


def _usage():
    print("用法: python3 submit_excel.py <设计单文件夹> [更多文件夹...]")
    print("")
    print("  每个文件夹需包含: 1 个 .xlsx 表格  +  若干 .png/.jpg 图片 (A/B/C1/C2...)")
    print("  若传入的是父目录(自身无表格、子目录有)，会自动逐个子目录处理。")
    print("")
    print("示例:")
    print("  python3 submit_excel.py ./我的设计单")
    print("  python3 submit_excel.py ./单1 ./单2")
    print("")
    print("提示: Windows 下命令也可写作 python；macOS/Linux 请用 python3。")


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        _usage()
        sys.exit(1)

    targets = [Path(a) for a in sys.argv[1:]]
    bad = [p for p in targets if not p.is_dir()]
    if bad:
        for p in bad:
            print(f"[ERROR] 不是有效文件夹: {p}")
        sys.exit(1)

    jobs = _expand(targets)
    results = []

    for i, folder in enumerate(jobs, 1):
        xls = _find_excel(folder)
        imgs = _collect_images(folder)
        print(f"\n{'='*60}")
        print(f"[{i}/{len(jobs)}] {folder}")

        if not xls or not imgs:
            missing = "、".join(
                [t for t in ("缺少Excel表格" if not xls else "",
                             "缺少图片" if not imgs else "") if t]
            )
            print(f"[SKIP] {missing}")
            results.append({"folder": str(folder), "success": False, "error": missing})
            continue

        try:
            r = submit_one(xls, imgs)
            results.append({"folder": str(folder), "success": r.get("success", False), "result": r})
        except Exception as e:
            print(f"[ERROR] {e}")
            import traceback
            traceback.print_exc()
            results.append({"folder": str(folder), "success": False, "error": str(e)})

    ok = sum(1 for r in results if r.get("success"))
    print(f"\n{'='*60}")
    print(f"全部完成: 成功 {ok} / 共 {len(results)}")

    if ok < len(results):
        print("\n未成功的项:")
        for r in results:
            if not r.get("success"):
                print(f"  - {r['folder']}: {r.get('error', '提交失败')}")
        sys.exit(2)

    print(f"\n{'='*60}")
    for r in results:
        s = "OK" if r.get("success") else "FAIL"
        print(f"  [{s}] {r['folder']}")

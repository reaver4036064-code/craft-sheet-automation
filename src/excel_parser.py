"""Excel 解析：从 submit_one 内联代码抽离基础信息 / SKU 区 / 工艺区 / 辅料区。依赖 parsers。"""
import openpyxl
from parsers import to_str, safe_float, parse_chinese_date


def parse_excel(excel_path):
    wb = openpyxl.load_workbook(excel_path, data_only=True)
    ws = wb.active
    row_warnings = []  # 无效行提醒（只报不改，随返回值带出由入口打印）

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

    finish_time_raw = to_str(ws["F10"].value) or ""
    finish_time, _date_warning = parse_chinese_date(finish_time_raw)

    # === Parse SKU section ===
    # Detect "SKU编号" header row to find section start (handles variant Excel layouts)
    sku_groups = {}
    sku_info = {}

    # Find SKU section start and build column map from header row
    # 全表扫描定位「SKU编号」表头行（V6 在第 20 行、V7 在第 34 行；插行后仍可定位）
    sku_header_row = 21
    sku_header_found = False
    col_map = {}  # header_name -> col_index (1-based)
    for r in range(1, ws.max_row + 1):
        if to_str(ws.cell(r, 1).value) == "SKU编号":
            sku_header_row = r
            sku_header_found = True
            # Scan header row to map column positions
            for c in range(1, 30):
                h = to_str(ws.cell(r, c).value)
                if h:
                    col_map[h] = c
            break
    if not sku_header_found:
        row_warnings.append(
            "未找到「SKU编号」表头行，SKU/面料区可能解析为空，请检查模板是否被改动。"
        )

    for r in range(sku_header_row + 1, ws.max_row + 1):
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
        width = to_str(ws.cell(r, col_map.get("幅宽/CM", 10)).value or ws.cell(r, col_map.get("幅宽", 10)).value)
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

    # === Parse processes (V7: 3 zones → works[] with cate 0/1/2) ===
    works = []  # 所有工艺统一进works[]

    zone = None  # 'make' | 'sew' | 'garm'

    # 工艺区上界：动态定位 SKU 区起点（'▼ SKU 与面料' 或 'SKU编号'），避免硬编码 35 在插行后截断成衣工艺
    process_end = ws.max_row + 1
    for _r in range(12, ws.max_row + 1):
        _a = to_str(ws.cell(_r, 1).value)
        if _a == 'SKU编号' or ('▼' in _a and 'SKU' in _a):
            process_end = _r
            break

    for r in range(12, process_end):
        label = to_str(ws.cell(r, 1).value)
        name = to_str(ws.cell(r, 2).value)
        factory = to_str(ws.cell(r, 3).value)    # 制衣厂
        unit_price = to_str(ws.cell(r, 4).value)  # 单价

        if not label:
            # A 列无序号/标题：若该行确实为空 → 视为分区间隔行，重置 zone；
            # 若仍填了内容且当前分区有效 → 保留收集（不丢数据），但必须告警提示确认。
            if zone and (name or factory or unit_price):
                _zone_cn = {'make': '工艺制作', 'sew': '车缝工艺', 'garm': '成衣工艺'}.get(zone, zone)
                row_warnings.append(
                    f"第{r}行：A列(序号)为空但填写了「{name or factory or unit_price}」，"
                    f"已按上一分区「{_zone_cn}」收集。请确认该行是否应填写——"
                    f"若非有意，请移到带序号的黄色行内并删除本行内容。"
                )
                # 不重置 zone，继续走下面的收集逻辑
            else:
                zone = None
                continue

        if '工艺制作' in label:
            zone = 'make'; continue
        elif '车缝工艺' in label:
            zone = 'sew'; continue
        elif '成衣工艺' in label:
            zone = 'garm'; continue
        elif '▼' in label or 'SKU' in label or '面料' in label:
            zone = None; continue

        if not zone or not name:
            continue
        # 表头行：A 列为「序号」，或 B 列为「工艺名称/工艺内容」的各种变体
        # （严禁裸 '工艺' in name 包含匹配，以免误判「工艺处理」等正常工艺名）
        if label == '序号' or '工艺名称' in name or '工艺内容' in name:
            continue

        cate = '0' if zone == 'make' else '1' if zone == 'sew' else '2'
        works.append({
            "cate": cate, "status": "0", "name": name, "sort": len(works),
            "factoryName": factory, "unitPrice": safe_float(unit_price),
        })

    # === Parse auxiliaries ===
    auxiliaries = []
    # Find "辅料名称" header row and build column map
    # 全表扫描定位「辅料名称」表头行（V6 在第 31 行、V7 在第 45 行；插行后仍可定位）
    aux_start = 32
    aux_header_found = False
    aux_col = {}  # header -> col index
    for r in range(1, ws.max_row + 1):
        if to_str(ws.cell(r, 2).value) == "辅料名称":
            aux_start = r + 1
            aux_header_found = True
            # Map columns from header row
            for c in range(1, 30):
                h = to_str(ws.cell(r, c).value)
                if h:
                    aux_col[h] = c
            break
    if not aux_header_found:
        row_warnings.append(
            "未找到「辅料名称」表头行，辅料区可能解析为空，请检查模板是否被改动。"
        )

    for r in range(aux_start, ws.max_row + 1):
        # 遇到下一分区标题（A 列含 ▼）即停止，避免越界收集后续分区内容
        if '▼' in to_str(ws.cell(r, 1).value):
            break
        name = to_str(ws.cell(r, aux_col.get("辅料名称", 2)).value)
        if not name:
            # 辅料名称为空：若 A 列有序号且 C-L 任一列有内容 → 记警告（只报不改）
            if to_str(ws.cell(r, 1).value) and any(
                to_str(ws.cell(r, c).value) for c in range(3, 13)
            ):
                row_warnings.append(
                    f"第{r}行：辅料名称（辅料信息区）为空但其他列有内容，该行无效，已忽略。"
                    f"请先填写「辅料名称」。"
                )
            continue
        auxiliaries.append({
            "name": name,
            "type": to_str(ws.cell(r, aux_col.get("规格型号", 3)).value),
            "unit": to_str(ws.cell(r, aux_col.get("单位", 6)).value) or "个",
            "usageAct": to_str(ws.cell(r, aux_col.get("用量", 5)).value),
            "price": safe_float(ws.cell(r, aux_col.get("采购单价", 7)).value),
            "supName": to_str(ws.cell(r, aux_col.get("供应商", 8)).value),
            "phone": to_str(ws.cell(r, aux_col.get("联系方式", 9)).value),
            "cgBy": to_str(ws.cell(r, aux_col.get("采购人", 11)).value),
            "color": to_str(ws.cell(r, aux_col.get("颜色", 4)).value),
            "arrivedTime": "",
            "isUsed": 0,
            "fCode": "",
        })

    wb.close()

    return {
        "item_num": item_num,
        "need_type": need_type,
        "cloth_type": cloth_type,
        "style": style,
        "customer_name": customer_name,
        "num_val": num_val,
        "layout": layout,
        "mark_name": mark_name,
        "finish_time_raw": finish_time_raw,
        "finish_time": finish_time,
        "_date_warning": _date_warning,
        "sku_groups": sku_groups,
        "sku_info": sku_info,
        "works": works,
        "auxiliaries": auxiliaries,
        "_row_warnings": row_warnings,
    }

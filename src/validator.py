"""提交前校验：规则 1(件数=SKU件数总和)、1b(SKU数=打版件数)、2(色号/颜色名必填)、3(面料不在DB查手工字段)。

原校验块不使用 to_str/safe_float，故本模块无运行时依赖。
"""


def validate(parsed, num_val, fabric_db):
    errors = []    # blocking: must fix before submit
    warnings = []  # non-blocking: user can skip

    sku_groups = parsed.get("sku_groups", {})
    sku_info = parsed.get("sku_info", {})

    # Date format warning (from parse_chinese_date earlier)
    _date_warning = parsed.get("_date_warning")
    if _date_warning:
        warnings.append(_date_warning)

    # Rule 1: 打版件数 = total SKU quantities
    total_qty = sum(int(sku_info.get(sn, {}).get("qty", 0) or 0) for sn in sku_groups)
    expected_qty = int(num_val or 0)
    if expected_qty > 0 and total_qty != expected_qty:
        errors.append(f"打版件数({expected_qty}件)与SKU件数总和({total_qty}件)不一致，必须修正")

    # Rule 1b: SKU编号数量 = 打版件数（每个SKU对应一件打版）
    sku_count = len(sku_groups)
    if expected_qty > 0 and sku_count != expected_qty:
        errors.append(f"打版件数为{expected_qty}件，但SKU区域有{sku_count}个SKU编号（应一致），请修正")

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

    return errors, warnings

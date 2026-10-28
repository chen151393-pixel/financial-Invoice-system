"""来源单价按本地列精度展示；原始价格留在快照，金额不能由展示单价反算。"""

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation, localcontext

from backend.core.errors import ApiError


def normalize(value, precision, scale):
    if value is None or value == "":
        return None
    try:
        if isinstance(value, (bool, float, dict, list)):
            raise ValueError()
        number = Decimal(str(value))
        with localcontext() as context:
            context.prec = precision + 1
            limit = Decimal(10) ** (precision - scale)
            if not number.is_finite() or number.copy_abs() >= limit:
                raise ValueError()
            rounded = number.quantize(Decimal(1).scaleb(-scale), rounding=ROUND_HALF_UP)
            # 进位可能越过整数位上限，必须在写入前拒绝，不能依赖数据库截断。
            if rounded.copy_abs() >= limit:
                raise ValueError()
        return rounded
    except (ValueError, InvalidOperation, OverflowError):
        raise ApiError(422, "字段unit_price格式或整数位超出数据库范围，未保存") from None


def warnings(documents, config):
    result = []
    for kind, spec_name, key, column, label in (
        ("customs", "customs_line", "unit_price", "unit_price", "报关单"),
        ("customs", "customs_line", "declared_unit_price", "declared_unit_price", "报关单（申报单价）"),
        ("purchase", "purchase_line", "tax_inclusive_price", "unit_price", "子采购单"),
    ):
        field = getattr(config, spec_name).storage_fields.get(key)
        if not field:
            continue
        for document in documents[kind]:
            count = 0
            for raw, line in zip(document["raw"]["lines"], document["lines"], strict=True):
                saved = line["row"] if kind == "customs" else line
                original = raw["record"].get(field)
                if original not in (None, "") and Decimal(str(original)) != saved[column]:
                    count += 1
            if count:
                number = document["head"].get("order_no" if kind == "purchase" else "record_no")
                number = number or document["ns_internal_id"]
                result.append(
                    f"{label} {number} 有 {count} 条明细单价已按 8 位小数四舍五入保存；"
                    "完整 NS 单价保留在原始快照，数量、行金额及单据总额未重新计算。"
                )
    return result

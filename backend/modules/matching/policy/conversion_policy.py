"""两种数量口径：采购数量 = 发票数量 × 分子 / 分母，禁止静默舍入。"""

from decimal import Decimal, localcontext

from backend.core.errors import ApiError
from backend.modules.source.public import unit_label

from .comparison_policy import same_unit


def convert(quantity, item, basis, body, units):
    if item["quantity"] is None or not item["unit"] or not basis["unit"]:
        raise ApiError(409, "发票或采购缺少可核实的数量单位，不能确认分配")
    numerator, denominator = body.conversionNumerator, body.conversionDenominator
    # 记录仍保存采购单位原值，只在判断是否同单位时按字典名称比较
    if same_unit(item["unit"], unit_label(basis["unit"], units)):
        if (numerator, denominator) != (Decimal(1), Decimal(1)):
            raise ApiError(422, "相同单位的换算因子必须为 1")
    elif not body.conversionEvidence.strip():
        raise ApiError(422, "不同单位须填写对应商品的换算证据")
    with localcontext() as ctx:
        ctx.prec = 64
        purchase = quantity * numerator / denominator
        if purchase != purchase.quantize(Decimal("0.00000001")) or purchase >= Decimal(10) ** 18:
            raise ApiError(422, "换算数量不能精确落在允许的 8 位小数或超出范围，请核实换算依据")
    return {
        "purchase_quantity": purchase,
        "invoice_unit": item["unit"],
        "purchase_unit": basis["unit"],
        "conversion_numerator": numerator,
        "conversion_denominator": denominator,
        "conversion_evidence": {
            "reference": body.conversionEvidence.strip(),
            "invoiceVersionId": str(body.invoiceVersionId or ""),
            "purchaseBasisId": str(basis["id"]),
        },
    }

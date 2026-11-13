"""既有业务用例显式模拟后台补算完成；队列及纯查询边界另由 test_review_calculations 覆盖。"""

from backend.modules.review.service.calculation_service import CalculationService
from backend.modules.review.service.review_service import ReviewService


def approve_customs(review, declaration_id):
    """下游任务用例先完成真实海关导入和人工审核；门槛本身由双审核专项验证。"""
    from backend.modules.review.dto.customs_receipt_dto import CustomsApproveRequest, CustomsReceiptQuery
    from backend.modules.review.service.customs_approval_service import CustomsApprovalService
    from backend.modules.review.service.customs_receipt_service import CustomsReceiptService
    from backend.modules.source.public import declarations_by_number
    from backend.tests.test_customs_receipts import _import, row

    content = review.declarations.detail(declaration_id)
    number = content["declaration"]["declaration_no"]
    with review.engine.connect() as connection:
        source = declarations_by_number(connection, [number])[number][0]
    service = CustomsReceiptService(review.engine)
    _import(
        service,
        [
            row(
                number,
                str(i).zfill(2),
                line["name"] or "待核对品名",
                line["unit"] or "待核对单位",
                line["quantity"] or 1,
            )
            for i, line in enumerate(source["lines"], 1)
        ],
    )
    item = service.browse(CustomsReceiptQuery(declarationNo=number)).items[0]
    result = CustomsApprovalService(review.engine, review.events).approve_batch(
        CustomsApproveRequest(
            items=[{"id": item.id, "token": item.approval.token}],
            method="manual",
            note="隔离测试已人工核实海关口径",
        ),
        "user:admin",
    )
    assert result.approved and not result.skipped


class MaterializedReviewService(ReviewService):
    def browse(self, query):
        CalculationService(self).rebuild()
        return super().browse(query)


def comparable_purchase(*args, **kwargs):
    """幅度/队列测试使用与报关行同单位的数据；卷/平方米换算另有专项回归。"""
    from backend.tests.test_source_storage import purchase

    order = purchase(*args, **kwargs)
    for _, record in order[2]:
        record["custrecord_swc_subpo_item_bgqty"] = record["custrecord_swc_subpo_item_qty"]
        record["custrecord_swc_subpo_item_bgunit"] = record["custrecord_swc_subpo_item_unit"]
    return order


def customs_prices(
    customs_id="870", modified="2026-09-02T10:00:00Z", *, original="1.5", declared="1.5", currency="USD"
):
    """同一报关行两种单价的财务测试来源；可显式构造异常与容差边界。"""
    from decimal import Decimal

    from backend.tests.test_source_storage import customs

    result = customs(customs_id, modified)
    for _, row in result[2]:
        row["custrecord_swc_unitprice"] = Decimal(original)
        row["custrecord_swc_grossamountzj"] = Decimal(declared)
        row["custrecord_swc_currency"] = currency
    return result

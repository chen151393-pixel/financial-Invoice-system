"""既有业务用例显式模拟后台补算完成；队列及纯查询边界另由 test_review_calculations 覆盖。"""

from backend.modules.review.service.calculation_service import CalculationService
from backend.modules.review.service.review_service import ReviewService


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

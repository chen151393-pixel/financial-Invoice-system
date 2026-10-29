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

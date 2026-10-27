"""既有业务用例显式模拟后台补算完成；队列及纯查询边界另由 test_review_calculations 覆盖。"""

from backend.modules.review.service.calculation_service import CalculationService
from backend.modules.review.service.review_service import ReviewService


class MaterializedReviewService(ReviewService):
    def browse(self, query):
        CalculationService(self).rebuild()
        return super().browse(query)

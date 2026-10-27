"""进项发票按匹配状态筛选的列表查询：沿用 invoice 列表的查询条件与校验，增加匹配状态。"""

from typing import Literal

from backend.modules.invoice.public import InvoiceQuery

MatchStatus = Literal["all", "confirmed", "partial", "proposed", "needs_review", "none", "excluded"]


class InvoiceListQuery(InvoiceQuery):
    matchStatus: MatchStatus = "all"

    def filters(self):
        """去掉匹配状态，得到 invoice 列表的查询条件。"""
        return InvoiceQuery(**self.model_dump(exclude={"matchStatus"}))

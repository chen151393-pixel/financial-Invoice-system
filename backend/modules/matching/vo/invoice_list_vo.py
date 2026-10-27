"""进项发票按匹配状态筛选的列表响应：列表结构与 invoice 列表相同，另附各状态张数与本页摘要。"""

from backend.core.dto import StrictModel
from backend.modules.invoice.public import InvoiceList

from .matching_vo import SummaryRow


class InvoiceListResult(StrictModel):
    list: InvoiceList
    # all 与各匹配状态的张数；不受所选匹配状态影响，只受其他筛选条件影响
    counts: dict[str, int]
    summaries: list[SummaryRow]
    # 筛选范围超过扫描上限时的提示（张数与筛选只覆盖较新的发票）
    notice: str = ""

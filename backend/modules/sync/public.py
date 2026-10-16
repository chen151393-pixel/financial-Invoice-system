"""手动拉票事件；发票模块订阅后在发布方事务中保存。"""

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class LemonInvoicesFetched:
    scope: str
    request_id: str
    account: str
    start: date
    end: date
    records: tuple[dict, ...]

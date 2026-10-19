"""列表补拉权限与持久同步状态。"""

from pydantic import BaseModel

from .lemon_invoice_vo import Action, LemonRun


class InvoiceDetailAction(Action):
    invoiceId: str


class LemonDetailActions(BaseModel):
    rows: list[InvoiceDetailAction]
    latest: LemonRun | None

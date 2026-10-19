"""账套与同步结果响应，只返回已提交统计。"""

from backend.modules.invoice.public import describe_lemon_result
from pydantic import BaseModel

from ..policy.lemon_invoice_policy import run_business_types


class Action(BaseModel):
    allowed: bool
    reason: str


class LemonAccount(BaseModel):
    asid: str
    name: str


class LemonAccounts(BaseModel):
    items: list[LemonAccount]


class LemonRun(BaseModel):
    requestId: str
    asid: str
    accountName: str
    startDate: str
    endDate: str
    businessTypes: list[str]
    status: str
    result: dict | None
    error: str | None
    createdAt: str


class LemonConfiguration(BaseModel):
    query: Action
    sync: Action
    selected: LemonAccount | None
    latest: LemonRun | None
    businessTypeOptions: list[str]
    defaultBusinessTypes: list[str]


def run_view(row):
    if not row:
        return None
    return {
        "requestId": row["request_id"],
        "asid": row["asid"],
        "accountName": row["account_name"],
        "startDate": row["start_date"].isoformat(),
        "endDate": row["end_date"].isoformat(),
        "businessTypes": run_business_types(row),
        "status": row["status"],
        "result": describe_lemon_result(row["result"])
        if row["status"] == "completed" and row["result"]
        else None,
        "error": row["error"],
        "createdAt": row["created_at"].isoformat() + "Z",
    }

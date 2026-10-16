"""账套与同步结果响应，只返回已提交统计。"""

from pydantic import BaseModel


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
    status: str
    result: dict | None
    error: str | None
    createdAt: str


class LemonConfiguration(BaseModel):
    query: Action
    sync: Action
    selected: LemonAccount | None
    latest: LemonRun | None


def run_view(row):
    if not row:
        return None
    return {
        "requestId": row["request_id"],
        "asid": row["asid"],
        "accountName": row["account_name"],
        "startDate": row["start_date"].isoformat(),
        "endDate": row["end_date"].isoformat(),
        "status": row["status"],
        "result": row["result"],
        "error": row["error"],
        "createdAt": row["created_at"].isoformat() + "Z",
    }

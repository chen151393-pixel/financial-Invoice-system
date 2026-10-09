"""现有回写接口响应契约，保留原字段及状态。"""

from typing import Any

from pydantic import BaseModel


class JobSummary(BaseModel):
    id: str
    target: str
    operation: str
    expires: int
    state: str


class Preview(JobSummary):
    payload: dict[str, Any]
    before: Any
    result: Any


class Action(BaseModel):
    allowed: bool
    reason: str | None


class PreviewView(Preview):
    actions: dict[str, Action]
    stateLabel: str

"""近 N 天同步情况响应：每行一个来源，每格一天（北京时间）。"""

from backend.core.dto import StrictModel


class HealthDay(StrictModel):
    date: str
    # success 全部成功；partial 部分成功；failed 失败；running 执行中；none 未执行
    status: str
    label: str
    runs: int
    failed: int


class HealthRow(StrictModel):
    key: str
    label: str
    days: list[HealthDay]


class SyncHealth(StrictModel):
    dates: list[str]
    rows: list[HealthRow]

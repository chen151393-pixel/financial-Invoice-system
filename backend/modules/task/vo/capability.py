"""可执行操作：是否允许及原因（前端只按此显示按钮）。"""

from backend.core.dto import StrictModel


class Capability(StrictModel):
    allowed: bool = False
    reason: str

"""NS 按批后台保存请求；分页与日期规则沿用 PullRequest。"""

from typing import Literal

from pydantic import Field, model_validator
from pydantic_core import PydanticCustomError

from .source_dto import PullRequest

UUID = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
SaveKind = Literal["sub-purchase-orders", "customs-declarations"]


class NsRunRequest(PullRequest):
    requestId: str = Field(pattern=UUID)
    kind: SaveKind

    @model_validator(mode="after")
    def background_save(self):
        # 后台批次固定按关联组部分保存，进度按请求编号查询；不接受旧协议的两个开关。
        if self.progressId is not None or "partialSave" in self.model_fields_set:
            raise PydanticCustomError(
                "sync_run", "后台同步按请求编号查询进度，请勿提交 progressId 或 partialSave"
            )
        return self

    def snapshot(self):
        return {
            "offset": self.offset,
            "limit": self.limit,
            "startDate": self.startDate,
            "endDate": self.endDate,
            "requireDateRange": self.requireDateRange,
            **({"cursor": self.cursor.model_dump()} if self.cursor is not None else {}),
        }

    def pull_request(self, progress_id):
        return PullRequest(**self.snapshot(), partialSave=True, progressId=progress_id)

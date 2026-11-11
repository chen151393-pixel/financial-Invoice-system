"""按 CD 单号重建已存关联；使用原有登录权限，不提供任意表或查询入口。"""

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from backend.core.dependencies import Owner


class RebuildRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    recordNo: str = Field(min_length=1, max_length=120)
    account: str | None = Field(default=None, min_length=1, max_length=100)


def create_router(service):
    router = APIRouter(prefix="/api/source/relations", tags=["来源关联"])

    @router.post("/rebuild")
    def rebuild(body: RebuildRequest, owner: Owner):
        return {"results": service.rebuild(record_no=body.recordNo, account=body.account)}

    return router

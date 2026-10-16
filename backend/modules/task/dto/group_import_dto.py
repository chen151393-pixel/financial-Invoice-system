"""外部群表导入及已导入目录的请求校验。"""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field, StringConstraints

from backend.core.dto import StrictModel

from .supplier_group_dto import GroupFields, SupplierId


class ExternalGroupFields(GroupFields):
    memberCount: int | None = None
    department: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
    createdAt: datetime | None = None


class GroupImportFile(StrictModel):
    filename: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1, max_length=5592408)
    account: str = Field(default="", max_length=100)


class CatalogQuery(StrictModel):
    keyword: Annotated[str, StringConstraints(strip_whitespace=True, max_length=120)] = ""
    page: int = Field(default=1, ge=1)
    pageSize: int = Field(default=20, ge=1, le=50)
    status: Literal["all", "unbound", "bound"] = "all"


class PreviewQuery(StrictModel):
    page: int = Field(default=1, ge=1)
    pageSize: int = Field(default=20, ge=1, le=50)
    importId: str = Field(min_length=36, max_length=36)


class ImportSelection(StrictModel):
    rowNo: int = Field(ge=2, le=1001)
    supplierId: SupplierId
    revision: int = Field(ge=0)
    replaceExisting: bool = False


class ImportConfirm(StrictModel):
    importId: str = Field(min_length=36, max_length=36)
    selections: list[ImportSelection] = Field(default_factory=list, max_length=1000)


class CatalogBinding(StrictModel):
    chatId: str = Field(min_length=1, max_length=190)
    catalogRevision: int = Field(ge=1)
    supplierId: SupplierId
    revision: int = Field(ge=0)
    replaceExisting: bool = False

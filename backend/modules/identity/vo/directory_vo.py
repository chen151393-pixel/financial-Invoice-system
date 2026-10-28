"""组织预览仅返回页面必需字段，不返回飞书令牌或头像地址。"""

from backend.core.dto import StrictModel

from ..dto.directory_dto import DirectorySelection
from .access_vo import SyncRun


class PreviewDepartment(StrictModel):
    id: str
    name: str
    path: str
    depth: int
    memberCount: int


class DirectoryPreview(StrictModel):
    id: str
    expiresAt: str
    departments: list[PreviewDepartment]
    selection: DirectorySelection


class PreviewMember(StrictModel):
    id: str
    name: str
    departments: list[str]
    selected: bool
    selectable: bool
    reason: str | None
    imported: bool
    coveredByDepartment: bool


class DirectoryMembers(StrictModel):
    items: list[PreviewMember]
    total: int
    page: int
    pageSize: int
    selectedCount: int
    coveredDepartmentIds: list[str]


class DirectoryPlan(StrictModel):
    selection: DirectorySelection
    selectedCount: int
    addedCount: int
    retainedCount: int
    removedNames: list[str]
    departmentNames: list[str]
    userNames: list[str]
    unavailableCount: int


class DirectoryResult(StrictModel):
    run: SyncRun
    userIds: list[int]

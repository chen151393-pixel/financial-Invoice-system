"""业务库只读连接检查结果，不返回连接串或账户凭据。"""

from typing import Literal

from backend.core.dto import StrictModel


class DatabaseStatus(StrictModel):
    configured: bool
    connected: bool
    ready: bool
    state: Literal["not_configured", "connection_failed", "schema_incomplete", "connected"]
    message: str
    missingTables: list[str]


class StorageConfiguration(StrictModel):
    allowed: bool
    reason: str
    localAllowed: bool
    database: DatabaseStatus


class SavedCounts(StrictModel):
    created: int
    updated: int
    linesCreated: int
    linesUpdated: int


class StorageResult(StrictModel):
    pl: str
    purchase: SavedCounts
    customs: SavedCounts
    warnings: list[str]
    savedAt: str
    message: str

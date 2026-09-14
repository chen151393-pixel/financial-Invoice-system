"""NS业务记录查询接口。"""

from fastapi import APIRouter

from backend.core.dependencies import Owner

from .database_vo import DatabaseStatus, StorageConfiguration, StorageResult
from .dto import LocalPlQuery, PlComparisonQuery, PlQuery, PlSyncRequest, RecordQuery
from .pl_comparison_vo import ComparisonResult
from .pl_vo import PlConfiguration, PlResult


def create_router(service):
    router = APIRouter(prefix="/api/ns", tags=["业务记录"])

    @router.post("/pl-comparison", response_model=ComparisonResult)
    def pl_comparison(body: PlComparisonQuery, owner: Owner):
        return service.pl_comparison.query(body.pl, body.company)

    @router.get("/pl-lookup/config", response_model=PlConfiguration)
    def pl_config(owner: Owner):
        return service.pl_lookup.configuration()

    @router.post("/pl-lookup", response_model=PlResult)
    def pl_lookup(body: PlQuery, owner: Owner):
        return service.pl_lookup.query(body.pl, body.page)

    @router.get("/records/{record_type}")
    def records(record_type: str, owner: Owner):
        return service.records(record_type)

    @router.get("/records/{record_type}/{record_id}")
    def record(record_type: str, record_id: str, owner: Owner):
        return service.records(record_type, record_id)

    @router.post("/query")
    def query(body: RecordQuery, owner: Owner):
        return service.query(body.model_dump())

    return router


def create_database_router(service):
    router = APIRouter(prefix="/api/business", tags=["业务数据库"])

    @router.get("/database-status", response_model=DatabaseStatus)
    def database_status(owner: Owner):
        return service.database_status()

    @router.get("/pl-storage/config", response_model=StorageConfiguration)
    def storage_configuration(owner: Owner):
        return service.storage.configuration()

    @router.post("/pl-sync", response_model=StorageResult)
    def sync_pl(body: PlSyncRequest, owner: Owner):
        return service.storage.sync(body.pl, owner)

    @router.post("/pl-documents/query", response_model=PlResult)
    def local_pl(body: LocalPlQuery, owner: Owner):
        return service.storage.query(body.pl, body.page, owner)

    return router

"""NS业务记录查询接口。"""

from fastapi import APIRouter

from backend.core.dependencies import Owner

from .dto import RecordQuery


def create_router(service):
    router = APIRouter(prefix="/api/ns", tags=["业务记录"])

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

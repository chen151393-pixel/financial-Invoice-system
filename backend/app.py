"""应用装配：创建依赖、注册接口、管理生命周期。"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from .core.config import load_settings
from .core.database import make_engine
from .core.dependencies import Owner
from .core.frontend import create_router as frontend_router
from .core.middleware import RequestGuard, register_error_handlers
from .integrations.netsuite.client import NetSuite
from .manage import verify_database
from .modules.business.controller import create_router as business_router
from .modules.business.service import BusinessService
from .modules.identity.controller import create_router as identity_router
from .modules.identity.service import IdentityService
from .modules.sync.controller import create_router as sync_router
from .modules.sync.service import ConnectionService
from .modules.writeback.controller import create_router as writeback_router
from .modules.writeback.service import WritebackService


def create_app(settings=None, ns=None, engine=None):
    settings = settings or load_settings()
    owns_ns, owns_engine = ns is None, engine is None
    ns = ns or NetSuite(settings)
    engine = engine or make_engine(settings.database_url)

    @asynccontextmanager
    async def lifespan(_app):
        try:
            verify_database(engine)
            yield
        finally:
            if owns_ns:
                ns.close()
            if owns_engine:
                engine.dispose()

    app = FastAPI(title="NS 发票对账后端", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    identity = IdentityService(settings)
    app.state.identity = identity
    app.add_middleware(RequestGuard, secure=settings.origin.startswith("https://"))
    register_error_handlers(app)
    app.include_router(identity_router(identity, settings))
    app.include_router(business_router(BusinessService(ns)))
    app.include_router(sync_router(ConnectionService(settings, ns)))
    app.include_router(writeback_router(WritebackService(settings, ns, engine)))

    @app.get("/api/health", tags=["基础设施"])
    def health():
        return {"status": "ok"}

    @app.get("/api/openapi.json", include_in_schema=False)
    def openapi(owner: Owner):
        return app.openapi()

    app.include_router(frontend_router(settings))
    return app

"""应用装配：创建依赖、注册接口、管理生命周期。"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from .core.business_database import make_business_engine
from .core.config import load_settings
from .core.database import make_engine
from .core.dependencies import Owner
from .core.frontend import create_router as frontend_router
from .core.middleware import RequestGuard, register_error_handlers
from .integrations.contract_archive import ContractArchive
from .integrations.netsuite.client import NetSuite
from .integrations.netsuite.subpo_contract import connection_settings
from .manage import verify_database
from .modules.business.controller import create_database_router
from .modules.business.controller import create_router as business_router
from .modules.business.public import CustomsReconciliationSource, PurchaseMatchingSource, SubpoContractSource
from .modules.business.service import BusinessService
from .modules.identity.controller import create_router as identity_router
from .modules.identity.service import IdentityService
from .modules.invoice.controller import create_router as invoice_router
from .modules.invoice.service import InvoiceService
from .modules.matching.controller import create_router as matching_router
from .modules.matching.service import MatchingService
from .modules.reconciliation.controller import create_router as reconciliation_router
from .modules.reconciliation.service import ReconciliationService
from .modules.reconciliation.task_controller import create_router as invoice_task_router
from .modules.reconciliation.task_service import InvoiceTaskService
from .modules.sync.controller import create_router as sync_router
from .modules.sync.pull_service import PullService
from .modules.sync.service import ConnectionService
from .modules.writeback.controller import create_router as writeback_router
from .modules.writeback.service import WritebackService


def create_app(settings=None, ns=None, engine=None, business_engine=None):
    settings = settings or load_settings()
    owns_ns, owns_engine = ns is None, engine is None
    ns = ns or NetSuite(settings)
    engine = engine or make_engine(settings.database_url)
    owns_business_engine = business_engine is None
    business_engine = business_engine or make_business_engine(settings.business_database_url)
    contract_ns = NetSuite(connection_settings(settings)) if settings.subpo_connection_file else ns

    @asynccontextmanager
    async def lifespan(_app):
        try:
            verify_database(engine)
            yield
        finally:
            if owns_ns:
                ns.close()
            if contract_ns is not ns:
                contract_ns.close()
            if owns_engine:
                engine.dispose()
            if owns_business_engine and business_engine is not None:
                business_engine.dispose()

    app = FastAPI(title="NS 发票对账后端", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    identity = IdentityService(settings)
    app.state.identity = identity
    app.add_middleware(RequestGuard, secure=settings.origin.startswith("https://"))
    register_error_handlers(app)
    app.include_router(identity_router(identity, settings))
    business = BusinessService(ns, business_engine)
    app.include_router(business_router(business))
    app.include_router(create_database_router(business))
    app.include_router(
        reconciliation_router(
            ReconciliationService(
                settings, business.pl_script, engine, CustomsReconciliationSource(business_engine)
            )
        )
    )
    invoices = InvoiceService(business_engine)
    app.include_router(
        invoice_task_router(
            InvoiceTaskService(
                engine,
                CustomsReconciliationSource(business_engine),
                SubpoContractSource(contract_ns),
                ContractArchive(settings.subpo_archive_root),
            )
        )
    )
    app.include_router(invoice_router(invoices))
    app.include_router(
        matching_router(MatchingService(invoices, PurchaseMatchingSource(business_engine), business_engine))
    )
    app.include_router(
        sync_router(ConnectionService(settings, ns), PullService(settings, ns, business.storage))
    )
    app.include_router(writeback_router(WritebackService(settings, ns, engine)))

    @app.get("/api/health", tags=["基础设施"])
    def health():
        return {"status": "ok"}

    @app.get("/api/openapi.json", include_in_schema=False)
    def openapi(owner: Owner):
        return app.openapi()

    app.include_router(frontend_router(settings))
    return app

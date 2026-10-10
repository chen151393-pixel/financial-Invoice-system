"""应用装配：创建依赖、注册接口、管理生命周期。"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from .core.business_database import make_business_engine
from .core.config import load_settings
from .core.dependencies import Owner
from .core.frontend import create_router as frontend_router
from .core.middleware import RequestGuard, register_error_handlers
from .integrations.contract_archive import ContractArchive
from .integrations.netsuite.client import NetSuite
from .integrations.netsuite.subpo_contract import connection_settings
from .integrations.wecom import WeComGroups
from .manage import verify_database
from .modules.business.controller import create_router as business_router
from .modules.business.public import (
    CustomsReconciliationSource,
    PurchaseMatchingSource,
    SubpoContractSource,
    SupplierDirectory,
)
from .modules.business.service import BusinessService
from .modules.identity.controller import create_router as identity_router
from .modules.identity.service import IdentityService
from .modules.invoice.controller import create_router as invoice_router
from .modules.invoice.service import InvoiceService
from .modules.matching.controller import create_router as matching_router
from .modules.matching.service import MatchingService
from .modules.reconciliation.controller import create_router as reconciliation_router
from .modules.reconciliation.group_controller import create_router as supplier_group_router
from .modules.reconciliation.group_service import SupplierGroupService
from .modules.reconciliation.service import ReconciliationService
from .modules.reconciliation.task_controller import create_router as invoice_task_router
from .modules.reconciliation.task_service import InvoiceTaskService
from .modules.sync.controller import create_router as sync_router
from .modules.sync.pull_service import PullService
from .modules.sync.service import ConnectionService


def create_app(settings=None, ns=None, engine=None, business_engine=None, wecom=None):
    settings = settings or load_settings()
    # 正式运行共用业务库连接池；显式注入连接仅供隔离测试和预览。
    owns_engine = engine is None and business_engine is None
    engine = engine if engine is not None else business_engine
    if engine is None:
        if not settings.business_database_url:
            raise ValueError("请配置 BUSINESS_DATABASE_URL 或 BUSINESS_MYSQL_*，正式运行统一使用业务MySQL")
        engine = make_business_engine(settings.business_database_url)
    business_engine = business_engine if business_engine is not None else engine
    owns_ns, owns_wecom = ns is None, wecom is None
    wecom = wecom or WeComGroups(settings)
    ns = ns or NetSuite(settings)
    contract_ns = NetSuite(connection_settings(settings)) if settings.subpo_connection_file else ns

    @asynccontextmanager
    async def lifespan(_app):
        try:
            verify_database(engine, business=owns_engine)
            yield
        finally:
            if owns_wecom:
                wecom.close()
            if owns_ns:
                ns.close()
            if contract_ns is not ns:
                contract_ns.close()
            if owns_engine:
                engine.dispose()

    app = FastAPI(title="NS 发票对账后端", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    identity = IdentityService(settings)
    app.state.identity = identity
    app.add_middleware(RequestGuard, secure=settings.origin.startswith("https://"))
    register_error_handlers(app)
    app.include_router(identity_router(identity, settings))
    business = BusinessService(ns, business_engine)
    app.include_router(business_router(business))
    app.include_router(
        reconciliation_router(
            ReconciliationService(
                settings, business.pl_script, engine, CustomsReconciliationSource(business_engine)
            )
        )
    )
    supplier_groups = SupplierGroupService(
        business_engine, SupplierDirectory(business_engine), f"user:{settings.admin_user}", wecom=wecom
    )
    app.include_router(supplier_group_router(supplier_groups))
    invoices = InvoiceService(business_engine)
    app.include_router(
        invoice_task_router(
            InvoiceTaskService(
                engine,
                CustomsReconciliationSource(business_engine),
                SubpoContractSource(contract_ns),
                ContractArchive(settings.subpo_archive_root),
                supplier_groups=supplier_groups,
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

    @app.get("/api/health", tags=["基础设施"])
    def health():
        return {"status": "ok"}

    @app.get("/api/openapi.json", include_in_schema=False)
    def openapi(owner: Owner):
        return app.openapi()

    app.include_router(frontend_router(settings))
    return app

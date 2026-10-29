"""应用装配：创建依赖、注册接口、管理生命周期。"""

import asyncio
from contextlib import asynccontextmanager
from functools import partial

from fastapi import FastAPI

from .core.config import load_settings
from .core.database import make_business_engine
from .core.dependencies import Owner
from .core.events import EventBus
from .core.frontend import create_router as frontend_router
from .core.middleware import RequestGuard, register_error_handlers
from .integrations.contract_archive import ContractArchive
from .integrations.feishu import FeishuClient
from .integrations.lemon.existing_account import LemonExistingAccount
from .integrations.lemon.invoice_client import LemonInvoiceClient
from .integrations.netsuite.client import NetSuite
from .integrations.netsuite.subpo_contract import connection_settings
from .integrations.wecom import WeComGroups
from .integrations.wecom_messaging import WeComMessaging
from .manage import verify_database
from .modules.identity.controller.access_controller import create_router as identity_access_router
from .modules.identity.controller.feishu_controller import create_router as feishu_login_router
from .modules.identity.controller.session_controller import create_router as identity_router
from .modules.identity.service.access_reader import AccessReader
from .modules.identity.service.access_service import AccessService
from .modules.identity.service.directory_preview_service import DirectoryPreviewService
from .modules.identity.service.directory_sync_service import DirectorySyncService
from .modules.identity.service.directory_sync_worker import DirectorySyncWorker
from .modules.identity.service.feishu_login_service import FeishuLoginService
from .modules.identity.service.session_service import IdentityService
from .modules.invoice.controller.invoice_controller import create_router as invoice_router
from .modules.invoice.public import InvoiceChanged, InvoiceChanging, InvoicesImported, LemonInvoicesStored
from .modules.invoice.service.import_service import ImportService
from .modules.invoice.service.invoice_service import InvoiceService
from .modules.invoice.service.invoice_stats_service import InvoiceStatsService
from .modules.invoice.service.lemon_invoice_service import on_lemon_invoices_fetched
from .modules.matching.controller.invoice_file_controller import create_router as invoice_file_router
from .modules.matching.controller.matching_controller import create_router as matching_router
from .modules.matching.controller.workbench_controller import create_router as workbench_router
from .modules.matching.public import AllocationChanged, InvoiceMatchingChanged
from .modules.matching.service import ledger_service
from .modules.matching.service.allocation_service import AllocationService
from .modules.matching.service.invoice_file_service import InvoiceFileService
from .modules.matching.service.invoice_list_service import InvoiceListService
from .modules.matching.service.matching_query_service import MatchingQueryService
from .modules.matching.service.proposal_service import ProposalService, on_invoices_imported
from .modules.matching.service.workbench_service import WorkbenchService
from .modules.review.controller.review_controller import create_router as review_router
from .modules.review.public import PurchaseBasisInvalidated, ReviewApproved
from .modules.review.service.calculation_service import CalculationService, request_calculation
from .modules.review.service.calculation_worker import CalculationWorker
from .modules.review.service.purchase_basis_service import on_source_changed
from .modules.review.service.review_service import ReviewService
from .modules.source.controller.pl_comparison_controller import create_router as source_pl_router
from .modules.source.controller.vendor_bill_controller import create_router as vendor_bill_router
from .modules.source.public import DeclarationService, PlScriptService, SourceChanged, SourceDirectory
from .modules.source.public import SubpoContractSource as SourceContracts
from .modules.source.service.storage_service import StorageService as SourceStorageService
from .modules.source.service.vendor_bill_query_service import VendorBillQueryService
from .modules.sync.controller import create_router as sync_router
from .modules.sync.controller.lemon_batch_controller import create_router as lemon_batch_router
from .modules.sync.controller.lemon_binding_controller import create_router as lemon_binding_router
from .modules.sync.controller.lemon_invoice_controller import create_router as lemon_invoice_router
from .modules.sync.controller.ns_run_controller import create_router as ns_run_router
from .modules.sync.controller.sync_health_controller import create_router as sync_health_router
from .modules.sync.public import LemonInvoicesFetched
from .modules.sync.pull_service import PullService
from .modules.sync.service import ConnectionService
from .modules.sync.service.lemon_account_service import LemonAccountService
from .modules.sync.service.lemon_batch_service import LemonBatchService
from .modules.sync.service.lemon_binding_service import LemonBindingService
from .modules.sync.service.lemon_invoice_service import LemonInvoiceService, on_lemon_invoices_stored
from .modules.sync.service.lemon_job_service import LemonJobService
from .modules.sync.service.lemon_plan_service import LemonPlanService
from .modules.sync.service.lemon_worker import LemonWorker
from .modules.sync.service.ns_run_service import NsRunService
from .modules.sync.service.sync_health_service import SyncHealthService
from .modules.task.controller.board_controller import create_router as task_board_router
from .modules.task.controller.delivery_controller import create_router as delivery_router
from .modules.task.controller.external_group_controller import create_router as external_group_router
from .modules.task.controller.signed_contract_controller import create_router as signed_contract_router
from .modules.task.controller.signed_upload_controller import JSON_BODY_LIMITS
from .modules.task.controller.signed_upload_controller import create_router as signed_upload_router
from .modules.task.controller.supplier_group_controller import create_router as task_group_router
from .modules.task.controller.task_controller import create_router as task_router
from .modules.task.service.closure_service import ClosureService
from .modules.task.service.contract_worker import ContractWorker
from .modules.task.service.declaration_document_service import DeclarationDocumentService
from .modules.task.service.delivery_receipt_service import DeliveryReceiptService
from .modules.task.service.delivery_reconcile_service import DeliveryReconcileService
from .modules.task.service.delivery_submit_service import DeliverySubmitService
from .modules.task.service.document_service import DocumentService
from .modules.task.service.external_group_service import ExternalGroupService
from .modules.task.service.group_import_preview import GroupImportPreview
from .modules.task.service.group_import_service import GroupImportService
from .modules.task.service.notification_service import NotificationService
from .modules.task.service.progress_service import on_allocation_changed
from .modules.task.service.signed_contract_service import SignedContractService
from .modules.task.service.signed_upload_service import SignedUploadService
from .modules.task.service.signed_upload_store import SignedUploadStore
from .modules.task.service.signed_upload_worker import SignedUploadWorker
from .modules.task.service.supplier_group_service import SupplierGroupService as TaskGroupService
from .modules.task.service.supplier_profile_service import SupplierProfileService
from .modules.task.service.task_board_service import TaskBoardService
from .modules.task.service.task_generation_service import on_review_approved
from .modules.task.service.task_service import TaskService
from .modules.writeback.controller.task_controller import create_router as writeback_router
from .modules.writeback.policy.write_gate import WriteGate
from .modules.writeback.service.execute_service import ExecuteService as WritebackExecutor
from .modules.writeback.service.prepare_worker import PrepareWorker
from .modules.writeback.service.query_service import QueryService as WritebackQueries
from .modules.writeback.service.queue_service import on_matching_changed
from .modules.writeback.service.task_service import TaskService as WritebackTasks


def create_app(settings=None, ns=None, engine=None, wecom=None, lemon=None, lemon_invoices=None, feishu=None):
    settings = settings or load_settings()
    owns_engine = engine is None
    if engine is None:
        if not settings.business_database_url:
            raise ValueError("请配置 BUSINESS_DATABASE_URL 或 BUSINESS_MYSQL_*，正式运行统一使用业务MySQL")
        engine = make_business_engine(settings.business_database_url)
    owns_lemon = lemon is None
    lemon = lemon or LemonExistingAccount(settings)
    owns_lemon_invoices = lemon_invoices is None
    lemon_invoices = lemon_invoices or LemonInvoiceClient(settings, lemon)
    owns_ns, owns_wecom, owns_feishu = ns is None, wecom is None, feishu is None
    feishu = feishu or FeishuClient(settings)
    wecom = wecom or WeComGroups(settings)
    ns = ns or NetSuite(settings)
    contract_ns = NetSuite(connection_settings(settings)) if settings.subpo_connection_file else ns

    @asynccontextmanager
    async def lifespan(_app):
        try:
            verify_database(engine)
            app.state.contract_worker.start()
            app.state.signed_upload_worker.start()
            app.state.lemon_worker.start()
            app.state.review_calculation_worker.start()
            app.state.directory_sync_worker.start()
            app.state.writeback_prepare_worker.start()
            yield
        finally:
            if hasattr(app.state, "writeback_prepare_worker"):
                await asyncio.to_thread(app.state.writeback_prepare_worker.stop)
            if hasattr(app.state, "directory_sync_worker"):
                await asyncio.to_thread(app.state.directory_sync_worker.stop)
            if hasattr(app.state, "review_calculation_worker"):
                await asyncio.to_thread(app.state.review_calculation_worker.stop)
            if hasattr(app.state, "signed_upload_worker"):
                await asyncio.to_thread(app.state.signed_upload_worker.stop)
            if hasattr(app.state, "lemon_worker"):
                await asyncio.to_thread(app.state.lemon_worker.stop)
            if hasattr(app.state, "contract_worker"):
                await asyncio.to_thread(app.state.contract_worker.stop)
            if hasattr(app.state, "ns_runs"):
                await asyncio.to_thread(app.state.ns_runs.stop)
            if owns_lemon_invoices:
                lemon_invoices.close()
            if owns_lemon:
                lemon.close()
            if owns_wecom:
                await asyncio.to_thread(wecom.close)
            if owns_feishu:
                feishu.close()
            if owns_ns:
                ns.close()
            if contract_ns is not ns:
                contract_ns.close()
            if owns_engine:
                engine.dispose()

    app = FastAPI(title="NS 发票对账后端", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    identity = IdentityService(settings, AccessReader(engine))
    app.state.identity = identity
    app.add_middleware(
        RequestGuard, secure=settings.origin.startswith("https://"), json_body_limits=JSON_BODY_LIMITS
    )
    register_error_handlers(app)
    app.include_router(identity_router(identity, settings, feishu))
    app.include_router(
        feishu_login_router(FeishuLoginService(engine, feishu, identity, identity.access, settings), settings)
    )
    directory_sync = DirectorySyncService(engine, feishu)
    app.state.directory_sync_worker = DirectorySyncWorker(directory_sync)
    app.include_router(
        identity_access_router(
            AccessService(engine, identity, feishu),
            directory_sync,
            identity,
            DirectoryPreviewService(engine, identity, feishu),
        )
    )
    app.state.lemon_binding = LemonBindingService(
        settings, engine, lemon, require_admin=identity.require_admin
    )
    app.include_router(lemon_binding_router(app.state.lemon_binding))
    _register_business(app, settings, ns, contract_ns, wecom, engine, lemon_invoices)

    @app.get("/api/health", tags=["基础设施"])
    def health():
        return {"status": "ok"}

    @app.get("/api/openapi.json", include_in_schema=False)
    def openapi(owner: Owner):
        return app.openapi()

    app.include_router(frontend_router(settings))
    return app


def create_events(*, writeback_queue_enabled=True):
    """关联写的订阅次序：任务生成/换版先于匹配重算，订阅方复用同一事务。"""
    events = EventBus()
    events.subscribe(InvoiceMatchingChanged, partial(on_matching_changed, enabled=writeback_queue_enabled))
    events.subscribe(SourceChanged, partial(on_source_changed, events=events))
    events.subscribe(PurchaseBasisInvalidated, partial(ledger_service.on_basis_invalidated, events=events))
    events.subscribe(ReviewApproved, on_review_approved)
    events.subscribe(ReviewApproved, partial(ledger_service.on_review_approved, events=events))
    events.subscribe(SourceChanged, request_calculation)
    events.subscribe(ReviewApproved, request_calculation)
    events.subscribe(InvoiceChanging, ledger_service.on_invoice_changing)
    events.subscribe(InvoiceChanged, partial(ledger_service.on_invoice_changed, events=events))
    events.subscribe(InvoicesImported, on_invoices_imported)
    events.subscribe(LemonInvoicesFetched, partial(on_lemon_invoices_fetched, events=events))
    events.subscribe(LemonInvoicesStored, on_lemon_invoices_stored)
    events.subscribe(AllocationChanged, on_allocation_changed)
    return events


def _register_business(app, settings, ns, contract_ns, wecom, engine, lemon_invoices):
    events = create_events(writeback_queue_enabled=settings.writeback_queue_enabled)
    lemon_accounts = LemonAccountService(app.state.lemon_binding, lemon_invoices)
    lemon_service = LemonInvoiceService(lemon_accounts, events)
    app.include_router(lemon_invoice_router(lemon_accounts, lemon_service))
    batches = LemonBatchService(lemon_accounts)
    plans = LemonPlanService(batches)
    app.include_router(lemon_batch_router(batches, plans))
    app.state.lemon_worker = LemonWorker(plans, LemonJobService(batches, lemon_service))
    pl_comparison = PlScriptService(ns, engine)
    app.include_router(source_pl_router(pl_comparison))
    app.include_router(vendor_bill_router(VendorBillQueryService(ns)))
    # source 保存来源，review 冻结依据，task 订阅审核通过生成任务。
    source_storage = SourceStorageService(ns, engine, events)
    declarations = DeclarationService(engine)
    review = ReviewService(engine, declarations, events, settings.review_unit_price_tolerance_cny)
    app.state.review_calculations = CalculationService(review)
    app.state.review_calculation_worker = CalculationWorker(app.state.review_calculations)
    app.include_router(review_router(review))
    directory = SourceDirectory(engine)
    app.include_router(
        external_group_router(
            GroupImportPreview(engine, directory),
            GroupImportService(engine, directory),
            ExternalGroupService(engine, directory),
        )
    )
    archive = ContractArchive(settings.subpo_archive_root)
    task_queries = TaskService(engine, directory, SourceContracts(contract_ns), archive, settings)
    messaging = WeComMessaging(wecom)
    receipts = DeliveryReceiptService(engine, messaging)
    app.include_router(
        delivery_router(
            DeliverySubmitService(engine, settings, messaging, task_queries),
            receipts,
            DeliveryReconcileService(engine, messaging, receipts),
        )
    )
    documents = DocumentService(engine, directory, SourceContracts(contract_ns), archive, task_queries)
    declaration_documents = DeclarationDocumentService(
        engine, directory, SourceContracts(contract_ns), archive, task_queries
    )
    app.state.contract_worker = ContractWorker(engine, documents, declaration_documents)
    app.include_router(
        task_group_router(
            TaskGroupService(engine, directory, wecom), SupplierProfileService(engine, directory)
        )
    )
    app.include_router(
        task_router(
            task_queries,
            documents,
            NotificationService(engine, task_queries),
            ClosureService(engine, task_queries),
            declaration_documents,
        )
    )
    app.include_router(task_board_router(TaskBoardService(engine, directory, task_queries)))
    signed_contracts = SignedContractService(engine, directory, archive)
    app.include_router(signed_contract_router(signed_contracts))
    upload_store = SignedUploadStore(settings.signed_upload_root)
    app.state.signed_uploads = SignedUploadService(engine, upload_store)
    app.state.signed_upload_worker = SignedUploadWorker(engine, upload_store, signed_contracts)
    app.include_router(signed_upload_router(app.state.signed_uploads))
    # 发票导入 → matching 生成比对建议；比对通过 / 取消 → task 重算收票进度（均在发布方事务中）。
    app.include_router(
        invoice_router(ImportService(engine, events), InvoiceService(engine), InvoiceStatsService(engine))
    )
    matching_queries = MatchingQueryService(engine)
    writeback_tasks = WritebackTasks(
        engine,
        settings.account,
        queue_enabled=settings.writeback_queue_enabled,
        gate=WriteGate(settings),
    )
    writeback_queries = WritebackQueries(writeback_tasks, VendorBillQueryService(ns))
    writeback_executor = WritebackExecutor(writeback_tasks, ns)
    app.include_router(writeback_router(writeback_tasks, writeback_queries, writeback_executor))
    # 写入开关开启且写入接口已配置时，后台自动写入已就绪任务；白名单在每个任务上再判断。
    auto_write = settings.write_enabled and bool(settings.vendor_bill_writeback_script)
    app.state.writeback_prepare_worker = PrepareWorker(
        writeback_tasks,
        writeback_queries,
        enabled=settings.writeback_query_enabled and bool(settings.vendor_bill_query_script),
        executor=writeback_executor if auto_write else None,
    )
    app.include_router(workbench_router(WorkbenchService(engine)))
    app.include_router(
        matching_router(
            matching_queries,
            AllocationService(engine, events, matching_queries),
            ProposalService(engine),
            InvoiceListService(engine),
        )
    )
    app.include_router(invoice_file_router(InvoiceFileService(engine, directory, archive)))
    pulls = PullService(settings, ns, source_storage)
    app.include_router(sync_router(ConnectionService(settings, ns), pulls))
    app.state.ns_runs = NsRunService(engine, pulls)
    app.include_router(ns_run_router(app.state.ns_runs))
    app.include_router(sync_health_router(SyncHealthService(engine)))

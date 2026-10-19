"""柠檬云账套及手动拉票 HTTP 边界。"""

from fastapi import APIRouter

from backend.core.dependencies import Owner

from ..dto.lemon_detail_dto import LemonDetailSelection, RefreshLemonDetails
from ..dto.lemon_invoice_dto import PullLemonInvoices, SelectLemonAccount
from ..service.lemon_detail_refresh_service import LemonDetailRefreshService
from ..vo.lemon_detail_vo import LemonDetailActions
from ..vo.lemon_invoice_vo import LemonAccounts, LemonConfiguration, LemonRun


def create_router(accounts, service):
    router = APIRouter(prefix="/api/sync/lemon", tags=["柠檬云进项发票同步"])
    details = LemonDetailRefreshService(service)

    @router.post("/invoices/detail-actions", response_model=LemonDetailActions)
    def detail_actions(body: LemonDetailSelection, owner: Owner):
        return details.actions(owner, body)

    @router.post("/invoices/refresh-details", response_model=LemonRun)
    def refresh_details(body: RefreshLemonDetails, owner: Owner):
        return details.refresh(owner, body)

    @router.get("/invoices/configuration", response_model=LemonConfiguration)
    def configuration(owner: Owner):
        return accounts.configuration(owner)

    @router.post("/accounts/query", response_model=LemonAccounts)
    def query(owner: Owner):
        return accounts.query(owner)

    @router.post("/account", response_model=LemonConfiguration)
    def select(body: SelectLemonAccount, owner: Owner):
        return accounts.select(owner, body.asid)

    @router.post("/invoices/pull-save", response_model=LemonRun)
    def pull(body: PullLemonInvoices, owner: Owner):
        return service.pull(owner, body)

    @router.get("/runs/{request_id}", response_model=LemonRun)
    def result(request_id: str, owner: Owner):
        return service.read(owner, request_id)

    return router

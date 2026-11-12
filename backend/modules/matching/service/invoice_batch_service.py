"""每张发票一个账本事务；只审核完整、当前置信度 100% 的待审整单建议。"""

from backend.core.errors import ApiError
from backend.modules.invoice.public import read_invoices

from ..dao import allocation_dao
from ..dto.matching_dto import GroupConfirmBody
from ..policy.pending_order_policy import REGENERATE, whole_order
from . import group_view_service


def _approve(service, connection, item, note, actor):
    invoice_id = int(item.invoiceId)
    found = read_invoices(connection, [invoice_id])
    if not found:
        raise ApiError(404, "发票不存在")
    if str(found[0]["current_version_id"]) != item.invoiceVersionId:
        raise ApiError(409, "发票版本已变化，请刷新后重新核对")
    rows = allocation_dao.by_invoices(connection, [invoice_id])
    wanted = {int(value) for value in item.allocationIds}
    selected = [row for row in rows if row["id"] in wanted]
    proposed = [row for row in rows if row["status"] == "proposed"]
    if len(selected) != len(wanted):
        raise ApiError(409, "建议不存在或不属于该发票，请刷新后重新核对")
    # 同一人重复提交已全部成功的原集合，不重复分配或覆盖审核记录。
    if not proposed and all(
        row["status"] == "confirmed"
        and row["reviewed_by"] == actor
        and row["verification_status"] == "valid"
        and str(row["invoice_version_id"]) == item.invoiceVersionId
        for row in selected
    ):
        return invoice_id
    if {row["id"] for row in proposed} != wanted:
        raise ApiError(409, "待审核建议已变化，请刷新后重新勾选整张发票")
    if any(not whole_order(row) or not group_view_service.group_id(row) for row in proposed):
        raise ApiError(409, REGENERATE)
    body = GroupConfirmBody(invoiceId=item.invoiceId, invoiceVersionId=item.invoiceVersionId, note=note)
    for own in group_view_service.grouped(proposed).values():
        group_view_service.approve_rows(service, connection, own, body, actor, batch=True)
    return invoice_id


def confirm(service, body, actor):
    approved, skipped = [], []
    for item in body.items:
        try:
            service._run(lambda connection: _approve(service, connection, item, body.note, actor), actor)
        except ApiError as error:
            if error.status not in (400, 404, 409, 422):
                raise  # 数据库不可用等停止后续；已完成发票不回滚，不自动重发。
            skipped.append({"id": item.invoiceId, "reason": error.message})
        else:
            approved.append({"id": item.invoiceId})
    return {"approved": approved, "skipped": skipped}

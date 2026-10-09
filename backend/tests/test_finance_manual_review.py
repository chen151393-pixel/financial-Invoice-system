"""人工整单审核：未完成机器逐行匹配仍可审核，保存来源快照并防止过期确认。"""

import json
import time

import pytest
from backend.core.errors import ApiError
from backend.modules.audit.entity import finance_audit
from backend.modules.business.entity import load_tables
from backend.modules.reconciliation import service as review_module
from backend.modules.reconciliation.dto import ApproveRequest, DeclarationListQuery
from backend.modules.reconciliation.entity import reviews, snapshots
from backend.modules.reconciliation.service import ReconciliationService
from backend.tests.test_finance_list import OWNER
from backend.tests.test_finance_list import local_source as local_source
from sqlalchemy import func, select


def context_service(context, local_source):
    service = ReconciliationService(context.settings, None, context.engine, local_source)
    group = service.browse(DeclarationListQuery(keyword="CD001"), OWNER).groups[0]
    return service, group


def test_manual_review_without_line_matching_persists_scope_and_is_idempotent(context, local_source):
    service, group = context_service(context, local_source)
    assert group.review.status == "pending" and group.review.allowed
    assert not group.warnings and not group.review.reason
    assert len(group.unlinkedLines) == 2 and not group.customsLines[0].purchaseLines
    body = ApproveRequest(snapshotId=group.snapshotId, note="财务已核对")
    result = service.approve(body, OWNER)
    retry = service.approve(ApproveRequest(snapshotId=group.snapshotId, note="不覆盖原备注"), OWNER)
    assert result.review.status == retry.review.status == "approved"
    assert retry.review.note == "财务已核对"
    assert result.unlinkedLines[0].scope == "order"
    assert result.unlinkedLines[0].amount == "9007199254740993.01"
    with context.engine.connect() as connection:
        assert connection.execute(select(func.count()).select_from(finance_audit)).scalar_one() == 1
        saved = connection.execute(
            select(snapshots.c.payload).where(snapshots.c.id == group.snapshotId)
        ).scalar_one()
        payload = json.loads(saved)
        assert payload["source"] == "database"
        assert payload["content"]["purchaseLines"][0]["amount"] == "9007199254740993.01"
    page = service.browse(DeclarationListQuery(status="approved"), OWNER)
    assert page.total == page.counts["approved"] == 1 and page.counts["pending"] == 2
    assert not context.ns.writes


@pytest.mark.parametrize("change", ["quantity", "membership", "inactive"])
def test_local_source_change_rejects_preview_and_removes_old_approval(context, local_source, change):
    service, group = context_service(context, local_source)
    body = ApproveRequest(snapshotId=group.snapshotId)
    service.approve(body, OWNER)
    with local_source.engine.begin() as connection:
        tables = load_tables(connection)
        if change == "quantity":
            table = tables["purchase_order_lines"]
            connection.execute(table.update().where(table.c.id == 1).values(quantity="2"))
        elif change == "membership":
            table = tables["purchase_orders"]
            connection.execute(table.update().where(table.c.id == 1).values(customs_declaration_id=None))
        else:
            table = tables["customs_declarations"]
            connection.execute(table.update().where(table.c.id == 1).values(is_active=0))
    with pytest.raises(ApiError) as error:
        service.approve(body, OWNER)
    assert error.value.status == 409
    assert service.browse(DeclarationListQuery(status="approved"), OWNER).total == 0
    with context.engine.connect() as connection:
        assert connection.execute(select(func.count()).select_from(finance_audit)).scalar_one() == 1


def test_expiry_permissions_and_audit_failure_do_not_confirm(context, local_source, monkeypatch):
    service, group = context_service(context, local_source)
    body = ApproveRequest(snapshotId=group.snapshotId)
    with pytest.raises(ApiError) as denied:
        service.approve(body, "service:reader")
    assert denied.value.status == 403
    with context.engine.begin() as connection:
        connection.execute(
            snapshots.update()
            .where(snapshots.c.id == group.snapshotId)
            .values(expires_at=int(time.time()) - 1)
        )
    with pytest.raises(ApiError, match="过期"):
        service.approve(body, OWNER)
    _, group = context_service(context, local_source)

    def fail_audit(*args, **kwargs):
        raise ApiError(503, "审计写入失败")

    monkeypatch.setattr(review_module, "record_finance_review", fail_audit)
    with pytest.raises(ApiError, match="审计"):
        service.approve(ApproveRequest(snapshotId=group.snapshotId), OWNER)
    with context.engine.connect() as connection:
        assert (
            connection.execute(
                select(func.count()).select_from(reviews).where(reviews.c.digest.is_not(None))
            ).scalar_one()
            == 0
        )
        assert connection.execute(select(func.count()).select_from(finance_audit)).scalar_one() == 0


def test_no_purchase_data_stays_pending_with_specific_disabled_reason(context, local_source):
    service = ReconciliationService(context.settings, None, context.engine, local_source)
    group = service.browse(DeclarationListQuery(keyword="CD005"), OWNER).groups[0]
    assert group.review.status == "pending" and not group.review.allowed and not group.snapshotId
    assert "暂无" in group.review.reason and "关联核实" not in group.review.reason

"""真实Service/事务/API验证，NS采用明确标记的合成来源，不访问真实账套。"""

import copy
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from backend.app import create_app
from backend.core.errors import ApiError
from backend.modules.audit.entity import finance_audit
from backend.modules.business.dto import PlScriptQuery
from backend.modules.business.pl_script_service import PlScriptService
from backend.modules.reconciliation.dto import ApproveRequest, ReviewQuery
from backend.modules.reconciliation.entity import reviews, snapshots
from backend.modules.reconciliation.service import ReconciliationService
from backend.tests.test_api import login
from backend.tests.test_pl_script import result
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update
from sqlalchemy.exc import SQLAlchemyError

OWNER = "user:admin"


def source_result(account):
    data = result(2)
    data.update(contractVersion=3, account=account)
    group = data["groups"][0]
    group.update(declarationId="101", recordNumber="CDTEST001", warnings=[], reviewIssues=[])
    customs, purchase = group["rows"]
    customs.update(sourceKey="customs:source:301")
    customs["cells"] = [
        "合成报关号",
        "2026-09-01",
        "PL-TEST",
        "SO-TEST",
        "PO-TEST",
        "",
        "",
        "",
        "合成申报公司",
        "相纸",
        "A4",
        "12.5000",
        "千克",
        "2.00",
        "25.00",
        "2.00",
        "USD",
    ]
    purchase.update(sourceKey="purchase:source:401", customsRowId="customs:0", currency="CNY")
    purchase["cells"] = [
        "",
        "",
        "PL-TEST",
        "",
        "PO-TEST",
        "SUB-TEST",
        "",
        "合成供应商",
        "合成申报公司",
        "相纸",
        "A4",
        "12.5000",
        "千克",
        "10.00",
        "125.00",
        "",
        "",
    ]
    return data


@pytest.fixture
def review_context(context):
    data = source_result(context.settings.account)
    calls = []

    def query(criteria):
        calls.append(criteria)
        response = copy.deepcopy(data)
        response["query"] = criteria
        return response

    context.ns.pl_script_query = query
    context.service = ReconciliationService(context.settings, PlScriptService(context.ns), context.engine)
    context.data, context.calls = data, calls
    return context


def query(context, **kwargs):
    return context.service.query(
        ReviewQuery(criteria=PlScriptQuery(type="customsRecord", pl="CDTEST001"), **kwargs), OWNER
    )


def approve(context, group, note="已核实本次已报关范围"):
    return context.service.approve(ApproveRequest(snapshotId=group.snapshotId, note=note), OWNER)


def test_real_relations_and_original_decimal_strings(review_context):
    context = review_context
    group = query(context).groups[0]
    assert group.review.allowed
    assert group.customsLines[0].purchaseLines[0].amount == "125.00"
    assert group.customsLines[0].purchaseLines[0].quantity == "12.5000"
    # 同品名且相邻也不形成关系：只有显式父行引用决定归属。
    row = copy.deepcopy(context.data["groups"][0]["rows"][0])
    row.update(id="customs:1", sourceKey="customs:source:302")
    context.data["groups"][0]["rows"].insert(1, row)
    context.data["groups"][0]["customsCount"] = 2
    context.data["counts"]["customs"] = 2
    actual = query(context).groups[0]
    assert actual.customsLines[0].purchaseCount == 1
    assert actual.customsLines[1].purchaseCount == 0
    assert not actual.review.allowed


def test_approval_persists_scope_audit_and_idempotency(review_context):
    context = review_context
    group = query(context).groups[0]
    saved = approve(context, group)
    assert saved.review.status == "approved"
    assert saved.review.reviewedBy == OWNER
    assert (
        context.calls[-1]
        == PlScriptQuery(type="customsRecord", pl="CDTEST001", showIncomplete=True).model_dump()
    )
    with context.engine.begin() as connection:
        connection.execute(update(snapshots).values(expires_at=0))
    # 成功后的网络重试即使预览过期也返回原记录，不再次读取NS或替换备注。
    call_count = len(context.calls)
    assert approve(context, group, "不应覆盖原备注").review == saved.review
    assert len(context.calls) == call_count
    context.service = ReconciliationService(context.settings, PlScriptService(context.ns), context.engine)
    assert query(context, status="approved").counts["approved"] == 1
    assert query(context, status="pending").groups == []
    with context.engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(finance_audit)) == 1
        assert connection.scalar(select(reviews.c.revision)) == 1
    assert context.ns.writes == []


@pytest.mark.parametrize("version", [1, 2])
def test_legacy_source_keeps_unlinked_rows_and_blocks_approval(review_context, version):
    context = review_context
    context.data["contractVersion"] = version
    if version == 1:
        for row in context.data["groups"][0]["rows"]:
            row["cells"] = row["cells"][:15]
    group = query(context).groups[0]
    assert len(group.unlinkedLines) == 1
    assert group.customsLines[0].purchaseLines == []
    assert not group.review.allowed
    with pytest.raises(ApiError, match="明确的行关联"):
        approve(context, group)


@pytest.mark.parametrize("change", ["amount", "quantity", "parent", "currency"])
def test_changed_source_invalidates_preview_and_old_approval(review_context, change):
    context = review_context
    group = query(context).groups[0]
    row = context.data["groups"][0]["rows"][1]
    if change == "amount":
        row["cells"][14] = "126.00"
    elif change == "quantity":
        row["cells"][11] = "13.00"
    elif change == "parent":
        row["customsRowId"] = None
    else:
        row["currency"] = "USD"
    with pytest.raises(ApiError, match="已变化"):
        approve(context, group)
    with context.engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(finance_audit)) == 0


def test_changed_data_requires_new_review_after_previous_approval(review_context):
    context = review_context
    approve(context, query(context).groups[0])
    context.data["groups"][0]["rows"][1]["cells"][14] = "126.00"
    changed = query(context).groups[0]
    assert changed.review.status == "pending" and changed.warnings
    approve(context, changed)
    with context.engine.connect() as connection:
        assert connection.scalar(select(reviews.c.revision)) == 2


def test_stale_preview_cannot_overwrite_newer_approval_even_if_source_reverts(review_context):
    context = review_context
    old = query(context).groups[0]
    context.data["groups"][0]["rows"][1]["cells"][14] = "126.00"
    current = query(context).groups[0]
    approve(context, current)
    context.data["groups"][0]["rows"][1]["cells"][14] = "125.00"
    with pytest.raises(ApiError, match="其他请求审核"):
        approve(context, old)
    with context.engine.connect() as connection:
        assert connection.scalar(select(reviews.c.snapshot_id)) == current.snapshotId
        assert connection.scalar(select(func.count()).select_from(finance_audit)) == 1


@pytest.mark.parametrize(
    "change", ["identity", "source", "amount", "quantity", "currency", "parent", "issue"]
)
def test_missing_or_invalid_scope_is_blocked(review_context, change):
    context = review_context
    group = context.data["groups"][0]
    row = group["rows"][1]
    if change == "identity":
        group["declarationId"] = ""
    elif change == "source":
        row["sourceKey"] = ""
    elif change == "amount":
        row["cells"][14] = "NaN"
    elif change == "quantity":
        row["cells"][11] = "0"
    elif change == "currency":
        row["currency"] = ""
    elif change == "parent":
        row["customsRowId"] = None
    else:
        group["reviewIssues"] = ["来源追溯存在歧义"]
    actual = query(context).groups[0]
    assert not actual.review.allowed and actual.review.reason
    with pytest.raises(ApiError):
        approve(context, actual)


def test_partial_pl_scope_and_expiry_blocked(review_context):
    context = review_context
    scoped = context.service.query(ReviewQuery(criteria=PlScriptQuery(pl="PL-TEST")), OWNER).groups[0]
    assert "完整报关单" in scoped.review.reason
    group = query(context).groups[0]
    with context.engine.begin() as connection:
        connection.execute(
            update(snapshots)
            .where(snapshots.c.id == group.snapshotId)
            .values(expires_at=int(time.time()) - 1)
        )
    with pytest.raises(ApiError, match="已过期"):
        approve(context, group)


def test_audit_failure_rolls_back_approval(review_context, monkeypatch):
    context = review_context
    group = query(context).groups[0]

    def fail(*args, **kwargs):
        raise SQLAlchemyError("test failure")

    monkeypatch.setattr("backend.modules.reconciliation.service.record_finance_review", fail)
    with pytest.raises(ApiError, match="结果暂无法确认"):
        approve(context, group)
    with context.engine.connect() as connection:
        assert connection.scalar(select(reviews.c.revision)) == 0
        assert connection.scalar(select(reviews.c.snapshot_id)) is None


def test_api_identity_scope_csrf_and_untrusted_fields(review_context):
    context = review_context
    with TestClient(create_app(context.settings, context.ns, context.engine)) as client:
        body = {"criteria": {"type": "customsRecord", "pl": "CDTEST001"}}
        assert client.post("/api/reconciliation/query", json=body).status_code == 401
        login(client, context)
        headers = {"Origin": context.settings.origin}
        response = client.post("/api/reconciliation/query", json=body, headers=headers)
        assert response.status_code == 200
        group = response.json()["groups"][0]
        request = {"snapshotId": group["snapshotId"]}
        assert client.post("/api/reconciliation/approve", json=request).status_code == 403
        assert (
            client.post(
                "/api/reconciliation/approve",
                json={**request, "amount": "1", "role": "admin"},
                headers=headers,
            ).status_code
            == 400
        )
        service_headers = {"Authorization": f"Bearer {context.settings.service_key}"}
        client.cookies.clear()
        assert (
            client.post("/api/reconciliation/approve", json=request, headers=service_headers).status_code
            == 403
        )
        login(client, context)
        context.settings.account = "other-account"
        assert client.post("/api/reconciliation/approve", json=request, headers=headers).status_code == 404
        assert context.ns.writes == []


def concurrent_approval(context):
    """供独立MySQL测试复用；SQLite不能证明行锁及真实并发行为。"""
    first, second = query(context).groups[0], query(context).groups[0]
    barrier = Barrier(2)
    source_query = context.service.source.query

    def synchronized(criteria):
        data = source_query(criteria)
        barrier.wait(timeout=10)
        return data

    context.service.source.query = synchronized
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda group: approve(context, group), [first, second]))
    assert all(item.review.status == "approved" for item in results)
    with context.engine.connect() as connection:
        assert connection.scalar(select(reviews.c.revision)) == 1
        assert connection.scalar(select(func.count()).select_from(finance_audit)) == 1


def test_invalid_parent_reference_or_duplicate_declaration_rejected(review_context):
    context = review_context
    context.data["groups"][0]["rows"][1]["customsRowId"] = "other-group-row"
    with pytest.raises(ApiError, match="契约或完整性"):
        query(context)
    context.data["groups"][0]["rows"][1]["customsRowId"] = "customs:0"
    duplicate = copy.deepcopy(context.data["groups"][0])
    duplicate["id"] = "other-display-group"
    context.data["groups"].append(duplicate)
    context.data["counts"].update(groups=2, customs=2, purchase=2)
    with pytest.raises(ApiError, match="契约或完整性"):
        query(context)

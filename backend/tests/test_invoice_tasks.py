"""审核派生任务：真实迁移、事务回滚、版本及分组隔离，不调用外部通知。"""

import copy

import pytest
from backend.app import create_app
from backend.core.errors import ApiError
from backend.modules.audit.entity import finance_audit
from backend.modules.business.entity import load_tables
from backend.modules.reconciliation import task_dao
from backend.modules.reconciliation.dto import ApproveRequest, DeclarationListQuery, TaskListQuery
from backend.modules.reconciliation.entity import reviews
from backend.modules.reconciliation.service import ReconciliationService
from backend.modules.reconciliation.task_entity import tasks
from backend.modules.reconciliation.task_policy import split_scope
from backend.modules.reconciliation.task_service import InvoiceTaskService
from backend.tests.test_api import login
from backend.tests.test_finance_list import OWNER
from backend.tests.test_finance_list import local_source as local_source
from backend.tests.test_reconciliation import review_context as review_context
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select
from sqlalchemy.exc import SQLAlchemyError


def approve(context, source):
    service = ReconciliationService(context.settings, None, context.engine, source)
    group = service.browse(DeclarationListQuery(keyword="CD001"), OWNER).groups[0]
    return service, group, service.approve(ApproveRequest(snapshotId=group.snapshotId), OWNER)


def test_approval_creates_once_with_immutable_original_amount(context, local_source):
    service, group, saved = approve(context, local_source)
    again = service.approve(ApproveRequest(snapshotId=group.snapshotId), OWNER)
    assert saved.invoiceTaskCount == again.invoiceTaskCount == 1
    followup = InvoiceTaskService(context.engine, local_source)
    result = followup.browse(TaskListQuery(), OWNER)
    assert result.total == result.counts.awaitingInvoice == result.counts.needsAttention == 1
    assert result.counts.receivedInvoices is None
    task = result.groups[0].tasks[0]
    assert task.expectedAmount is None and task.status == "documents_pending"
    detail = followup.detail(task.id, OWNER)
    assert detail.sourceStatus == "current"
    assert detail.lines[0].amount == "9007199254740993.01"
    assert not detail.notify.allowed and not detail.prepare.allowed
    assert task.snapshotId == group.snapshotId and task.lineCount == 2
    assert not context.ns.writes


def test_creation_failure_rolls_back_review_and_audit(context, local_source, monkeypatch):
    service = ReconciliationService(context.settings, None, context.engine, local_source)
    group = service.browse(DeclarationListQuery(keyword="CD001"), OWNER).groups[0]

    def fail(*args):
        raise SQLAlchemyError("synthetic task insert failed")

    with monkeypatch.context() as patch:
        patch.setattr(task_dao, "replace_revision", fail)
        with pytest.raises(ApiError) as error:
            service.approve(ApproveRequest(snapshotId=group.snapshotId), OWNER)
        assert error.value.status == 503
    with context.engine.connect() as connection:
        assert connection.execute(select(reviews.c.digest)).scalar_one() is None
        assert connection.execute(select(func.count()).select_from(finance_audit)).scalar_one() == 0
        assert connection.execute(select(func.count()).select_from(tasks)).scalar_one() == 0
    assert service.approve(ApproveRequest(snapshotId=group.snapshotId), OWNER).invoiceTaskCount == 1


def test_new_approval_supersedes_old_task_and_both_views_use_same_ids(context, local_source):
    service, group, saved = approve(context, local_source)
    followup = InvoiceTaskService(context.engine, local_source)
    old = followup.browse(TaskListQuery(), OWNER).groups[0].tasks[0]
    with local_source.engine.begin() as connection:
        lines = load_tables(connection)["purchase_order_lines"]
        connection.execute(lines.update().where(lines.c.id == 1).values(quantity="101"))
    assert followup.detail(old.id, OWNER).sourceStatus == "changed"
    with pytest.raises(ApiError):
        service.approve(ApproveRequest(snapshotId=group.snapshotId), OWNER)
    new_group = service.browse(DeclarationListQuery(keyword="CD001"), OWNER).groups[0]
    assert service.approve(ApproveRequest(snapshotId=new_group.snapshotId), OWNER).invoiceTaskCount == 1
    supplier = followup.browse(TaskListQuery(), OWNER)
    declaration = followup.browse(TaskListQuery(groupBy="declaration"), OWNER)
    assert supplier.groups[0].tasks[0].id == declaration.groups[0].tasks[0].id != old.id
    assert followup.detail(old.id, OWNER).sourceStatus == "superseded"
    assert followup.browse(TaskListQuery(status="all"), OWNER).counts.tasks == 2
    assert followup.browse(TaskListQuery(status="superseded"), OWNER).counts.awaitingInvoice == 0
    assert followup.detail(old.id, OWNER).lines[0].quantity == "100.0000"


def test_scope_groups_on_id_company_currency_and_isolates_missing_identity():
    order = {
        "id": 1,
        "order_no": "SUB1",
        "supplier_identifier": "V1",
        "supplier_name": "同名供应商",
        "company_identifier": "C1",
        "company_name": "购方1",
        "currency_code": "CNY",
    }
    orders = [
        order,
        {**order, "id": 2},
        {**order, "id": 3, "company_identifier": "C2"},
        {**order, "id": 4, "currency_code": "USD"},
        {**order, "id": 5, "supplier_identifier": "V2"},
    ]
    payload = {"source": "database", "content": {"purchases": orders, "purchaseLines": []}}
    groups = split_scope(payload, "prod", "CD1")
    assert len(groups) == 4 and len(groups[0]["payload"]["orders"]) == 2
    assert groups[0]["supplier_key"] == groups[1]["supplier_key"] == groups[2]["supplier_key"]
    assert groups[3]["supplier_key"] != groups[0]["supplier_key"]
    assert groups[0]["supplier_key"] != split_scope(payload, "sb", "CD1")[0]["supplier_key"]
    unknown = copy.deepcopy(payload)
    for item in unknown["content"]["purchases"]:
        item.pop("supplier_identifier")
    assert len(split_scope(unknown, "prod", "CD1")) == 5


def test_task_api_owner_filter_pagination_and_validation(context, local_source):
    approve(context, local_source)
    app = create_app(context.settings, context.ns, context.engine, local_source.engine)
    with TestClient(app) as client:
        login(client, context)
        csrf = {"Origin": context.settings.origin}
        url = "/api/reconciliation/invoice-tasks"
        response = client.post(f"{url}/query", json={}, headers=csrf)
        assert response.status_code == 200
        task = response.json()["groups"][0]["tasks"][0]
        detail = client.get(f"{url}/{task['id']}")
        assert detail.status_code == 200 and detail.json()["sourceStatus"] == "current"
        assert client.post(f"{url}/query", json={"groupBy": "invalid"}, headers=csrf).status_code == 400
        assert client.post(f"{url}/query", json={"pageSize": 999}, headers=csrf).status_code == 400
        assert client.post(f"{url}/query", json={"keyword": "%"}, headers=csrf).json()["total"] == 0
        assert client.post(f"{url}/query", json={"account": "sb"}, headers=csrf).json()["total"] == 0
    followup = InvoiceTaskService(context.engine, local_source)
    assert followup.browse(TaskListQuery(), "user:other").counts.tasks == 0
    with pytest.raises(ApiError) as error:
        followup.detail(task["id"], "user:other")
    assert error.value.status == 404


def test_legacy_approval_also_generates_pending_task(review_context):
    from backend.tests.test_reconciliation import approve as legacy_approve
    from backend.tests.test_reconciliation import query

    group = query(review_context).groups[0]
    assert legacy_approve(review_context, group).invoiceTaskCount == 1
    assert legacy_approve(review_context, group).invoiceTaskCount == 1
    task = InvoiceTaskService(review_context.engine, None).browse(TaskListQuery(), OWNER).groups[0].tasks[0]
    assert task.status == "documents_pending" and task.expectedAmount is None


def seed_grouped_sources(local_source):
    """仅供隔离测试库：两张报关单、两家供应商，跨购方及币种的四个任务。"""
    with local_source.engine.begin() as connection:
        tables = load_tables(connection)
        heads, orders, lines = (
            tables[name] for name in ("customs_declarations", "purchase_orders", "purchase_order_lines")
        )
        connection.execute(
            orders.update()
            .where(orders.c.id == 1)
            .values(
                supplier_identifier="V1",
                supplier_name="测试供应商甲（隔离数据）",
                company_identifier="C1",
                company_name="测试采购公司一",
            )
        )
        first = dict(connection.execute(select(orders).where(orders.c.id == 1)).mappings().one())
        line = dict(connection.execute(select(lines).where(lines.c.id == 1)).mappings().one())
        head = dict(connection.execute(select(heads).where(heads.c.id == 1)).mappings().one())
        connection.execute(
            heads.insert().values(
                **{
                    **head,
                    "id": 6,
                    "ns_internal_id": "test-cd-6",
                    "record_no": "CD006-TEST",
                    "declaration_no": "测试报关单006",
                }
            )
        )
        details = tables["customs_declaration_lines"]
        detail = dict(connection.execute(select(details).where(details.c.id == 1)).mappings().one())
        connection.execute(details.insert().values(**{**detail, "id": 6, "customs_declaration_id": 6}))
        for identity, declaration, supplier, company, currency in [
            (9, 1, "V1", "C1", "CNY"),
            (10, 1, "V2", "C1", "CNY"),
            (11, 6, "V1", "C2", "CNY"),
            (12, 6, "V2", "C1", "USD"),
        ]:
            connection.execute(
                orders.insert().values(
                    **{
                        **first,
                        "id": identity,
                        "order_no": f"SUB-TEST-{identity}",
                        "customs_declaration_id": declaration,
                        "supplier_identifier": supplier,
                        "supplier_name": "测试供应商甲（隔离数据）"
                        if supplier == "V1"
                        else "测试供应商乙（隔离数据）",
                        "company_identifier": company,
                        "company_name": "测试采购公司一" if company == "C1" else "测试采购公司二",
                        "currency_code": currency,
                    }
                )
            )
            connection.execute(
                lines.insert().values(
                    **{
                        **line,
                        "id": identity,
                        "purchase_order_id": identity,
                        "quantity": "10",
                        "amount": "128.00",
                    }
                )
            )


def test_database_group_pagination_keeps_whole_groups_and_same_task_population(context, local_source):
    seed_grouped_sources(local_source)
    service = ReconciliationService(context.settings, None, context.engine, local_source)
    for number in ("CD001", "CD006-TEST"):
        group = service.browse(DeclarationListQuery(keyword=number), OWNER).groups[0]
        assert service.approve(ApproveRequest(snapshotId=group.snapshotId), OWNER).invoiceTaskCount == 2
    followup = InvoiceTaskService(context.engine, local_source)
    populations = []
    for mode in ("supplier", "declaration"):
        first = followup.browse(TaskListQuery(groupBy=mode, pageSize=1), OWNER)
        second = followup.browse(TaskListQuery(groupBy=mode, pageSize=1, page=2), OWNER)
        assert first.total == first.pages == 2 and first.counts.tasks == second.counts.tasks == 4
        assert first.groups[0].counts.tasks == second.groups[0].counts.tasks == 2
        populations.append(
            {task.id for result in (first, second) for group in result.groups for task in group.tasks}
        )
    assert populations[0] == populations[1] and len(populations[0]) == 4
    selected = followup.browse(TaskListQuery(keyword="供应商甲"), OWNER)
    assert selected.counts.tasks == 2 and selected.total == 1


def test_group_reads_keep_one_snapshot_during_concurrent_reapproval(context, local_source):
    service, _, _ = approve(context, local_source)
    followup = InvoiceTaskService(context.engine, local_source)
    old = followup.browse(TaskListQuery(), OWNER).groups[0].tasks[0]
    with local_source.engine.begin() as connection:
        orders = load_tables(connection)["purchase_orders"]
        connection.execute(orders.update().where(orders.c.id == 1).values(supplier_identifier="new-vendor"))
    preview = service.browse(DeclarationListQuery(keyword="CD001"), OWNER).groups[0]
    written = False

    def reapprove_between_queries(connection, cursor, statement, parameters, execution_context, many):
        nonlocal written
        if not written and "GROUP BY" in statement and "LIMIT" in statement:
            written = True
            service.approve(ApproveRequest(snapshotId=preview.snapshotId), OWNER)

    event.listen(context.engine, "after_cursor_execute", reapprove_between_queries)
    try:
        during = followup.browse(TaskListQuery(), OWNER)
    finally:
        event.remove(context.engine, "after_cursor_execute", reapprove_between_queries)
    assert written and during.counts.tasks == 1
    assert during.groups[0].tasks[0].id == old.id
    after = followup.browse(TaskListQuery(), OWNER)
    assert after.groups[0].tasks[0].id != old.id

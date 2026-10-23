"""业务状态（2026-10-23）：任务与报关单归类、开票跟进按状态与报关单创建日期筛选、
工作台五个分区与供应商、日期筛选、比对队列按供应商与开票日期筛选。SQLite 隔离库，合成 NS 数据。
"""

from datetime import date

import pytest
from backend.modules.matching.dto.matching_dto import QueueQuery
from backend.modules.matching.dto.workbench_dto import WorkbenchQuery
from backend.modules.matching.service.workbench_service import WorkbenchService
from backend.modules.source.public import SourceDirectory
from backend.modules.task.dto.supplier_group_dto import SupplierNotifySave
from backend.modules.task.dto.task_dto import TaskListQuery
from backend.modules.task.policy.stage_policy import declaration_stage, task_stage
from backend.modules.task.service.supplier_profile_service import SupplierProfileService
from backend.tests.invoice_files import invoice
from backend.tests.test_matching import INK, import_invoices
from backend.tests.test_matching import world as world  # 共用夹具
from backend.tests.test_source_storage import bundle, customs, purchase, rows, save
from backend.tests.test_source_storage import engine as engine  # 共用夹具
from backend.tests.test_source_storage import ns as ns  # 共用夹具
from backend.tests.test_task import USER, approve
from backend.tests.test_task import app_services as app_services  # 共用夹具


def other(order_id, customs_id, vendor=("78", "第二供应商"), created=None):
    order = purchase(order_id, customs_id)
    order[1]["custrecord_swc_subpo_vendor"] = {"id": vendor[0], "refName": vendor[1]}
    head = customs(customs_id)
    if created:
        head[1]["created"] = created
    return order, head


def supplier(engine, name):
    return str(rows(engine, "SELECT id FROM source_suppliers WHERE name = :n", n=name)[0]["id"])


@pytest.fixture
def seeded(ns, engine, app_services):
    """CD870 已审核（待通知开票）；CD890 待审核；CD891 已审核但供应商关闭通知（无需开票）。"""
    save(ns, engine, bundle([purchase()], [customs("870")]))
    order, head = other("210", "890", created="2026-10-05T02:00:00Z")
    save(ns, engine, bundle([order], [head]))
    order, head = other("220", "891", vendor=("79", "第三供应商"))
    save(ns, engine, bundle([order], [head]))
    SupplierProfileService(engine, SourceDirectory(engine)).set_notify(
        SupplierNotifySave(supplierId=supplier(engine, "第三供应商"), enabled=False, revision=0), USER
    )
    approve(app_services, "CD870")
    approve(app_services, "CD891")
    return engine


def test_stage_mapping_takes_the_slowest_current_task():
    assert task_stage("documents_pending") == task_stage("notify_pending") == "notify"
    assert task_stage("awaiting_invoice") == task_stage("partially_received") == "invoicing"
    assert task_stage("documents_incomplete") == "documents" and task_stage("completed") == "completed"
    assert task_stage("superseded") is None
    assert declaration_stage(["completed", "partially_received"]) == "invoicing"
    assert declaration_stage(["completed", "documents_incomplete"]) == "documents"
    assert declaration_stage(["superseded"]) == declaration_stage([]) == "none"


def test_task_list_filters_by_declaration_stage_and_created_date(engine, app_services, seeded):
    tasks = app_services["tasks"]
    notify = tasks.browse(TaskListQuery(stage="notify"))
    assert [t.recordNumber for g in notify.groups for t in g.tasks] == ["CD870"]
    assert notify.groups[0].tasks[0].stageLabel == "待通知开票"
    assert tasks.browse(TaskListQuery(stage="invoicing")).total == 0
    with engine.begin() as connection:
        connection.exec_driver_sql("UPDATE task_tasks SET status = 'partially_received'")
    assert tasks.browse(TaskListQuery(stage="invoicing")).total == 1
    # CD870 创建时间为 UTC 2026-09-01 16:30，即中国日期 2026-09-02
    hit = TaskListQuery(createdFrom=date(2026, 9, 2), createdTo=date(2026, 9, 2))
    miss = TaskListQuery(createdFrom=date(2026, 9, 1), createdTo=date(2026, 9, 1))
    assert tasks.browse(hit).total == 1 and tasks.browse(miss).total == 0
    with pytest.raises(ValueError):
        TaskListQuery(createdFrom=date(2026, 9, 2))
    with pytest.raises(ValueError):
        TaskListQuery(stage="pending_review")


def read(engine, **values):
    return WorkbenchService(engine).read(WorkbenchQuery(**values))


def test_workbench_partitions_count_declarations_and_skip_no_task(engine, seeded):
    result = read(engine)
    assert {stage.key: stage.count for stage in result.stages} == {
        "pending_review": 1,
        "notify": 1,
        "invoicing": 0,
        "documents": 0,
        "completed": 0,
    }
    assert [stage.label for stage in result.stages] == [
        "待审批",
        "待通知开票",
        "待核票",
        "资料已回",
        "开票完成",
    ]
    assert result.noTaskCount == 1  # CD891：供应商关闭通知，无需开票，不进分区与待办
    assert all("CD891" not in item.title for item in result.items)
    labels = {item.title: item.stageLabel for item in result.items}
    assert labels == {"CD870": "待通知开票", "CD890": "待审批"}
    names = {option.name for option in result.supplierOptions}
    assert {"第二供应商", "第三供应商"} <= names


def test_workbench_supplier_and_created_date_filters(engine, seeded):
    second = read(engine, supplierId=supplier(engine, "第二供应商"))
    assert {stage.key: stage.count for stage in second.stages}["pending_review"] == 1
    assert sum(stage.count for stage in second.stages) == 1 and [i.title for i in second.items] == ["CD890"]
    october = read(engine, createdFrom=date(2026, 10, 5), createdTo=date(2026, 10, 5))
    assert sum(stage.count for stage in october.stages) == 1 and [i.title for i in october.items] == ["CD890"]
    exported = WorkbenchService(engine).read(WorkbenchQuery(), export=True)
    assert "业务状态" in exported["content"] and "待通知开票" in exported["content"]
    with pytest.raises(ValueError):
        WorkbenchQuery(createdFrom=date(2026, 10, 5))


def test_queue_filters_by_supplier_and_invoice_date(engine, world, seeded):
    import_invoices(world, [invoice("26000000000000004401", [INK], remark="SUB-200")])
    queries = world["queries"]
    everything = queries.queue(QueueQuery())
    assert everything.total >= 1 and everything.suppliers
    ink_supplier = supplier(engine, "上海 供应商（有限）公司")
    assert queries.queue(QueueQuery(supplierId=ink_supplier)).total == everything.total
    assert queries.queue(QueueQuery(supplierId=supplier(engine, "第二供应商"))).total == 0
    issued = rows(engine, "SELECT invoice_date FROM invoice_headers")[0]["invoice_date"]
    day = date.fromisoformat(str(issued)[:10])
    assert queries.queue(QueueQuery(invoiceFrom=day, invoiceTo=day)).total == everything.total
    empty = queries.queue(QueueQuery(invoiceFrom=date(2000, 1, 1), invoiceTo=date(2000, 1, 1)))
    assert empty.total == 0 and empty.counts["all"] == 0

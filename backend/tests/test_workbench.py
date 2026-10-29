"""工作台：真实业务链路、全量筛选导出、币种日期口径和只读认证。"""

from datetime import datetime
from decimal import Decimal

from backend.app import create_app
from backend.core.config import load_settings
from backend.modules.matching.dto.workbench_dto import WorkbenchQuery
from backend.modules.matching.policy.workbench_flow import funnel, node_distribution
from backend.modules.matching.policy.workbench_kpis import kpis
from backend.modules.matching.policy.workbench_reports import monthly_receipts, supplier_ranking
from backend.modules.matching.service.workbench_service import WorkbenchService
from backend.tests.documents_ready import complete_documents
from backend.tests.invoice_files import invoice
from backend.tests.matching_helpers import confirm_groups
from backend.tests.test_matching import FLUID, INK, import_invoices, invoice_id, proposals
from backend.tests.test_matching import engine as engine
from backend.tests.test_matching import ns as ns
from backend.tests.test_matching import reviewed as reviewed
from backend.tests.test_matching import world as world
from backend.tests.test_source_storage import ACCOUNT, bundle, customs, purchase, save
from backend.tests.test_task import USER, approve
from fastapi.testclient import TestClient
from sqlalchemy import text


def read(engine, **values):
    return WorkbenchService(engine).read(WorkbenchQuery(**values))


def test_empty_auth_validation_and_export(engine, env):
    app = create_app(load_settings(env), engine=engine)
    with TestClient(app) as client:
        auth = {"Authorization": "Bearer " + env["SERVICE_API_KEY"]}
        for suffix in ("query", "export"):
            path = "/api/matching/workbench/" + suffix
            assert client.post(path, json={}).status_code == 401
            assert client.post(path, json={"pageSize": 0}, headers=auth).status_code == 400
            assert client.post(path, json={"kind": "fake"}, headers=auth).status_code == 400
            result = client.post(path, json={}, headers=auth)
            assert result.status_code == 200, result.text
        result = read(engine)
        assert result.counts.all == 0 and result.items == []
        assert result.funnel.completionRate is None and result.nodes.total == 0
        assert [k.key for k in result.kpis] == ["expected", "received", "outstanding", "review", "notify"]


def test_review_to_task_to_receipt_and_version_review(engine, ns, world):
    save(ns, engine, bundle([purchase()], [customs("870")]))
    save(ns, engine, bundle([], [customs("880")]))  # 未出库：无子采购单，拉取时跳过
    initial = read(engine)
    assert initial.counts.review == 1
    assert [row.title for row in initial.items] == ["CD870"]
    assert initial.items[0].statusLabel == "待财务核对"
    assert all(row.amount is None for row in initial.items)
    approve(world, "CD870")
    complete_documents(engine)  # 完结需资料齐全；本测试关注收票与工作台计数
    result = read(engine)
    assert (result.counts.review, result.counts.task) == (0, 1)
    assert Decimal(next(row.amount for row in result.items if row.kind == "task")) == Decimal("120.5")
    number = "26000000000000009901"
    import_invoices(world, [invoice(number, [INK, FLUID], remark="SUB-200")])
    result = read(engine)
    assert result.counts.matching == 1 and result.counts.reverify == 0
    assert proposals(world, invoice_id(engine, number))
    confirm_groups(world, invoice_id(engine, number), USER)
    result = read(engine)
    assert result.counts.matching == result.counts.task == 0
    received = next(k for k in result.kpis if k.key == "received")
    assert Decimal(received.value) == Decimal("120.5") and received.hint == "已收齐 1 / 1 个任务"
    # 漏斗与按月应开/已收：已完结的报关单走完全部环节；本月人民币应开与已收各 120.5
    steps = result.funnel.steps
    assert [(step.key, step.count) for step in steps][-1] == ("completed", 1)
    assert all(step.count == 1 for step in steps) and steps[1].rate == "100.0"
    assert result.funnel.completionRate == "100.0" and result.nodes.total == 0
    current = result.monthly[-1]
    assert (Decimal(current.expected), Decimal(current.received), current.percent) == (
        Decimal("120.5"),
        Decimal("120.5"),
        "100.0",
    )
    assert result.queue.all == 0
    import_invoices(world, [invoice(number, [INK, FLUID], remark="SUB-200 换版")])
    result = read(engine)
    assert result.counts.reverify == result.counts.matching == 1
    assert result.counts.task == 1
    assert next(k for k in result.kpis if k.key == "received").hint == "已收齐 0 / 1 个任务"


def test_filters_pagination_and_full_export(engine, ns, world, reviewed):
    save(ns, engine, bundle([purchase("210", "890")], [customs("890")]))
    save(ns, engine, bundle([], [customs("880")]))
    service = WorkbenchService(engine)
    first = read(engine, pageSize=1)
    second = read(engine, pageSize=1, page=2)
    assert first.total == 2 and first.pages == 2 and first.items[0].key != second.items[0].key
    assert read(engine, pageSize=1, page=100).page == 2
    assert read(engine, account="missing").total == 0
    assert read(engine, account=ACCOUNT).total == 2
    filtered = read(engine, keyword="SUB-200", kind="task")
    assert filtered.total == 1 and filtered.counts.all == 2 and filtered.filteredCounts.all == 1
    assert read(engine, keyword="%_").total == 0
    exported = service.read(WorkbenchQuery(pageSize=1, page=2), export=True)
    assert exported["count"] == 2 and "CD870" in exported["content"] and "CD890" in exported["content"]
    assert "CD880" not in exported["content"]
    assert service.read(WorkbenchQuery(keyword="SUB-200"), export=True)["count"] == 1


def test_monthly_receipts_by_creation_month_cny_only():
    today = datetime(2026, 10, 19).date()
    base = {"created_at": datetime(2026, 10, 1, 2), "currency": "CNY", "received": Decimal("40")}
    rows = [
        {**base, "expected": Decimal("100")},
        {**base, "expected": None},  # 应开缺失：不计入金额，另计张数
        {**base, "currency": "USD", "expected": Decimal("999")},  # 非人民币不混入
        {**base, "created_at": datetime(2026, 9, 30, 15, 59), "expected": Decimal("50")},  # 北京时间 9 月
    ]
    months = monthly_receipts(rows, today)
    assert [item["month"] for item in months][0] == "2026-05" and len(months) == 6
    october, september = months[-1], months[-2]
    assert (october["expected"], october["received"], october["percent"], october["unknownTasks"]) == (
        "100",
        "40",
        "40.0",
        1,
    )
    assert september["expected"] == "50" and months[0]["percent"] is None


def test_ranking_does_not_mix_currencies_or_partial_unknown_totals():
    base = {
        "status": "documents_pending",
        "ns_account": "A",
        "supplier_id": 1,
        "supplier": "供应商",
        "currency": "CNY",
        "outstanding": Decimal("0.1"),
    }
    base["waiting_days"] = 3
    result, unknown = supplier_ranking(
        [
            base,
            {**base, "outstanding": Decimal("0.2")},
            {**base, "currency": "USD", "outstanding": Decimal("10")},
            {**base, "supplier_id": 2, "outstanding": None},
            {**base, "supplier_id": 2, "outstanding": Decimal("100")},
            {**base, "status": "completed", "outstanding": Decimal("1000")},
        ]
    )
    assert unknown == 1
    assert [(row["currency"], row["amount"]) for row in result] == [("CNY", "0.3"), ("USD", "10")]
    assert result[0]["longestDays"] == 3 and not result[0]["overdue"]


def test_source_changes_return_to_review(engine, ns, world, reviewed):
    assert read(engine).counts.review == 0
    save(ns, engine, bundle([purchase(amounts=("200", "20"))], [customs("870")]))
    assert read(engine).counts.review == 1


def test_export_treats_external_names_as_text(engine, ns):
    from backend.modules.matching.service.workbench_service import export_csv

    save(ns, engine, bundle([purchase()], [customs("870")]))
    item = read(engine).items[0].model_copy(update={"party": ' =HYPERLINK("https://example.invalid")'})
    content = export_csv([item])["content"]
    assert "' =HYPERLINK" in content


def test_funnel_counts_positions_and_stuck_breakdown():
    from collections import Counter

    positions = Counter(
        pending_review=16, documents=6, notification=11, invoices=27, comparison=5, completion=8, done=54
    )
    result = funnel(positions)
    steps = result["steps"]
    assert [step["count"] for step in steps] == [127, 111, 105, 94, 67, 54]
    assert steps[0]["rate"] is None and steps[1]["rate"] == "87.4"
    assert [(s["key"], s["count"]) for s in steps[1]["stuck"]] == [("pending_review", 16)]
    assert [(s["label"], s["count"]) for s in steps[-1]["stuck"]] == [("部分收票", 5), ("待补资料", 8)]
    assert result["completionRate"] == "42.5"
    empty = funnel(Counter())
    assert empty["completionRate"] is None and all(step["rate"] is None for step in empty["steps"])


def test_node_distribution_excludes_completed_tasks():
    tasks = [{"node": "invoices"}] * 3 + [{"node": "documents"}, {"node": "done"}]
    result = node_distribution(tasks)
    assert result["total"] == 4
    shares = {row["key"]: (row["count"], row["percent"]) for row in result["nodes"]}
    assert shares["invoices"] == (3, "75.0") and shares["completion"] == (0, "0.0")
    assert "done" not in shares


def test_kpis_month_change_outstanding_and_counts():
    today = datetime(2026, 10, 19).date()
    monthly = [
        {"month": m, "expected": e, "received": r, "percent": p}
        for m, e, r, p in (
            ("2026-05", "0", "0", None),
            ("2026-06", "0", "0", None),
            ("2026-07", "0", "0", None),
            ("2026-08", "0", "0", None),
            ("2026-09", "200", "100", "50.0"),
            ("2026-10", "250", "50", "20.0"),
        )
    ]
    base = {
        "created_at": datetime(2026, 10, 2),
        "currency": "CNY",
        "status": "awaiting_invoice",
        "node": "invoices",
        "ns_account": "A",
        "supplier_id": 1,
        "outstanding": Decimal("30"),
        "waiting_days": 17,
    }
    tasks = [
        base,
        {**base, "supplier_id": 2, "outstanding": None, "node": "notification", "waiting_days": 2},
        {**base, "node": "documents", "status": "documents_pending"},
        {**base, "status": "completed", "node": "done", "outstanding": Decimal("0")},
        {**base, "currency": "USD", "outstanding": Decimal("999")},
    ]
    reviews = [{"changed": True, "ns_created_at": datetime(2026, 9, 3)}, {"changed": False}]
    found = {k["key"]: k for k in kpis(monthly=monthly, tasks=tasks, reviews=reviews, today=today)}
    assert found["expected"]["delta"] == "较上月 +25.0%" and found["expected"]["direction"] == "up"
    assert found["expected"]["hint"] == "本月生成 4 个开票任务"
    assert found["received"]["delta"] == "收票率 20.0%" and found["received"]["hint"] == "已收齐 1 / 4 个任务"
    outstanding = found["outstanding"]
    assert outstanding["value"] == "60" and outstanding["tone"] == "warning"
    assert outstanding["hint"] == "涉及 1 家供应商，另有 1 个任务金额待核实"
    assert outstanding["series"][-1] == "60"
    assert found["review"]["value"] == "2" and found["review"]["delta"] == "1 张来源变化需重审"
    assert found["review"]["series"][-2:] == ["1", "0"]
    assert (found["notify"]["value"], found["notify"]["delta"]) == ("1", "另有 1 个待存合同")
    assert found["notify"]["role"] == "purchase"


def test_anomaly_counts_only_proposals_and_skip_missing_data():
    from backend.modules.matching.service.workbench_service import anomaly_counts

    def check(key, result, value="x"):
        return {"key": key, "label": key, "result": result, "invoiceValue": value}

    rows = [
        {"status": "proposed", "checks": {"items": [check("unit", "mismatch"), check("price", "mismatch")]}},
        {
            "status": "proposed",
            "checks": {"items": [check("unit", "partial"), check("buyer", "missing", None)]},
        },
        {"status": "proposed", "checks": {"items": [check("price", "missing")]}},
        {"status": "proposed", "checks": None},
        {"status": "confirmed", "checks": {"items": [check("amount", "mismatch")]}},
    ]
    assert anomaly_counts(rows) == [
        {"label": "单位", "count": 2, "percent": "100.0"},
        {"label": "价格", "count": 1, "percent": "50.0"},
    ]


def test_unbound_supplier_reminder_counts_notify_tasks_without_group(engine, ns, world):
    save(ns, engine, bundle([purchase()], [customs("870")]))
    approve(world, "CD870")
    complete_documents(engine)  # 资料齐全后任务停在“待通知供应商”节点
    result = read(engine)
    assert next(k for k in result.kpis if k.key == "notify").value == "1"
    assert (result.unboundNotify.suppliers, result.unboundNotify.tasks) == (1, 1)
    assert result.unboundNotify.names == ["上海 供应商（有限）公司"]
    # 与供应商档案“未绑定”同一口径：有绑定记录（含停用）即不算未绑定
    with engine.begin() as connection:
        supplier_id = connection.execute(text("SELECT supplier_id FROM task_tasks")).scalar_one()
        connection.execute(
            text(
                "INSERT INTO task_supplier_groups (supplier_id, group_name, chat_id, owner_name, owner_userid,"
                " enabled, updated_by) VALUES (:s, '开票群', 'wr-chat', '群主', 'owner', 0, 'user:admin')"
            ),
            {"s": supplier_id},
        )
    result = read(engine)
    assert (result.unboundNotify.suppliers, result.unboundNotify.tasks, result.unboundNotify.names) == (
        0,
        0,
        [],
    )
    assert read(engine, account="other").unboundNotify.suppliers == 0

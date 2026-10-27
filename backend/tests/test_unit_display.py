"""单位字典仅改变展示，来源、数量、金额、冻结依据和摘要保持原值。"""

from copy import deepcopy
from types import SimpleNamespace

import pytest
from backend.app import create_events
from backend.core.config import Settings
from backend.modules.matching.mapper.allocation_mapper import check_views, purchase_side
from backend.modules.matching.service.matching_query_service import MatchingQueryService
from backend.modules.review.dto.review_dto import ApproveRequest, DeclarationListQuery
from backend.modules.source.dto.pl_comparison import PlScriptQuery
from backend.modules.source.public import DeclarationService, SourceDirectory, unit_label, unit_names
from backend.modules.source.service.pl_comparison_service import PlScriptService
from backend.modules.task.service.task_service import TaskService
from backend.tests.review_helpers import MaterializedReviewService as ReviewService
from backend.tests.test_pl_script import result as script_result
from backend.tests.test_source_storage import bundle, customs, purchase, rows, save
from backend.tests.test_source_storage import engine as engine
from backend.tests.test_source_storage import ns as ns
from sqlalchemy import Column, Integer, MetaData, String, Table, insert, update
from sqlalchemy.exc import OperationalError


@pytest.fixture
def dictionary(engine):
    table = Table(
        "unit_dictionary",
        MetaData(),
        Column("unit_id", Integer, primary_key=True),
        Column("unit_name", String(191)),
        Column("enabled", Integer),
    )
    table.create(engine)
    with engine.begin() as connection:
        connection.execute(
            insert(table),
            [
                {"unit_id": 1, "unit_name": "台", "enabled": 1},
                {"unit_id": 23, "unit_name": "幅", "enabled": 1},
                {"unit_id": 7, "unit_name": "个", "enabled": 0},
                {"unit_id": 999, "unit_name": "", "enabled": 1},
            ],
        )
    return table


@pytest.mark.parametrize(
    "value,expected",
    [
        ("1", "台"),
        (" 023 ", "幅"),
        (23, "幅"),
        ("7", "7"),
        ("999", "999"),
        ("未知", "未知"),
        ("台", "台"),
        ("23/箱", "23/箱"),
        ("1.0", "1.0"),
        (None, ""),
    ],
)
def test_dictionary_labels(engine, dictionary, value, expected):
    with engine.connect() as connection:
        assert unit_label(value, unit_names(connection)) == expected


def test_absent_dictionary_keeps_original(engine):
    with engine.connect() as connection:
        assert unit_names(connection) == {}
        assert unit_label("23", unit_names(connection)) == "23"


def test_database_errors_are_not_hidden(engine, dictionary, monkeypatch):
    with engine.connect() as connection:

        def fail(*args, **kwargs):
            raise OperationalError("read", {}, Exception("offline"))

        monkeypatch.setattr(connection, "execute", fail)
        with pytest.raises(OperationalError):
            unit_names(connection)


def test_review_task_matching_display_preserves_evidence(engine, ns, dictionary):
    order, declaration = purchase(), customs()
    mapping = ns.settings.pl_lookup
    for _, line in order[2]:
        line[mapping["purchase_line"]["storage_fields"]["unit_name"]] = "1"
        line[mapping["purchase_line"]["storage_fields"]["declaration_unit"]] = "23"
    for _, line in declaration[2]:
        line[mapping["customs_line"]["storage_fields"]["declared_unit"]] = "23"
    save(ns, engine, bundle([order], [declaration]))
    events = create_events()
    review = ReviewService(engine, DeclarationService(engine), events)
    group = review.browse(DeclarationListQuery()).groups[0]
    before = rows(engine, "SELECT * FROM source_purchase_order_lines")
    assert all(line.unit == "幅" for line in group.customsLines)
    purchase_views = group.unlinkedLines + [p for c in group.customsLines for p in c.purchaseLines]
    assert all(line.unit == "台" and "幅" in line.note for line in purchase_views)
    digest = group.contentSha256
    review.approve(int(group.id), ApproveRequest(contentSha256=digest), "user:admin")
    frozen = rows(engine, "SELECT unit,quantity,amount FROM review_lines")
    assert all(line["unit"] == "1" for line in frozen)
    assert all(line["unit"] == "1" for line in rows(engine, "SELECT unit FROM task_lines"))
    task_id = rows(engine, "SELECT id FROM task_tasks")[0]["id"]
    detail = TaskService(engine, SourceDirectory(engine)).detail(task_id)
    assert all(line.unit == "台" for line in detail.lines)
    with engine.connect() as connection:
        context, tasks = MatchingQueryService._context(
            connection, [{"purchase_line_id": r["id"]} for r in before]
        )
        for key, line in context.items():
            assert line["unit"] == "1"
            assert purchase_side(key, line, tasks.get(key)).unit == "台"
    # 字典更新即时影响展示，不能使已有审核失效或改变金额、数量与冻结依据。
    with engine.begin() as connection:
        connection.execute(update(dictionary).where(dictionary.c.unit_id == 1).values(unit_name="设备台"))
    after = review.browse(DeclarationListQuery()).groups[0]
    assert after.contentSha256 == digest
    assert after.review.status == "approved"
    assert rows(engine, "SELECT * FROM source_purchase_order_lines") == before
    assert rows(engine, "SELECT unit,quantity,amount FROM review_lines") == frozen
    assert all(
        line.unit == "设备台" for line in TaskService(engine, SourceDirectory(engine)).detail(task_id).lines
    )


@pytest.mark.parametrize("version", [1, 2, 3])
def test_live_comparison_only_changes_unit_column(engine, dictionary, version):
    payload = script_result(2 if version == 3 else version)
    payload["contractVersion"] = version
    for row in payload["groups"][0]["rows"]:
        row["cells"][12] = "23"
    original = deepcopy(payload)
    ns = SimpleNamespace(settings=Settings(account="test-sb1"), pl_script_query=lambda _: payload)
    result = PlScriptService(ns, engine).query(PlScriptQuery(pl="PL001"))
    for row, raw in zip(result.groups[0].rows, original["groups"][0]["rows"]):
        assert row.cells[12] == "幅"
        assert row.cells[:12] + row.cells[13:] == raw["cells"][:12] + raw["cells"][13:]
    assert payload == original


def test_matching_unit_label_preserves_check_result_and_original():
    check = {
        "key": "unit",
        "label": "单位",
        "invoiceValue": "台",
        "purchaseValue": "1",
        "result": "mismatch",
        "difference": None,
        "note": "需核实。",
    }
    original = deepcopy(check)
    view = check_views([check], "台")[0]
    assert view.purchaseValue == "台"
    assert view.invoiceValue == "台"
    assert view.result == "mismatch"
    assert "原值：1" in view.note
    assert check == original

"""导航列表批量读取的等价性与查询数回归；全部使用隔离库和合成来源。"""

from backend.modules.review.dao import customs_receipt_dao
from backend.modules.review.service.customs_approval_service import approval_view, approval_views
from backend.modules.settlement.dao import document_group_dao
from backend.modules.settlement.service.direct_document_source import DirectDocumentSource
from backend.modules.source.public import digest, purchase_lines, snapshot, snapshots, workbench_line_labels
from backend.tests.settlement.documents_support import HK, SELLER, Documents
from backend.tests.settlement.test_direct_documents import direct_documents
from backend.tests.settlement.test_document_groups import create_body, group_docs, make_direct
from backend.tests.settlement.test_settlement_batches import create, services
from backend.tests.settlement.test_settlement_batches import seeded as seeded
from backend.tests.test_customs_approval import approve, body, current
from backend.tests.test_customs_approval import world as world
from backend.tests.test_customs_receipts import _import, row
from backend.tests.test_schema_baseline import schema_engine as schema_engine
from backend.tests.test_source_storage import bundle, customs, purchase, save
from backend.tests.test_source_storage import ns as ns
from sqlalchemy import event


def measured(engine, read):
    statements = []

    def count(*args):
        statements.append(args[2])

    event.listen(engine, "before_cursor_execute", count)
    try:
        return read(), statements
    finally:
        event.remove(engine, "before_cursor_execute", count)


def test_customs_batch_matches_single_views_and_preserves_approval_versions(world, ns):
    engine, _, receipts, _ = world
    approve(world, body(current(world)))
    save(ns, engine, bundle([purchase("201", "871")], [customs("871")]))
    _import(
        receipts, [row("REAL871", "01", "墨水", "个", 10, total=20), row("REAL999", "01", "无来源", "个", 1)]
    )
    with engine.connect() as connection:
        _, heads = customs_receipt_dao.page(connection, {}, None, 0, 100)
        lines = customs_receipt_dao.current_lines(connection, [head["id"] for head in heads])
        expected = {head["id"]: approval_view(connection, head, lines[head["id"]]) for head in heads}
        actual, statements = measured(engine, lambda: approval_views(connection, heads, lines))
        assert actual == expected
        matched = [head for head in heads if head["declaration_no"] == "REAL870"]
        _, single_statements = measured(engine, lambda: approval_views(connection, matched, lines))
        assert len(statements) <= len(single_statements) + 2
        ids = [item[1] for item in actual.values() if item[1]]
        contents = snapshots(connection, [*ids, 999999])
        assert 999999 not in contents
        assert all(contents[identity] == snapshot(connection, identity) for identity in ids)
        assert all(
            digest(content) == content["declaration"]["content_sha256"] for content in contents.values()
        )


def test_workbench_labels_preserve_full_context_names(world):
    engine = world[0]
    with engine.connect() as connection:
        _, heads = customs_receipt_dao.page(connection, {}, None, 0, 100)
        contents = snapshots(
            connection, [head["ns_declaration_id"] for head in heads if head["ns_declaration_id"]]
        )
        ids = [line["id"] for content in contents.values() for line in content["purchase_lines"]]
        assert ids
        labels = workbench_line_labels(connection, [*ids, 999999])
        context = purchase_lines(connection, ids)
        assert {
            key: {field: row[field] for field in ("order_no", "supplier_name")} for key, row in labels.items()
        } == {
            key: {field: row[field] for field in ("order_no", "supplier_name")}
            for key, row in context.items()
        }


def test_document_batch_preserves_hk_direct_scope_and_whole_state(seeded, tmp_path):
    _, batches = services(seeded)
    first = create(batches, ["REAL870"], "600")
    second = create(batches, ["REAL871"], "400.5")
    hk, direct = Documents(seeded, tmp_path), direct_documents(seeded, tmp_path)
    hk.party(HK, HK)
    direct.party("ACME LTD", "ACME LTD")
    seller = hk.party(SELLER, "EXPORT SELLER")
    for identity in (first.id, second.id):
        hk.upload(identity)
        hk.generate(identity, seller.id)
    direct.upload("REAL872")
    direct.generate("REAL872", seller.id)
    with seeded.connect() as connection:
        contexts = {identity: hk.views.load(connection, identity) for identity in (first.id, second.id)}
        contexts["REAL872"] = direct.views.load(connection, "REAL872")
        expected = {
            key: hk.reader.state(connection, context, rows) for key, (context, rows) in contexts.items()
        }
        actual, statements = measured(seeded, lambda: hk.reader.states(connection, contexts))
        assert actual == expected
        _, single = measured(seeded, lambda: hk.reader.states(connection, {first.id: contexts[first.id]}))
        assert len(statements) <= len(single) + 1
        assert len({state["bills"][0]["id"] for state in actual.values()}) == 3


def test_filtered_direct_rows_still_use_complete_document_group(seeded, ns, tmp_path):
    make_direct(seeded, ns)
    docs = group_docs(seeded, tmp_path)
    docs.groups.create(create_body(["REAL870", "REAL871"]), "finance-user")
    candidates, _ = services(seeded)
    source = DirectDocumentSource(candidates)
    with seeded.connect() as connection:
        rows = candidates.load(connection, numbers=["REAL870", "REAL872"], limit=None)
        groups = document_group_dao.by_numbers(connection, [row["declaration_no"] for row in rows])
        expected = {row["declaration_no"]: source.for_row(connection, row) for row in rows}
        actual = source.for_rows(connection, rows, groups)
        assert actual == expected
        assert [row["declaration_no"] for row in actual["REAL870"][1]] == ["REAL870", "REAL871"]
        contexts = {context["id"]: (context, members) for context, members in actual.values()}
        assert docs.reader.states(connection, contexts) == {
            key: docs.reader.state(connection, context, members)
            for key, (context, members) in contexts.items()
        }

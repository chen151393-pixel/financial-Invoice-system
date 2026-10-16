"""真实向前迁移：旧 v2 历史不可伪造或清空，旧库对象完全保留。"""

from decimal import Decimal
from uuid import uuid4

from backend.manage import upgrade_schema, verify_database
from backend.tests.test_schema_baseline import NOW, insert, purchase_line
from backend.tests.test_schema_baseline import schema_engine as schema_engine
from sqlalchemy import text

INITIAL_REVISION = "0004_source_purchase_currency"


def test_upgrade_keeps_v2_history_and_marks_unverifiable_occupancy(schema_engine):
    with schema_engine.begin() as c:
        c.execute(text("CREATE TABLE old_test_evidence (id INTEGER PRIMARY KEY)"))
        c.execute(text("INSERT INTO old_test_evidence VALUES (71)"))
        order, line = purchase_line(c)
        review = insert(
            c,
            "review_records",
            ns_account="prod",
            customs_declaration_id=1,
            revision=1,
            status="active",
            content_sha256="a" * 64,
            approved_by="user:before",
            approved_at=NOW,
        )
        review_line = insert(
            c,
            "review_lines",
            review_id=review,
            purchase_order_id=order,
            purchase_line_id=line,
            order_no="SUB-1",
            currency="CNY",
            quantity=10,
            unit="个",
            amount=100,
            line_sha256="b" * 64,
        )
        task = insert(
            c,
            "task_tasks",
            review_id=review,
            ns_account="prod",
            customs_declaration_id=1,
            group_key="c" * 64,
            status="completed",
            completed_at=NOW,
        )
        insert(
            c,
            "task_lines",
            task_id=task,
            review_line_id=review_line,
            purchase_order_id=order,
            purchase_line_id=line,
            expected_quantity=10,
            expected_amount=100,
            received_quantity=10,
            received_amount=100,
            status="received",
        )
        invoice = insert(
            c,
            "invoice_headers",
            source="lemon_excel",
            lemon_account="excel",
            invoice_key=":1",
            invoice_no="1",
            imported_at=NOW,
        )
        item = insert(
            c,
            "invoice_items",
            invoice_id=invoice,
            source_line_key="1",
            item_name="墨水",
            unit="个",
            quantity=10,
            amount_including_tax=100,
        )
        allocation = insert(
            c,
            "matching_allocations",
            invoice_id=invoice,
            invoice_item_id=item,
            purchase_line_id=line,
            quantity=10,
            amount=100,
            status="confirmed",
            request_id=str(uuid4()),
            proposed_by="user:before",
            proposed_at=NOW,
            reviewed_by="user:before",
            reviewed_at=NOW,
        )
    target = schema_engine.url.render_as_string(hide_password=False)
    upgrade_schema(target)
    upgrade_schema(target)
    verify_database(schema_engine)
    with schema_engine.connect() as c:
        assert c.execute(text("SELECT id FROM old_test_evidence")).scalar_one() == 71
        basis = c.execute(text("SELECT * FROM review_purchase_bases")).mappings().one()
        assert basis["status"] == "review_required" and Decimal(str(basis["amount"])) == 100
        assert basis["source_sha256"] == "b" * 64
        saved = (
            c.execute(text("SELECT * FROM matching_allocations WHERE id=:id"), {"id": allocation})
            .mappings()
            .one()
        )
        assert saved["status"] == "confirmed" and saved["reviewed_by"] == "user:before"
        assert saved["verification_status"] == "needs_review" and saved["purchase_basis_id"] is None
        assert saved["purchase_quantity"] is None and saved["invoice_version_id"]
        progress = c.execute(text("SELECT * FROM task_lines")).mappings().one()
        assert Decimal(str(progress["pending_amount"])) == 100 and progress["received_amount"] == 0
        assert progress["requires_review"] and progress["purchase_basis_id"] == basis["id"]
        assert c.execute(text("SELECT completed_at FROM task_tasks")).scalar_one() is not None

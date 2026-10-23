"""测试辅助：为当前任务补齐完结所需资料记录，并按资料规则重算任务状态。

2026-10-23 起任务完结要求发票收齐且资料齐全（子采购合同、报关单、销售合同、发票、回签合同）。
收票与比对类测试不关心资料下载过程，用本辅助直接写入已归档记录；资料流程本身见 test_task_documents_completion.py。
"""

from datetime import datetime, timezone

from backend.core.write_lock import transaction
from backend.modules.task.service.progress_service import refresh_tasks
from sqlalchemy import text

DOC_TYPES = ("customs_declaration", "sales_contract", "invoice")


def complete_documents(engine, actor="user:admin"):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    with transaction(engine) as connection:

        def rows(sql, **params):
            return [dict(row) for row in connection.execute(text(sql), params).mappings()]

        tasks = rows("SELECT * FROM task_tasks WHERE status <> 'superseded' ORDER BY id")
        for task in tasks:
            orders = rows(
                "SELECT DISTINCT purchase_order_id FROM task_lines WHERE task_id = :t AND status <> 'superseded'",
                t=task["id"],
            )
            for order in (row["purchase_order_id"] for row in orders):
                if not rows(
                    "SELECT id FROM task_documents WHERE task_id = :t AND purchase_order_id = :o",
                    t=task["id"],
                    o=order,
                ):
                    connection.execute(
                        text(
                            "INSERT INTO task_documents (task_id, purchase_order_id, order_no, ns_environment,"
                            " status, archived_at, created_at, updated_at)"
                            " VALUES (:t, :o, 'TEST', 'test', 'archived', :n, :n, :n)"
                        ),
                        {"t": task["id"], "o": order, "n": now},
                    )
                if not rows("SELECT id FROM task_signed_contracts WHERE purchase_order_id = :o", o=order):
                    connection.execute(
                        text(
                            "INSERT INTO task_signed_contracts (purchase_order_id, customs_declaration_id, order_no,"
                            " original_filename, filename, sha256, archive_path, uploaded_by, created_at, updated_at)"
                            " VALUES (:o, :d, 'TEST', 'test.pdf', 'test.pdf', :s, 'test', 'test', :n, :n)"
                        ),
                        {"o": order, "d": task["customs_declaration_id"], "s": "0" * 64, "n": now},
                    )
            for doc_type in DOC_TYPES:
                found = rows(
                    "SELECT id FROM task_declaration_documents WHERE customs_declaration_id = :d AND doc_type = :k",
                    d=task["customs_declaration_id"],
                    k=doc_type,
                )
                if found:
                    connection.execute(
                        text(
                            "UPDATE task_declaration_documents SET status = 'archived', files = '[]' WHERE id = :i"
                        ),
                        {"i": found[0]["id"]},
                    )
                else:
                    connection.execute(
                        text(
                            "INSERT INTO task_declaration_documents (customs_declaration_id, ns_account, doc_type,"
                            " status, files, requested_by, attempts, created_at, updated_at)"
                            " VALUES (:d, :a, :k, 'archived', '[]', 'test', 0, :n, :n)"
                        ),
                        {
                            "d": task["customs_declaration_id"],
                            "a": task["ns_account"],
                            "k": doc_type,
                            "n": now,
                        },
                    )
        refresh_tasks(connection, [task["id"] for task in tasks], actor, "测试补齐资料", now)

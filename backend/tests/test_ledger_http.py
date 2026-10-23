"""使用真实 JSON 请求覆盖复核、替换、人工分配和差额结束，防止 DTO 只接受 Python 对象。"""

from uuid import uuid4

from backend.app import create_app
from backend.tests.documents_ready import complete_documents
from backend.tests.invoice_files import invoice
from backend.tests.test_ledger_versions import active_lines, confirm_all
from backend.tests.test_matching import FLUID, INK, import_invoices, task
from backend.tests.test_matching import reviewed as reviewed
from backend.tests.test_matching import world as world
from backend.tests.test_source_storage import engine as engine
from backend.tests.test_source_storage import ns as ns
from fastapi.testclient import TestClient


def test_json_ledger_actions(context, engine, world, reviewed):
    complete_documents(engine)  # 完结需资料齐全；本测试关注收票与账本
    target, found = confirm_all(engine, world)
    import_invoices(world, [invoice("26000000000000008801", [INK, FLUID], remark="SUB-200 修订")])
    with TestClient(create_app(context.settings, context.ns, engine)) as client:
        headers = {"Origin": context.settings.origin}
        assert (
            client.post(
                "/api/session",
                headers=headers,
                json={
                    "username": "admin",
                    "password": context.settings.admin_password,
                },
            ).status_code
            == 200
        )
        for row in found:
            result = client.post(
                f"/api/matching/allocations/{row.id}/reverify",
                headers=headers,
                json={"note": "已核实仅备注修订", "conversionNumerator": "1", "conversionDenominator": "1"},
            )
            assert result.status_code == 200, result.text
        row = found[0]
        body = {
            "requestId": str(uuid4()),
            "invoiceId": str(target),
            "invoiceItemId": row.invoiceItemId,
            "purchaseLineId": row.purchaseLineId,
            "quantity": "11",
            "amount": row.amount,
            "note": "已核实原分配",
            "reason": "替换凭据",
        }
        path = f"/api/matching/allocations/{row.id}/replace"
        rejected = client.post(path, headers=headers, json=body)
        assert rejected.status_code == 409 and "超过" in rejected.json()["error"]
        body["quantity"] = row.quantity
        replaced = client.post(path, headers=headers, json=body)
        assert replaced.status_code == 200, replaced.text
        current = next(
            a
            for item in replaced.json()["items"]
            for a in item["allocations"]
            if a["status"] == "confirmed" and a["purchaseLineId"] == row.purchaseLineId
        )
        assert (
            client.post(
                f"/api/matching/allocations/{current['id']}/cancel",
                headers=headers,
                json={"reason": "测试人工分配"},
            ).status_code
            == 200
        )
        body.pop("reason")
        body["requestId"] = str(uuid4())
        manual = client.post("/api/matching/allocations", headers=headers, json=body)
        assert manual.status_code == 200, manual.text
        second = found[1]
        assert (
            client.post(
                f"/api/matching/allocations/{second.id}/cancel",
                headers=headers,
                json={"reason": "测试差异结束"},
            ).status_code
            == 200
        )
        line = next(r for r in active_lines(engine) if str(r["purchase_line_id"]) == second.purchaseLineId)
        closure = {
            "requestId": str(uuid4()),
            "purchaseBasisId": str(line["purchase_basis_id"]),
            "ledgerSha256": line["ledger_sha256"],
            "reason": "隔离测试差异已核实",
        }
        closed = client.post(
            f"/api/tasks/{task(engine)['id']}/lines/{line['id']}/close", headers=headers, json=closure
        )
        assert closed.status_code == 200, closed.text
        assert closed.json()["task"]["status"] == "completed"

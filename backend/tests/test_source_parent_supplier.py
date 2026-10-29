"""母采购供应商同步及回写就绪：隔离来源、真实服务，不访问 NS。"""

import json
from datetime import datetime, timezone

import pytest
from backend.core.errors import ApiError
from backend.modules.matching.dto.matching_dto import ConfirmBody
from backend.modules.source.service.parent_order_service import save_header
from backend.modules.writeback.dto.task_dto import TaskQuery
from backend.modules.writeback.service.task_service import TaskService
from backend.tests.invoice_files import invoice
from backend.tests.test_matching import FLUID, INK, USER, approve, import_invoices, invoice_id, proposals
from backend.tests.test_matching import world as world
from backend.tests.test_source_storage import ACCOUNT, PARENT, bundle, customs, purchase, rows, save
from backend.tests.test_source_storage import engine as engine
from backend.tests.test_source_storage import ns as ns
from sqlalchemy import text


def parent(supplier_id="77", name="上海供应商（有限）公司"):
    return {**PARENT, "currency": "1", "supplierid": supplier_id, "suppliername": name}


def test_sync_saves_parent_supplier_reference_and_raw_snapshot_idempotently(ns, engine):
    payload = parent()
    data = bundle([purchase()], [customs()], parents={"100": payload})
    save(ns, engine, data)
    save(ns, engine, data)
    stored = rows(engine, "SELECT * FROM source_parent_orders")[0]
    child = rows(engine, "SELECT * FROM source_purchase_orders")[0]
    assert stored["supplier_id"] == child["supplier_id"]
    assert len(rows(engine, "SELECT * FROM source_suppliers")) == 1
    raw = rows(engine, "SELECT payload FROM source_raw_records WHERE id=:id", id=stored["raw_record_id"])[0]
    assert json.loads(raw["payload"])["supplierid"] == "77"
    assert len(rows(engine, "SELECT * FROM source_raw_records WHERE record_type='purchaseOrder'")) == 1


def test_parent_display_label_does_not_replace_existing_supplier_name_or_status(ns, engine):
    save(ns, engine, bundle([purchase()], [customs()], parents={"100": parent()}))
    with engine.begin() as connection:
        connection.execute(text("UPDATE source_suppliers SET is_active=0"))
    before = rows(engine, "SELECT name,is_active FROM source_suppliers")[0]
    with engine.begin() as connection:
        save_header(
            connection,
            ACCOUNT,
            "100",
            parent(name="V0077 不同显示标签"),
            "CNY",
            datetime.now(timezone.utc).replace(tzinfo=None),
        )
    assert rows(engine, "SELECT name,is_active FROM source_suppliers")[0] == before


@pytest.mark.parametrize("supplier_id", ["88", None])
def test_parent_supplier_is_not_inferred_from_child(ns, engine, supplier_id):
    save(ns, engine, bundle([purchase()], [customs()], parents={"100": parent(supplier_id, "另一供应商")}))
    stored = rows(engine, "SELECT * FROM source_parent_orders")[0]
    child = rows(engine, "SELECT * FROM source_purchase_orders")[0]
    assert stored["supplier_id"] != child["supplier_id"]
    if supplier_id is None:
        assert stored["supplier_id"] is None
    else:
        supplier = rows(
            engine, "SELECT ns_internal_id FROM source_suppliers WHERE id=:id", id=stored["supplier_id"]
        )[0]
        assert supplier["ns_internal_id"] == supplier_id


def test_parent_supplier_reference_is_scoped_to_account(ns, engine):
    save(ns, engine, bundle([purchase()], [customs()], parents={"100": parent()}))
    first = rows(engine, "SELECT supplier_id FROM source_parent_orders")[0]["supplier_id"]
    with engine.begin() as connection:
        save_header(
            connection,
            "other-account",
            "100",
            parent(),
            "CNY",
            datetime.now(timezone.utc).replace(tzinfo=None),
        )
    second = rows(engine, "SELECT supplier_id FROM source_parent_orders WHERE ns_account='other-account'")[0][
        "supplier_id"
    ]
    assert first != second


@pytest.mark.parametrize("supplier_id,name", [("bad-id", "供应商"), ("88", None)])
def test_invalid_parent_supplier_rolls_back_source_save(ns, engine, supplier_id, name):
    with pytest.raises(ApiError):
        save(ns, engine, bundle([purchase()], [customs()], parents={"100": parent(supplier_id, name)}))
    assert not rows(engine, "SELECT * FROM source_parent_orders")
    assert not rows(engine, "SELECT * FROM source_purchase_orders")


def test_synced_parent_supplier_allows_missing_buyer_invoice_to_enqueue(ns, engine, world):
    save(ns, engine, bundle([purchase()], [customs()], parents={"100": parent()}))
    approve(world, "CD870")
    number = "26000000000000008888"
    import_invoices(world, [invoice(number, [INK, FLUID], remark="SUB-200")])
    target = invoice_id(engine, number)
    for proposal in proposals(world, target):
        world["allocations"].confirm(int(proposal.id), ConfirmBody(), USER)
    service = TaskService(engine, ACCOUNT)
    ready = service.invoice(target)
    assert ready["ready"], ready
    assert ready["task"]["state"] == "queued"
    service.recheck(target, USER)
    assert service.list(TaskQuery())["total"] == 1

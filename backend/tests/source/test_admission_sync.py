"""拉取时的出库准入（2026-10-23）：无真实报关单号或无关联子采购单的报关单不入库，带出的子采购一起跳过；
同时保存 NS 报关单创建时间供归档月份使用。SQLite 隔离库，合成 NS 数据。
"""

from backend.modules.source.mapper.admission_filter import skip_unshipped
from backend.modules.source.mapper.group_bundle import split_groups
from backend.modules.source.policy.ns_config import LookupConfig
from backend.modules.source.vo.partial_sync_result import PartialResult
from backend.tests.test_source_storage import bundle, config, customs, purchase, rows, save
from backend.tests.test_source_storage import engine as engine  # 共用夹具
from backend.tests.test_source_storage import ns as ns  # 共用夹具


def without_real_no(customs_id):
    customs_id, head, lines = customs(customs_id)
    head["custrecord_swc_realno"] = ""
    return customs_id, head, lines


def saved(engine, table):
    return rows(engine, f"SELECT * FROM {table} ORDER BY id")


def test_declaration_without_real_number_and_its_purchases_are_not_saved(ns, engine):
    result = save(ns, engine, bundle([purchase("210", "890")], [without_real_no("890")]))
    assert saved(engine, "source_customs_declarations") == []
    assert saved(engine, "source_purchase_orders") == []
    assert result["skipped"] == [{"id": "890", "number": "CD890", "reason": "未出库：缺少真实报关单号"}]
    assert result["message"] == "本页报关单均未出库，已跳过，未保存"
    assert "已跳过未出库报关单" in result["warnings"][0] and "CD890" in result["warnings"][0]


def test_declaration_without_purchases_is_skipped_but_shipped_one_is_saved(ns, engine):
    result = save(ns, engine, bundle([purchase()], [customs("870"), customs("880")]))
    assert [row["record_no"] for row in saved(engine, "source_customs_declarations")] == ["CD870"]
    assert [row["order_no"] for row in saved(engine, "source_purchase_orders")] == ["SUB-200"]
    assert [item["number"] for item in result["skipped"]] == ["CD880"]
    assert "没有关联的子采购单" in result["skipped"][0]["reason"]
    assert result["customs"]["created"] == 1


def test_filled_in_later_is_saved_on_next_pull(ns, engine):
    save(ns, engine, bundle([purchase("210", "890")], [without_real_no("890")]))
    save(ns, engine, bundle([purchase("210", "890")], [customs("890")]))
    head = saved(engine, "source_customs_declarations")[0]
    assert head["declaration_no"] == "REAL890"


def test_ns_created_time_is_saved_and_missing_value_stays_empty(ns, engine):
    save(ns, engine, bundle([purchase()], [customs("870")]))
    created = saved(engine, "source_customs_declarations")[0]["ns_created_at"]
    assert str(created).startswith("2026-09-01 16:30:00")  # UTC；中国时间 2026-09-02
    customs_id, head, lines = customs("870", modified="2026-09-03T10:00:00Z")
    del head["created"]
    save(ns, engine, bundle([purchase()], [(customs_id, head, lines)]))
    assert saved(engine, "source_customs_declarations")[0]["ns_created_at"] is None


def test_purchase_entry_whose_declaration_is_unshipped_is_marked_skipped_in_batch():
    lookup = LookupConfig.model_validate(config())
    data = bundle([purchase("210", "890"), purchase("200", "870")], [without_real_no("890"), customs("870")])
    skipped = skip_unshipped(data, lookup)
    assert [(item["kind"], item["id"]) for item in skipped] == [("customs", "890"), ("purchase", "210")]
    rows_in = [{"id": "210", "number": "SUB-210"}, {"id": "200", "number": "SUB-200"}]
    groups = split_groups(data, "sub-purchase-orders", rows_in, lookup)
    assert [[row["id"] for row in entry] for entry, _ in groups] == [["200"]]
    result = PartialResult({"rows": rows_in})
    result.mark_skipped(skipped)
    response = result.response()
    assert response["batch"]["counts"]["skipped"] == 1
    item = next(item for item in response["batch"]["items"] if item["id"] == "210")
    assert item["status"] == "skipped" and "CD890 未出库" in item["reason"]
    assert "未出库跳过 1 张" in response["message"]

"""真实同步保存链路配合合成 NS 数据，验证追溯缺失不阻断人工审核和开票任务。"""

from copy import deepcopy
from decimal import Decimal

import pytest
from backend.app import create_app, create_events
from backend.core.errors import ApiError
from backend.modules.review.dto.review_dto import ApproveRequest, DeclarationListQuery
from backend.modules.review.service.review_service import ReviewService
from backend.modules.source.public import DeclarationService
from backend.modules.source.service.storage_service import StorageService
from backend.tests.test_source_optional_trace import success, unavailable
from backend.tests.test_source_storage import (
    ACCOUNT,
    PARENT,
    SALES,
    customs,
    declaration,
    evidence,
    purchase,
    rows,
)
from backend.tests.test_source_storage import engine as engine  # 共用隔离库
from backend.tests.test_source_storage import ns as ns  # 共用来源映射
from fastapi.testclient import TestClient


@pytest.fixture
def source(ns):
    mapping = ns.settings.pl_lookup
    order_id, order, order_lines = purchase()
    customs_id, header, details = customs()
    records = {
        (mapping["purchase"]["type"], order_id): order,
        (mapping["customs"]["type"], customs_id): header,
        (mapping["pl"]["type"], "783"): {mapping["pl"]["number"]: "PL001"},
    }
    records.update({(mapping["purchase_line"]["type"], key): value for key, value in order_lines})
    records.update({(mapping["customs_line"]["type"], key): value for key, value in details})
    calls = []

    def validate(kind, identity=None):
        if kind not in ns.settings.record_types:
            raise ApiError(403, "记录类型未授权")

    def request(method, kind, identity, **kwargs):
        assert method == "GET"
        return {"data": deepcopy(records[kind, identity])}

    def filtered(kind, field, identity, **kwargs):
        candidates = {
            mapping["purchase"]["type"]: [order_id],
            mapping["purchase_line"]["type"]: [key for key, _ in order_lines],
            mapping["customs_line"]["type"]: [key for key, _ in details],
        }
        return candidates[kind]

    def relation_rows(kind, ids):
        calls.append(kind)
        value = evidence()
        return deepcopy(
            {
                "parent_headers": [PARENT],
                "sales_headers": [SALES],
                "packing_by_customs": value["packingLines"],
                "purchase_links": value["purchaseLinks"],
                "parent_lines": value["parentLines"],
            }[kind]
        )

    def no_comparison(payload):
        pytest.fail("原始来源缺失时不能继续调用依赖它的 v3 追溯")

    ns.validate, ns.request, ns.filtered_ids = validate, request, filtered
    ns.projected_records = lambda kind, ids, fields: {
        key: {"id": key, **ns.request("GET", kind, key)["data"]} for key in ids
    }
    ns.relation_rows, ns.pl_script_query = relation_rows, no_comparison
    ns.finance_source_query = lambda ids: unavailable()
    ns.settings.finance_source_script, ns.settings.finance_source_deploy = "482", "1"
    ns.settings.pl_restlet_script, ns.settings.pl_restlet_deploy = "configured", "1"
    page = {
        "rows": [{"id": customs_id, "number": header["name"], "record": header}],
        "count": 1,
        "offset": 0,
        "hasMore": False,
        "nextOffset": None,
    }
    return ns, page, calls, records


@pytest.mark.parametrize("kind", ["customs-declarations", "sub-purchase-orders"])
@pytest.mark.parametrize("mode", ["sublist_unavailable", "fields_unavailable", "unconfigured"])
def test_base_save_review_and_task_generation_continue(source, engine, mode, kind):
    ns, page, calls, _ = source
    if mode == "fields_unavailable":
        ns.finance_source_query = lambda ids: unavailable("RAW_FIELDS_UNAVAILABLE")
    if mode == "unconfigured":
        ns.settings.finance_source_script = ""
        ns.settings.pl_restlet_script = ""
    if kind == "sub-purchase-orders":
        identity, head, _ = purchase()
        page = {**page, "rows": [{"id": identity, "number": head["name"], "record": head}]}
    events = create_events()
    storage = StorageService(ns, engine, events)
    assert storage.configuration()["allowed"] is True
    result = storage.sync_page(kind, lambda: page)["storage"]
    assert result["customs"]["created"] == result["purchase"]["created"] == 1
    assert result["relations"]["partial"] == 1 and result["relations"]["matched"] == 0
    assert result["relations"]["rawLines"] == 0
    assert any("精确追溯未完成" in warning for warning in result["warnings"])
    assert "parent_headers" in calls
    head = declaration(engine)
    assert head["relation_status"] == "partial"
    detail = DeclarationService(engine).detail(head["id"])
    assert detail["evidence"]["status"] == "partial" and "comparison" not in detail["evidence"]
    assert len(detail["orders"]) == 1 and len(detail["purchase_lines"]) == 2
    review = ReviewService(engine, DeclarationService(engine), events)
    group = review.browse(DeclarationListQuery()).groups[0]
    review.approve(int(group.id), ApproveRequest(contentSha256=group.contentSha256), "user:admin")
    assert len(rows(engine, "SELECT id FROM task_tasks")) == 1
    tasks = rows(engine, "SELECT expected_amount, expected_quantity FROM task_lines ORDER BY id")
    assert [Decimal(str(row["expected_amount"])) for row in tasks] == [Decimal("100.50"), Decimal("20")]
    assert all(Decimal(str(row["expected_quantity"])) == Decimal("10") for row in tasks)
    # 同一基础数据重拉不会因本次追溯缺失重复生成任务或使已有审核失效。
    storage.sync_page(kind, lambda: page)
    assert review.browse(DeclarationListQuery()).groups[0].review.status == "approved"
    assert len(rows(engine, "SELECT id FROM task_tasks")) == 1


def test_missing_v3_config_is_warning_not_save_prerequisite(source, engine):
    ns, page, _, _ = source
    ns.finance_source_query = lambda ids: success(ids)
    ns.settings.pl_restlet_script = ""
    result = StorageService(ns, engine, create_events()).sync_page("customs-declarations", lambda: page)
    assert result["storage"]["customs"]["created"] == 1
    assert any("v3关联查询接口未配置" in warning for warning in result["storage"]["warnings"])
    assert declaration(engine)["relation_status"] == "partial"


@pytest.mark.parametrize("failure", ["base_read", "base_field", "auth", "account", "parent_header"])
def test_base_and_unexpected_errors_still_leave_existing_data_unchanged(source, engine, failure):
    ns, page, _, records = source
    storage = StorageService(ns, engine, create_events())
    storage.sync_page("customs-declarations", lambda: page)
    before = declaration(engine)["content_sha256"]
    mapping = ns.settings.pl_lookup
    records[mapping["purchase_line"]["type"], "2001"]["custrecord_swc_subpo_item_amountwithtax"] = Decimal(
        "999"
    )
    if failure == "base_read":

        def fail_request(*args, **kwargs):
            raise ApiError(502, "基础明细读取失败")

        ns.request = fail_request
    elif failure == "base_field":
        del records[mapping["purchase_line"]["type"], "2001"]["custrecord_swc_subpo_item_bgname"]
    elif failure == "auth":

        def fail_auth(ids):
            raise ApiError(502, "NS认证失败")

        ns.finance_source_query = fail_auth
    elif failure == "account":
        ns.finance_source_query = lambda ids: unavailable(account="other")
    else:
        previous = ns.relation_rows

        def fail_parent(kind, ids):
            if kind == "parent_headers":
                raise ApiError(502, "母采购币种读取失败")
            return previous(kind, ids)

        ns.relation_rows = fail_parent
    with pytest.raises(ApiError):
        storage.sync_page("customs-declarations", lambda: page)
    assert declaration(engine)["content_sha256"] == before
    stored = rows(engine, "SELECT amount FROM source_purchase_order_lines ORDER BY id")
    assert Decimal(str(stored[0]["amount"])) == Decimal("100.50")


def test_http_save_configuration_and_partial_warning(source, engine, context, monkeypatch, tmp_path):
    ns, page, _, _ = source
    settings = context.settings
    settings.account, settings.pl_lookup, settings.record_types = (
        ACCOUNT,
        ns.settings.pl_lookup,
        ns.settings.record_types,
    )
    settings.finance_source_script = settings.finance_source_deploy = ""
    settings.pl_restlet_script = settings.pl_restlet_deploy = ""
    settings.client_id = settings.certificate_id = "test-only"
    settings.private_key = tmp_path / "test-key"
    settings.private_key.write_text("test-only", encoding="utf-8")
    ns.settings = settings
    monkeypatch.setattr(
        "backend.modules.sync.pull_service.PullService.pull", lambda self, kind, request: page
    )
    with TestClient(create_app(settings, ns, engine)) as client:
        headers = {"Authorization": f"Bearer {settings.service_key}"}
        sources = client.get("/api/ns/sync/sources", headers=headers).json()["sources"]
        source = next(item for item in sources if item["kind"] == "customs-declarations")
        assert source["storageAllowed"] is True
        assert "精确追溯缺失会单独提示" in source["storageReason"]
        response = client.post(
            "/api/ns/sync/customs-declarations/pull-save", json={"limit": 20}, headers=headers
        )
    assert response.status_code == 200, response.text
    result = response.json()["storage"]
    assert result["customs"]["created"] == 1 and result["relations"]["partial"] == 1
    assert any("原始报关行接口未配置" in warning for warning in result["warnings"])

"""多选范围、真实结果提示及重启后请求条件一致性。"""

import pytest
from backend.core.errors import ApiError
from backend.modules.invoice.entity import headers, versions
from backend.modules.sync.dao import lemon_run_dao as runs
from backend.modules.sync.dto.lemon_invoice_dto import PullLemonInvoices
from backend.modules.sync.entity.lemon_run import lemon_runs
from backend.modules.sync.service.lemon_invoice_service import LemonInvoiceService
from backend.tests.sync.test_lemon_invoices import BASE, OWNER, body, count, invoice
from backend.tests.sync.test_lemon_invoices import setup as setup
from sqlalchemy import select, update


def pull(world, **changes):
    return world.client.post(BASE + "/invoices/pull-save", json=body(**changes))


def test_default_scope_imports_purchase_expense_and_discovered_types(setup):
    setup.upstream.rows = [
        invoice(BusinessTypeText="采购支出"),
        invoice(InvoiceId=2, Number="2", BusinessTypeText="办公费"),
    ]
    first = pull(setup)
    assert first.status_code == 200
    result = first.json()["result"]
    assert result["created"] == result["excluded"] == 1 and result["saved"]
    config = setup.client.get(BASE + "/invoices/configuration").json()
    assert config["defaultBusinessTypes"] == ["采购固定资产", "采购支出"]
    assert "办公费" in config["businessTypeOptions"]
    assert pull(setup, businessTypes=["办公费"]).json()["result"]["created"] == 1
    assert count(setup.engine, headers) == 2


def test_all_excluded_empty_and_unchanged_have_honest_messages(setup):
    setup.upstream.rows = [invoice(BusinessTypeText="采购支出")]
    skipped = pull(setup, businessTypes=["采购固定资产"]).json()["result"]
    assert skipped["excluded"] == 1 and not skipped["saved"]
    assert "本次未保存发票" in skipped["message"]
    assert count(setup.engine, headers) == 0
    assert pull(setup).json()["result"]["created"] == 1
    unchanged = pull(setup).json()["result"]
    assert unchanged["unchanged"] == 1 and not unchanged["saved"]
    assert "均已存在且未变化" in unchanged["message"]
    setup.upstream.rows = []
    empty = pull(setup).json()["result"]
    assert not empty["saved"] and "未查到" in empty["message"]
    assert count(setup.engine, versions) == 1


def test_unchecking_type_does_not_invalidate_existing_invoice(setup):
    assert pull(setup).json()["result"]["created"] == 1
    excluded = pull(setup, businessTypes=["采购支出"]).json()["result"]
    assert excluded["excluded"] == 1 and excluded["updated"] == 0
    with setup.engine.connect() as connection:
        assert connection.scalar(select(headers.c.status)) == "normal"
    assert count(setup.engine, versions) == 1


@pytest.mark.parametrize("types", [[], [""], [" "], ["采购支出", " 采购支出 "], [1], "采购支出", ["x" * 256]])
def test_invalid_types_rejected_before_upstream_or_database(setup, types):
    assert pull(setup, businessTypes=types).status_code == 400
    assert setup.upstream.pulls == 0 and count(setup.engine, lemon_runs) == 0


@pytest.mark.parametrize("phase", ["running", "completed", "failed"])
def test_scope_snapshot_survives_restart_and_failure(setup, phase):
    request = PullLemonInvoices(**body(businessTypes=["采购支出", "办公费"]))
    if phase == "running":
        setup.service._start(OWNER, request)
    else:
        if phase == "failed":
            setup.upstream.failure = ApiError(502, "测试失败")
            with pytest.raises(ApiError):
                setup.service.pull(OWNER, request)
        else:
            setup.service.pull(OWNER, request)
    service = LemonInvoiceService(setup.accounts, setup.events)
    stored = service.read(OWNER, request.requestId)
    assert stored["status"] == phase and set(stored["businessTypes"]) == {"采购支出", "办公费"}
    reordered = PullLemonInvoices(**{**request.model_dump(), "businessTypes": ["办公费", "采购支出"]})
    assert service.pull(OWNER, reordered) == stored
    changed = PullLemonInvoices(**{**request.model_dump(), "businessTypes": ["采购固定资产"]})
    with pytest.raises(ApiError, match="不同业务类型"):
        service.pull(OWNER, changed)
    if phase != "completed":
        assert stored["result"] is None


def test_old_completed_message_is_corrected_without_rewriting_history(setup):
    request = PullLemonInvoices(**body(businessTypes=["采购固定资产"]))
    scope, _, _ = setup.service._start(OWNER, request)
    historical = {
        "created": 0,
        "updated": 0,
        "unchanged": 0,
        "fetched": 7,
        "excluded": 7,
        "pendingDetails": 0,
        "saved": True,
        "message": "拉取结果已提交",
    }
    with setup.engine.begin() as connection:
        runs.finish(connection, scope, request.requestId, "completed", result=historical)
    result = setup.service.read(OWNER, request.requestId)
    assert result["businessTypes"] == ["采购固定资产"]
    assert not result["result"]["saved"] and "全部不在所选业务类型" in result["result"]["message"]
    with setup.engine.connect() as connection:
        assert runs.get(connection, scope, request.requestId)["result"] == historical


def test_old_running_request_uses_original_scope(setup):
    request = PullLemonInvoices(**body(businessTypes=["采购固定资产"]))
    setup.service._start(OWNER, request)
    with setup.engine.begin() as connection:
        connection.execute(update(lemon_runs).values(result=None))
    assert setup.service.pull(OWNER, request)["status"] == "running"
    with pytest.raises(ApiError, match="不同业务类型"):
        setup.service.pull(
            OWNER, PullLemonInvoices(**{**request.model_dump(), "businessTypes": ["采购支出"]})
        )

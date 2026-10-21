"""NS 后台保存批次：持久请求编号、按编号查询实际结果、结果未知不重试。"""

import logging
from threading import Event

import pytest
from backend.core.database import make_engine
from backend.core.errors import ApiError
from backend.modules.sync.dto.ns_run_dto import NsRunRequest
from backend.modules.sync.entity.ns_run import ns_runs
from backend.modules.sync.service.ns_run_service import NsRunService
from backend.modules.sync.service.progress_service import ProgressService
from backend.tests.test_sync_pull import sync_api as sync_api
from pydantic import ValidationError

REQUEST = "0f8fad5b-d9cb-469f-a165-70867728950e"
RANGE = {"startDate": "2026-09-01", "endDate": "2026-09-30", "requireDateRange": True}


class Immediate:
    """测试用执行器：提交即执行，便于断言最终状态。"""

    def submit(self, function, *args):
        function(*args)

    def shutdown(self, wait=True):
        pass


class Settings:
    account = "td001"


class Pulls:
    def __init__(self, outcome=None):
        self.settings = Settings()
        self.progress = ProgressService()
        self.outcome = outcome or (lambda report: page("completed"))
        self.calls = []

    def ensure_storage(self, kind):
        pass

    def pull_and_save(self, kind, request, owner):
        self.calls.append((kind, request.offset, request.partialSave))
        with self.progress.track(request.progressId, owner) as report:
            return self.outcome(report)


def page(status):
    counts = {"saved": 1, "failed": int(status == "partial"), "unknown": 0, "not_processed": 0}
    return {"count": 1, "hasMore": False, "batch": {"status": status, "counts": counts, "items": []}}


def body(**changes):
    return NsRunRequest(
        **{"requestId": REQUEST, "kind": "customs-declarations", "offset": 0, **RANGE, **changes}
    )


@pytest.fixture
def engine(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'runs.sqlite'}")
    ns_runs.create(engine)
    yield engine
    engine.dispose()


def test_result_is_persisted_and_same_request_never_reruns(engine):
    pulls = Pulls()
    service = NsRunService(engine, pulls, Immediate())
    run = service.start("owner", body())
    assert run["status"] == "completed" and run["result"]["batch"]["counts"]["saved"] == 1
    assert run["request"] == {"offset": 0, "limit": 20, **RANGE}
    # 提交响应丢失后用同一编号再次提交，只返回原结果。
    again = service.start("owner", body())
    assert again["status"] == "completed" and pulls.calls == [("customs-declarations", 0, True)]
    assert service.read("owner", REQUEST)["result"] == run["result"]
    with pytest.raises(ApiError) as error:
        service.read("other", REQUEST)
    assert error.value.status == 404


def test_same_request_with_other_page_is_rejected(engine):
    service = NsRunService(engine, Pulls(), Immediate())
    service.start("owner", body())
    with pytest.raises(ApiError) as error:
        service.start("owner", body(offset=20))
    assert error.value.status == 409


def test_cursor_is_persisted_passed_to_save_and_included_in_idempotency(engine):
    cursor = {"afterId": "100", "throughId": None, "offset": 0}
    request = body(offset=20000, cursor=cursor)
    assert request.pull_request("a" * 32).cursor.model_dump() == cursor
    service = NsRunService(engine, Pulls(), Immediate())
    run = service.start("owner", request)
    assert run["request"]["cursor"] == cursor
    assert service.start("owner", request)["status"] == "completed"
    with pytest.raises(ApiError) as error:
        service.start("owner", body(offset=20000, cursor={**cursor, "afterId": "200"}))
    assert error.value.status == 409


@pytest.mark.parametrize(
    "failure,status",
    [
        (ApiError(502, "NS 列表读取失败"), "failed"),
        (ApiError(409, "当前账户已有采购报关保存操作"), "failed"),
        (ApiError(503, "数据库连接中断，请先核实已保存单据"), "unknown"),
        (RuntimeError("bug"), "unknown"),
    ],
)
def test_errors_map_to_failed_or_unknown(engine, failure, status, caplog):
    def outcome(report):
        raise failure

    pulls = Pulls(outcome)
    with caplog.at_level(logging.ERROR, logger="ns_api.sync"):
        run = NsRunService(engine, pulls, Immediate()).start("owner", body())
    assert run["status"] == status and run["result"] is None and run["error"]
    assert len(pulls.calls) == 1


def test_running_record_without_worker_is_unknown_and_not_retried(engine):
    entered = Event()

    class Hold:
        def submit(self, function, *args):
            entered.set()  # 模拟进程在执行期间退出：记录保持 running。

    service = NsRunService(engine, Pulls(), Hold())
    assert service.start("owner", body())["status"] == "running"
    restarted = Pulls()
    view = NsRunService(engine, restarted, Immediate()).start("owner", body())
    assert view["status"] == "unknown" and "待核实" in view["statusLabel"]
    assert restarted.calls == []


def test_running_batch_reports_progress_then_final_result(engine):
    entered, release = Event(), Event()

    def outcome(report):
        report("整页读取：读取报关明细", 1, 3)
        entered.set()
        assert release.wait(5)
        return page("partial")

    service = NsRunService(engine, Pulls(outcome))
    try:
        assert service.start("owner", body())["status"] == "running"
        assert entered.wait(5)
        running = service.read("owner", REQUEST)
        assert running["status"] == "running" and running["progress"]["completed"] == 1
        release.set()
    finally:
        service.stop()
    final = service.read("owner", REQUEST)
    assert final["status"] == "partial" and final["progress"] is None


def test_stopped_service_rejects_new_batches(engine):
    service = NsRunService(engine, Pulls(), Immediate())
    service.stop()
    with pytest.raises(ApiError) as error:
        service.start("owner", body())
    assert error.value.status == 503


def test_request_rejects_old_protocol_switches():
    with pytest.raises(ValidationError):
        body(partialSave=True)
    with pytest.raises(ValidationError):
        body(progressId="a" * 32)
    with pytest.raises(ValidationError):
        NsRunRequest(requestId="not-a-uuid", kind="customs-declarations", **RANGE)
    with pytest.raises(ValidationError):
        NsRunRequest(requestId=REQUEST, kind="purchase-orders", **RANGE)


def test_http_requires_identity_and_reports_config_without_creating_run(sync_api):
    client, headers, context, calls = sync_api
    payload = {"requestId": REQUEST, "kind": "customs-declarations", "offset": 0, **RANGE}
    assert client.post("/api/sync/ns/runs", json=payload).status_code == 401
    assert client.get(f"/api/sync/ns/runs/{REQUEST}").status_code == 401
    # 测试配置未提供保存字段映射：同步返回原因，不创建批次、不读取 NS。
    response = client.post("/api/sync/ns/runs", headers=headers, json=payload)
    assert response.status_code == 503
    assert client.get(f"/api/sync/ns/runs/{REQUEST}", headers=headers).status_code == 404
    assert client.get("/api/sync/ns/runs/bad-id", headers=headers).status_code == 400
    assert calls == []

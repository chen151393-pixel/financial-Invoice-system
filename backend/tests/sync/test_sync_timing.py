"""每批耗时汇总：只含类别、次数和毫秒数；并发读取计入同一批次；整页读取失败改逐组读取并留痕。"""

import logging
import time

import pytest
from backend.core.errors import ApiError
from backend.integrations.netsuite import request_stats
from backend.integrations.netsuite.read_batch import RecordReader
from backend.modules.source.service.storage_service import StorageService
from backend.modules.sync.dto.source_dto import PullRequest
from backend.modules.sync.pull_service import PullService
from backend.tests.test_source_storage import engine as engine
from backend.tests.test_source_storage import ns as ns
from backend.tests.test_source_storage import rows
from backend.tests.test_sync_optimization import batch as batch
from backend.tests.test_sync_partial_save import page_result


class FakeNs:
    class settings:
        sync_read_workers = 2

    def validate(self, record_type, identity=None):
        pass

    def request(self, method, record_type, identity, **kwargs):
        request_stats.record_request("record", time.monotonic())
        return {"data": {"id": identity, "secret": "不应进入日志"}}


def timing_lines(caplog):
    return [r.getMessage() for r in caplog.records if r.getMessage().startswith("ns_sync_timing")]


def test_summary_counts_parallel_requests_and_phases(caplog):
    with caplog.at_level(logging.INFO, logger="ns_api.netsuite"):
        with request_stats.collect("customs-declarations@0"):
            RecordReader(FakeNs()).prefetch("customrecord_customs", ["1", "2", "3"], "读取")
            with request_stats.phase("db_write"):
                pass
    [line] = timing_lines(caplog)
    assert "batch=customs-declarations@0 outcome=ok" in line
    assert "ns_record=3/" in line and "db_write=1/" in line
    assert "不应进入日志" not in line and "customrecord_customs" not in line
    # 批次外的请求不计入任何汇总，也不报错。
    request_stats.record_request("record", time.monotonic())


def test_failed_batch_still_logs_summary(caplog):
    with caplog.at_level(logging.INFO, logger="ns_api.netsuite"), pytest.raises(ApiError):
        with request_stats.collect("sub-purchase-orders@20"):
            raise ApiError(502, "失败")
    [line] = timing_lines(caplog)
    assert "outcome=error" in line and line.endswith("none")


def test_pull_and_save_logs_one_summary_per_batch(caplog):
    class Storage:
        def sync_partial_page(self, kind, read, progress=None):
            return {"batch": {"status": "completed"}}

    service = PullService(None, None, Storage())
    with caplog.at_level(logging.INFO, logger="ns_api.netsuite"):
        service.pull_and_save("customs-declarations", PullRequest(partialSave=True, offset=40))
    [line] = timing_lines(caplog)
    assert "batch=customs-declarations@40 outcome=ok" in line


def test_whole_page_failure_falls_back_to_group_reads(batch, engine, caplog):
    ns, page, _, _ = batch
    original = ns.projected_records

    def projected(kind, ids, fields):
        if "2011" in ids:
            raise ApiError(502, "明细读取失败")
        return original(kind, ids, fields)

    ns.projected_records = projected
    with caplog.at_level(logging.INFO, logger="ns_api.source"):
        result = StorageService(ns, engine).sync_partial_page(
            "customs-declarations", lambda: page_result(page[:3])
        )
    assert any("ns_sync_whole_page_fallback" in r.getMessage() for r in caplog.records)
    assert result["batch"]["counts"] == {"saved": 2, "failed": 1, "unknown": 0, "not_processed": 0}
    assert len(rows(engine, "SELECT id FROM source_customs_declarations")) == 2

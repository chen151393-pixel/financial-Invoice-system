"""回签分片与持久队列：隔离磁盘和 SQLite；并发另在专用 MySQL 验证。"""

import base64
from dataclasses import replace
from uuid import uuid4

import pytest
from backend.app import create_app
from backend.core.database import make_engine
from backend.core.errors import ApiError
from backend.modules.task.dto.signed_upload_dto import (
    CreateSignedUpload,
    RetrySignedUpload,
    SignedUploadChunk,
)
from backend.modules.task.entity import signed_upload_jobs
from backend.modules.task.policy.signed_upload_policy import CHUNK_BYTES, MAX_FILE_BYTES
from backend.modules.task.service.signed_upload_service import SignedUploadService
from backend.modules.task.service.signed_upload_store import SignedUploadStore
from backend.modules.task.service.signed_upload_worker import SignedUploadWorker
from backend.modules.task.vo.signed_contract_vo import SignedUploadItem
from fastapi.testclient import TestClient
from sqlalchemy import select

USER = "user:admin"


class Processor:
    def __init__(self):
        self.calls = []

    def process_content(self, filename, content, order_no, actor):
        self.calls.append((filename, len(content), order_no, actor))
        if filename == "bad.pdf":
            raise ApiError(409, "未匹配到订单")
        return SignedUploadItem(
            filename=filename,
            orderNumber=order_no,
            status="saved",
            reason="已保存",
            archivePath="isolated/test.pdf",
        )


@pytest.fixture
def queue(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'queue.db'}")
    signed_upload_jobs.create(engine)
    store = SignedUploadStore(tmp_path / "spool")
    service = SignedUploadService(engine, store)
    processor = Processor()
    yield service, SignedUploadWorker(engine, store, processor), processor
    engine.dispose()


def create(service, files):
    body = CreateSignedUpload(
        requestId=uuid4(), files=[dict(filename=name, size=size) for name, size in files]
    )
    return service.create(body, USER), body


def chunk(service, batch, index, data, offset=0):
    return service.chunk(
        batch.id,
        batch.items[index].id,
        SignedUploadChunk(offset=offset, content=base64.b64encode(data).decode()),
        USER,
    )


def test_manifest_idempotent_and_user_isolation(queue):
    service, _, _ = queue
    job, body = create(service, [("one.pdf", 10)])
    assert service.create(body, USER).items[0].id == job.items[0].id
    body.files[0].size = 11
    with pytest.raises(ApiError, match="清单"):
        service.create(body, USER)
    for actor in ["service:key", "user:other"]:
        with pytest.raises(ApiError):
            service.get(job.id, actor)
        with pytest.raises(ApiError):
            service.chunk(job.id, job.items[0].id, SignedUploadChunk(offset=0, content="YQ=="), actor)
    assert service.recent("user:other") == {"items": []}


def test_chunks_restart_duplicate_and_worker_single_failure_isolated(queue):
    service, worker, processor = queue
    job, _ = create(service, [("ok.pdf", 6), ("bad.pdf", 3), ("too-big.pdf", MAX_FILE_BYTES + 1)])
    assert job.items[2].status == "failed"
    job = chunk(service, job, 0, b"abc")
    assert job.items[0].receivedBytes == 3 and job.items[0].status == "uploading"
    worker.run_once()
    assert not processor.calls
    restarted = SignedUploadService(service.engine, SignedUploadStore(service.store.root))
    assert chunk(restarted, job, 0, b"abc").items[0].receivedBytes == 3
    with pytest.raises(ApiError, match="内容不同"):
        chunk(service, job, 0, b"xyz")
    with pytest.raises(ApiError, match="偏移"):
        chunk(service, job, 0, b"x", 4)
    job = chunk(restarted, job, 0, b"def", 3)
    chunk(restarted, job, 1, b"bad")
    worker.run_once()
    result = restarted.get(job.id, USER)
    assert [v.status for v in result.items] == ["saved", "failed", "failed"]
    assert result.finished == 3 and result.saved == 1 and result.progressPercent == 100
    assert result.uploadPercent == 100  # 被拒绝的超限文件不计入传输进度。
    assert len(processor.calls) == 2
    worker.run_once()
    assert len(processor.calls) == 2
    assert not restarted.store.path(job.items[0].id).exists()
    assert restarted.store.path(job.items[1].id).exists()
    restarted.retry(job.id, job.items[1].id, RetrySignedUpload(orderNo="SUB-1"), USER)
    worker.run_once()
    assert processor.calls[-1][2] == "SUB-1"


def test_full_100mb_file_is_accepted_in_bounded_chunks(queue):
    service, worker, processor = queue
    job, _ = create(service, [("large.pdf", MAX_FILE_BYTES)])
    payload = b"a" * CHUNK_BYTES
    for offset in range(0, MAX_FILE_BYTES, CHUNK_BYTES):
        job = chunk(service, job, 0, payload, offset)
    assert job.items[0].receivedBytes == MAX_FILE_BYTES and job.items[0].status == "queued"
    worker.run_once()
    assert processor.calls[0][1] == MAX_FILE_BYTES
    assert service.get(job.id, USER).items[0].status == "saved"


def test_uncommitted_disk_tail_is_rewritten_and_corruption_not_processed(queue):
    service, worker, processor = queue
    job, _ = create(service, [("one.pdf", 6)])
    chunk(service, job, 0, b"abc")
    service.store.put(job.items[0].id, 3, b"uncommitted-tail")
    chunk(service, job, 0, b"def", 3)
    assert service.store.path(job.items[0].id).read_bytes() == b"abcdef"
    service.store.path(job.items[0].id).write_bytes(b"badbad")
    worker.run_once()
    assert not processor.calls
    assert service.get(job.id, USER).items[0].status == "failed"


def test_oversize_chunk_cannot_change_committed_progress(queue):
    service, _, _ = queue
    job, _ = create(service, [("one.pdf", 3)])
    with pytest.raises(ApiError) as err:
        chunk(service, job, 0, b"1234")
    assert err.value.status == 413
    assert service.get(job.id, USER).items[0].receivedBytes == 0


def test_running_job_recovers_after_restart(queue):
    service, worker, processor = queue
    job, _ = create(service, [("one.pdf", 3)])
    chunk(service, job, 0, b"abc")
    with service.engine.begin() as c:
        c.execute(signed_upload_jobs.update().values(status="running"))
    SignedUploadWorker(service.engine, service.store, processor).run_once()
    assert service.get(job.id, USER).items[0].status == "saved"


def test_http_chunk_over_128kb_is_accepted_and_other_routes_stay_limited(context, tmp_path):
    settings = replace(context.settings, signed_upload_root=tmp_path / "spool")
    app = create_app(settings, context.ns, context.engine)
    # 不启动后台线程，HTTP 接收测试与后台消费分开确定性验收。
    client = TestClient(app)
    root = "/api/tasks/signed-contracts/upload-jobs"
    body = {"requestId": str(uuid4()), "files": [{"filename": "SUB-1.pdf", "size": 300000}]}
    assert client.post(root, json=body).status_code == 401
    headers = {"Origin": settings.origin}
    assert (
        client.post(
            "/api/session", headers=headers, json={"username": "admin", "password": settings.admin_password}
        ).status_code
        == 200
    )
    r = client.post(root, headers=headers, json=body)
    assert r.status_code == 202
    job = r.json()
    path = f"{root}/{job['id']}/files/{job['items'][0]['id']}/chunks"
    payload = {"offset": 0, "content": base64.b64encode(b"x" * 300000).decode()}
    assert client.post(path, headers={"Origin": "https://other.invalid"}, json=payload).status_code == 403
    r = client.post(path, headers=headers, json=payload)
    assert r.status_code == 202 and r.json()["items"][0]["status"] == "queued"
    assert client.post("/api/tasks/query", headers=headers, json=payload).status_code == 413
    assert (
        client.post(path, headers=headers, json={"offset": 0, "content": "x" * (6 * 1024 * 1024)}).status_code
        == 413
    )
    with context.engine.connect() as c:
        row = c.execute(select(signed_upload_jobs)).mappings().one()
    assert row["received_bytes"] == 300000
    client.close()

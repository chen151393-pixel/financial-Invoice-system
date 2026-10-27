"""MySQL 命名锁验证：同一文件只能由一个消费者归档。"""

from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from backend.core.errors import ApiError
from backend.modules.task.dto.signed_upload_dto import RetrySignedUpload
from backend.modules.task.service.signed_upload_service import SignedUploadService
from backend.modules.task.service.signed_upload_store import SignedUploadStore
from backend.modules.task.service.signed_upload_worker import SignedUploadWorker
from backend.tests.test_matching_mysql import engine as engine
from backend.tests.test_signed_upload_jobs import USER, Processor, chunk, create


def test_two_workers_and_retry_cannot_process_same_file(engine, tmp_path):
    entered, finish = Event(), Event()
    store = SignedUploadStore(tmp_path / "spool")
    service = SignedUploadService(engine, store)
    processor = Processor()
    process = processor.process_content

    def blocked(*args):
        entered.set()
        assert finish.wait(20)
        return process(*args)

    processor.process_content = blocked
    job, _ = create(service, [("one.pdf", 3)])
    chunk(service, job, 0, b"abc")
    first = SignedUploadWorker(engine, store, processor)
    second = SignedUploadWorker(engine, store, processor)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(first.run_once)
        try:
            assert entered.wait(20)
            second.run_once()
            with pytest.raises(ApiError, match="正在处理"):
                service.retry(job.id, job.items[0].id, RetrySignedUpload(), USER)
        finally:
            finish.set()
        future.result(timeout=20)
    second.run_once()
    assert len(processor.calls) == 1
    assert service.get(job.id, USER).items[0].status == "saved"

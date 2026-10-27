"""后台消费回签队列；同文件互斥，完整接收的原件在重启后继续处理。"""

import logging
from threading import Event, Thread

from sqlalchemy.exc import SQLAlchemyError

from backend.core.errors import ApiError

from ..dao import signed_upload_dao as dao
from ..policy.signed_upload_policy import MAX_FILE_BYTES
from .contract_lock import contract_lock
from .signed_upload_service import now

logger = logging.getLogger(__name__)


class SignedUploadWorker:
    def __init__(self, engine, store, contracts):
        self.engine, self.store, self.contracts = engine, store, contracts
        self.stopping, self.thread = Event(), None

    def start(self):
        self.stopping.clear()
        self.thread = Thread(target=self._run, name="signed-contract-upload", daemon=True)
        self.thread.start()

    def stop(self):
        self.stopping.set()
        if self.thread:
            self.thread.join()

    def _run(self):
        while not self.stopping.is_set():
            try:
                self.run_once()
            except Exception as error:  # noqa: BLE001 -- 后台线程隔离边界，只记录类型，保留持久队列。
                logger.error("signed_upload_worker_failed type=%s", type(error).__name__)
            self.stopping.wait(2)

    def run_once(self):
        # 独立于 NS 下载消费者，慢 NS 请求不会挡住回签上传。
        with contract_lock(self.engine, "signed-upload-worker") as acquired:
            if not acquired:
                return
            with self.engine.connect() as connection:
                rows = dao.pending(connection)
            for row in rows:
                if self.stopping.is_set():
                    break
                try:
                    self.process(row)
                except SQLAlchemyError:
                    logger.error("signed_upload_database_unavailable file=%s", row["id"])

    def process(self, candidate):
        file_id = candidate["id"]
        with contract_lock(self.engine, f"signed-upload:{file_id}") as acquired:
            if not acquired:
                return
            with self.engine.begin() as connection:
                row = dao.get(connection, candidate["actor"], candidate["batch_id"], file_id)
                if row is None or row["status"] not in {"queued", "running"}:
                    return
                dao.change(connection, file_id, status="running", updated_at=now())
            try:
                path = self.store.path(file_id)
                if (
                    not 0 < path.stat().st_size == row["size_bytes"] <= MAX_FILE_BYTES
                    or self.store.digest(file_id) != row["sha256"]
                ):
                    raise ApiError(409, "暂存文件不完整或内容变化，请重新上传")
                # 沿用无覆盖归档；中途重启后同内容返回已保存，不重复覆盖或推进任务。
                result = self.contracts.process_content(
                    row["filename"], path.read_bytes(), row["order_no"], row["actor"]
                )
                values = dict(
                    status=result.status,
                    reason=result.reason[:500],
                    order_no=result.orderNumber,
                    archive_path=result.archivePath,
                    updated_at=now(),
                )
            except ApiError as error:
                values = dict(status="failed", reason=error.message[:500], updated_at=now())
            except OSError:
                values = dict(
                    status="failed", reason="上传暂存文件无法读取，请检查暂存目录后重试", updated_at=now()
                )
            except SQLAlchemyError:
                # 归档可能已经成功，保留 running；恢复后核对原件摘要，不能误报已失败。
                raise
            except Exception as error:  # noqa: BLE001 -- 单文件隔离边界，不泄露业务或磁盘异常原文。
                logger.error("signed_upload_file_failed file=%s type=%s", file_id, type(error).__name__)
                values = dict(
                    status="failed", reason="文件处理异常，请联系管理员检查后重试", updated_at=now()
                )
            with self.engine.begin() as connection:
                dao.change(connection, file_id, **values)
            if values["status"] == "saved":
                try:
                    self.store.remove(file_id)
                except OSError:
                    logger.warning("signed_upload_cleanup_pending file=%s", file_id)

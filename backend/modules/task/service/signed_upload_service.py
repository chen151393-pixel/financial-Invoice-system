"""持久上传批次：分片落盘后排队，逐文件重试，不把整批文件放进内存。"""

import base64
import binascii
import hashlib
import json
from datetime import UTC, datetime
from uuid import uuid4

from backend.core.errors import ApiError

from ..dao import signed_upload_dao as dao
from ..policy.signed_upload_policy import CHUNK_BYTES, MAX_FILE_BYTES, RETRYABLE, progress
from ..vo.signed_upload_vo import SignedUploadBatch, SignedUploadJobFile
from .contract_lock import contract_lock


def now():
    return datetime.now(UTC).replace(tzinfo=None)


def require_user(actor):
    if not actor.startswith("user:"):
        raise ApiError(403, "服务身份不能操作回签上传队列")


class SignedUploadService:
    def __init__(self, engine, store):
        self.engine, self.store = engine, store

    def create(self, body, actor):
        require_user(actor)
        batch_id = str(body.requestId)
        digest = hashlib.sha256(json.dumps(body.model_dump(mode="json"), sort_keys=True).encode()).hexdigest()
        with contract_lock(self.engine, f"signed-upload-batch:{actor}:{batch_id}") as acquired:
            if not acquired:
                raise ApiError(409, "该上传任务正在建立，请稍后重试")
            with self.engine.begin() as connection:
                existing = dao.batch(connection, actor, batch_id)
                if existing:
                    if existing[0]["manifest_sha256"] != digest:
                        raise ApiError(409, "同一上传任务不能更换文件清单")
                else:
                    rows = []
                    for index, item in enumerate(body.files):
                        reason = (
                            "文件不能为空且单个不能超过 100 MB" if not 0 < item.size <= MAX_FILE_BYTES else ""
                        )
                        rows.append(
                            dict(
                                id=str(uuid4()),
                                batch_id=batch_id,
                                actor=actor,
                                position=index,
                                manifest_sha256=digest,
                                filename=item.filename,
                                order_no=item.orderNo.strip(),
                                size_bytes=item.size,
                                received_bytes=0,
                                status="failed" if reason else "uploading",
                                reason=reason,
                                sha256=None,
                                archive_path=None,
                                created_at=now(),
                                updated_at=now(),
                            )
                        )
                    dao.create(connection, rows)
        return self.get(batch_id, actor)

    def get(self, batch_id, actor):
        require_user(actor)
        with self.engine.connect() as connection:
            rows = dao.batch(connection, actor, batch_id)
        if not rows:
            raise ApiError(404, "上传任务不存在")
        return SignedUploadBatch(
            id=batch_id,
            chunkBytes=CHUNK_BYTES,
            maxFileBytes=MAX_FILE_BYTES,
            **progress(rows),
            items=[
                SignedUploadJobFile(
                    id=r["id"],
                    filename=r["filename"],
                    size=r["size_bytes"],
                    receivedBytes=r["received_bytes"],
                    status=r["status"],
                    reason=r["reason"],
                    orderNumber=r["order_no"],
                    archivePath=r["archive_path"],
                    canRetry=r["status"] in RETRYABLE and bool(r["sha256"]),
                )
                for r in rows
            ],
        )

    def recent(self, actor):
        require_user(actor)
        with self.engine.connect() as connection:
            ids = dao.recent_batches(connection, actor)
        return {"items": [self.get(v, actor) for v in ids]}

    def _file(self, batch_id, file_id, actor):
        require_user(actor)
        with self.engine.connect() as connection:
            row = dao.get(connection, actor, batch_id, file_id)
        if row is None:
            raise ApiError(404, "上传文件不存在")
        return row

    def chunk(self, batch_id, file_id, body, actor):
        require_user(actor)
        try:
            content = base64.b64decode(body.content, validate=True)
        except (ValueError, binascii.Error):
            raise ApiError(422, "文件分片编码无效") from None
        if not 0 < len(content) <= CHUNK_BYTES:
            raise ApiError(413, "单个上传分片不能超过 4 MB")
        with contract_lock(self.engine, f"signed-upload:{file_id}") as acquired:
            if not acquired:
                raise ApiError(409, "该文件正在接收或处理，请稍后查询进度")
            row = self._file(batch_id, file_id, actor)
            end = body.offset + len(content)
            try:
                # 允许网络响应丢失后重传同一个已提交分片，不增加字节数或重复排队。
                if end <= row["received_bytes"] and row["status"] != "saved":
                    if not self.store.matches(file_id, body.offset, content):
                        raise ApiError(409, "重复上传的分片内容不同，请重新建立上传任务")
                elif row["status"] == "uploading" and body.offset == row["received_bytes"]:
                    if end > row["size_bytes"] or end > MAX_FILE_BYTES:
                        raise ApiError(413, "文件超过声明大小或 100 MB 上限")
                    self.store.put(file_id, body.offset, content)
                    complete = end == row["size_bytes"]
                    digest = self.store.digest(file_id) if complete else None
                    with self.engine.begin() as connection:
                        dao.change(
                            connection,
                            file_id,
                            received_bytes=end,
                            sha256=digest,
                            status="queued" if complete else "uploading",
                            updated_at=now(),
                        )
                elif row["status"] == "saved" and end <= row["received_bytes"]:
                    # 成功文件已清理暂存；返回持久成功事实，不再接受任何字节修改。
                    pass
                else:
                    raise ApiError(409, "上传偏移或状态已变化，请刷新任务后继续")
            except OSError:
                raise ApiError(503, "上传暂存失败，请检查服务器磁盘；已接收进度保留") from None
        return self.get(batch_id, actor)

    def retry(self, batch_id, file_id, body, actor):
        require_user(actor)
        with contract_lock(self.engine, f"signed-upload:{file_id}") as acquired:
            if not acquired:
                raise ApiError(409, "该文件正在处理，请稍后重试")
            row = self._file(batch_id, file_id, actor)
            if row["status"] not in RETRYABLE or not row["sha256"]:
                raise ApiError(409, "该文件不可重试；未完整上传的文件需要重新选择上传")
            with self.engine.begin() as connection:
                dao.change(
                    connection,
                    file_id,
                    status="queued",
                    reason="",
                    order_no=body.orderNo.strip() or row["order_no"],
                    updated_at=now(),
                )
        return self.get(batch_id, actor)

"""子采购合同：从 NS 下载并保存到共享盘，数据库只记录路径与校验值。

顺序固定（后端规则第 7 节）：事务外下载 → 短事务登记首次获取记录 → 事务外写共享盘 → 短事务标记已归档；
全部子采购单的合同都已归档时，任务进入"待通知供应商"。共享盘按首次获取日期建文件夹，重试不会另存一份。
"""

import hashlib
from datetime import UTC, datetime, timezone

from sqlalchemy.exc import SQLAlchemyError

from backend.core.errors import ApiError

from ..dao import document_dao, task_dao, task_line_dao
from .task_status_service import change_status


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class DocumentService:
    def __init__(self, engine, directory, contracts, archive, tasks):
        self.engine, self.directory = engine, directory
        self.contracts, self.archive, self.tasks = contracts, archive, tasks

    def prepare(self, task_id, order_id, actor):
        if actor.startswith("service:"):
            raise ApiError(403, "服务身份只读，不能获取或保存合同")
        task, existing = self._check(task_id, order_id)
        if existing and existing["status"] == "archived":
            return self.tasks.detail(task_id)
        names = self.directory.describe(
            supplier_ids=[task["supplier_id"]] if task["supplier_id"] else [], order_ids=[order_id]
        )
        order_no = names["orders"].get(order_id) or ""
        supplier = (names["suppliers"].get(task["supplier_id"]) or {}).get("name") or ""
        if not order_no:
            raise ApiError(409, "子采购单编号缺失，无法获取合同")
        # 网络下载在数据库事务之外；成功后在短事务中再次核对任务与首次获取记录。
        contract = self.contracts.download(order_no, supplier, task["record_no"] or "")
        digest = hashlib.sha256(contract["content"]).hexdigest()
        record = self._register(task_id, order_id, order_no, contract, digest)
        if record["status"] == "archived":
            return self.tasks.detail(task_id)
        fetched_at = record["created_at"].replace(tzinfo=UTC).timestamp()
        try:
            path, filename = self.archive.save(order_no, supplier, fetched_at, contract["content"])
        except ApiError as error:
            self._fail(record["id"], error.message)
            raise
        self._archive(task_id, record["id"], path, filename, actor)
        return self.tasks.detail(task_id)

    def _check(self, task_id, order_id):
        try:
            with self.engine.connect() as connection:
                task = task_dao.get(connection, task_id)
                if task is None:
                    raise ApiError(404, "开票任务不存在")
                order_ids = self.tasks.order_ids(task_line_dao.by_tasks(connection, [task_id]))
                existing = document_dao.get(connection, task_id, order_id)
        except SQLAlchemyError:
            raise ApiError(503, "开票任务读取失败，请检查业务数据库") from None
        if order_id not in order_ids:
            raise ApiError(404, "子采购单不属于此任务")
        if task["status"] == "superseded":
            raise ApiError(409, "任务已被新审核版本替代，不能继续准备资料")
        if self.archive is None or self.archive.root is None:
            raise ApiError(503, "合同共享盘路径尚未配置")
        if self.contracts is None:
            raise ApiError(503, "子采购合同下载接口尚未配置")
        reason = self.contracts.unavailable_reason()
        if reason:
            raise ApiError(503, reason)
        return task, existing

    def _register(self, task_id, order_id, order_no, contract, digest):
        try:
            with self.engine.begin() as connection:
                task = task_dao.get(connection, task_id, lock=True)
                if task["status"] == "superseded":
                    raise ApiError(409, "任务已被新审核版本替代，文件未入库")
                record = document_dao.get(connection, task_id, order_id, lock=True)
                if record is None:
                    document_dao.insert_document(
                        connection,
                        {
                            "task_id": task_id,
                            "purchase_order_id": order_id,
                            "order_no": order_no,
                            "ns_environment": contract["environment"],
                            "ns_file_id": contract["ns_id"],
                            "filename": contract["filename"],
                            "sha256": digest,
                        },
                        _now(),
                    )
                    return document_dao.get(connection, task_id, order_id)
                if record["status"] != "archived" and (
                    record["sha256"] != digest
                    or record["ns_file_id"] != contract["ns_id"]
                    or record["ns_environment"] != contract["environment"]
                ):
                    raise ApiError(409, "合同来源或内容与首次获取记录不同，未覆盖共享盘；请人工核对")
                return record
        except SQLAlchemyError:
            raise ApiError(503, "合同记录保存失败，流程未推进；请检查业务数据库") from None

    def _fail(self, document_id, message):
        try:
            with self.engine.begin() as connection:
                document_dao.update_document(
                    connection, document_id, {"status": "failed", "error_message": message[:500]}, _now()
                )
        except SQLAlchemyError:
            # 记录失败原因只用于展示；不能掩盖原始的共享盘错误。
            pass

    def _archive(self, task_id, document_id, path, filename, actor):
        try:
            with self.engine.begin() as connection:
                task = task_dao.get(connection, task_id, lock=True)
                now = _now()
                document_dao.update_document(
                    connection,
                    document_id,
                    {
                        "status": "archived",
                        "archive_path": path,
                        "filename": filename,
                        "archived_at": now,
                        "error_message": None,
                    },
                    now,
                )
                order_ids = self.tasks.order_ids(task_line_dao.by_tasks(connection, [task_id]))
                saved = document_dao.by_task(connection, task_id)
                archived = {row["purchase_order_id"] for row in saved if row["status"] == "archived"}
                if task["status"] == "documents_pending" and set(order_ids) <= archived:
                    change_status(
                        connection, task, "notify_pending", actor, "子采购合同已全部保存到共享盘", now
                    )
        except SQLAlchemyError:
            raise ApiError(
                503, "文件已保存到共享盘，但记录保存失败；请重试，同内容文件不会重复覆盖"
            ) from None
        if task["status"] == "superseded":
            raise ApiError(409, "文件已保存到共享盘，但任务已被新审核版本替代，未推进任务")

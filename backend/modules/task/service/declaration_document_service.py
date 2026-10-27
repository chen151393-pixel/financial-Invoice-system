"""报关资料（报关单、销售合同、发票）：从 NS 下载并保存到该报关单的共享盘文件夹，数据库只记录路径与校验值。

- 审核通过生成任务时登记三类待下载记录（按报关单各一份，各供应商任务共用），后台队列逐条下载；
- 每类资料可单独人工重试或重新下载；失败只记录原因，不影响通知供应商，只影响任务完结；
- 顺序：事务外读取 NS 与写共享盘 → 短事务标记已归档并重算该报关单下任务的完结状态。
"""

import hashlib
from datetime import datetime, timezone

from sqlalchemy.exc import SQLAlchemyError

from backend.core.errors import ApiError
from backend.core.write_lock import transaction
from backend.integrations.contract_archive import document_filename

from ..dao import declaration_document_dao, task_dao
from ..policy.document_policy import DECLARATION_DOCUMENTS
from .contract_lock import contract_lock
from .progress_service import refresh_tasks

BUSY_REASON = "该资料正在下载归档，请稍后刷新或重试"


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class DeclarationDocumentService:
    def __init__(self, engine, directory, contracts, archive, tasks):
        self.engine, self.directory = engine, directory
        self.contracts, self.archive, self.tasks = contracts, archive, tasks

    def retry(self, task_id, doc_type, actor):
        """任务详情页的单项人工重试 / 重新下载；返回最新任务详情。"""
        if actor.startswith("service:"):
            raise ApiError(403, "服务身份只读，不能下载报关资料")
        if doc_type not in DECLARATION_DOCUMENTS:
            raise ApiError(404, "不支持的报关资料类型")
        try:
            with transaction(self.engine) as connection:
                task = task_dao.get(connection, task_id)
                if task is None:
                    raise ApiError(404, "开票任务不存在")
                if task["status"] == "superseded":
                    raise ApiError(409, "任务已被新审核版本替代，不能下载资料")
                # 本功能上线前生成的任务没有登记记录，人工重试时补登记
                declaration_document_dao.ensure(
                    connection,
                    task["customs_declaration_id"],
                    task["ns_account"],
                    task["record_no"],
                    actor,
                    _now(),
                )
        except SQLAlchemyError:
            raise ApiError(503, "报关资料记录读取失败，请检查业务数据库") from None
        self.prepare(task["customs_declaration_id"], doc_type, actor)
        return self.tasks.detail(task_id)

    def prepare(self, declaration_id, doc_type, actor):
        """下载并归档一类报关资料；后台队列与人工重试共用。"""
        with contract_lock(self.engine, f"declaration:{declaration_id}:{doc_type}") as acquired:
            if not acquired:
                raise ApiError(409, BUSY_REASON)
            self._prepare(declaration_id, doc_type, actor)

    def unavailable_reason(self):
        if self.archive is None or self.archive.root is None:
            return "合同共享盘路径尚未配置"
        if self.contracts is None:
            return "报关资料下载接口尚未配置"
        return self.contracts.declaration_unavailable_reason()

    def _prepare(self, declaration_id, doc_type, actor):
        try:
            with transaction(self.engine) as connection:
                row = declaration_document_dao.get(connection, declaration_id, doc_type, lock=True)
                if row is None:
                    raise ApiError(404, "报关资料记录不存在")
                declaration_document_dao.start_attempt(connection, row["id"], actor, _now())
        except SQLAlchemyError:
            raise ApiError(503, "报关资料记录保存失败，请检查业务数据库") from None
        try:
            reason = self.unavailable_reason()
            if reason:
                raise ApiError(503, reason)
            head = self.directory.declarations([declaration_id]).get(declaration_id)
            if head is None:
                raise ApiError(404, "报关单不存在")
            files = self._download(head, doc_type, row["files"] or [])
        except ApiError as error:
            self._fail(row["id"], error.message)
            raise
        try:
            with transaction(self.engine) as connection:
                now = _now()
                declaration_document_dao.archived(connection, row["id"], files["files"], files["ns_id"], now)
                refresh_tasks(
                    connection,
                    task_dao.current_ids_by_declaration(connection, declaration_id),
                    actor,
                    f"{DECLARATION_DOCUMENTS[doc_type]}已保存到共享盘",
                    now,
                )
        except SQLAlchemyError:
            raise ApiError(
                503, "文件已保存到共享盘，但记录保存失败；请重试，同内容文件不会重复覆盖"
            ) from None

    def _download(self, head, doc_type, archived_files):
        # 网络下载与写共享盘都在数据库事务之外
        result = self.contracts.download_declaration(head["record_no"], head["declaration_no"], doc_type)
        label, count = DECLARATION_DOCUMENTS[doc_type], len(result["files"])
        planned = [
            {
                "filename": document_filename(label, head["record_no"], index, count, item["extension"]),
                "sha256": hashlib.sha256(item["content"]).hexdigest(),
                "content": item["content"],
            }
            for index, item in enumerate(result["files"], 1)
        ]
        # 换格式或份数也属于原件变化；须在写任何文件之前核对整组，不能绕过同名保护。
        if archived_files and [(f["filename"], f["sha256"]) for f in archived_files] != [
            (f["filename"], f["sha256"]) for f in planned
        ]:
            raise ApiError(
                409, "重新下载的文件与已归档原件不同（同名但内容不同、格式或份数变化），未覆盖；请人工核对"
            )
        saved = []
        for item in planned:
            filename, content = item["filename"], item["content"]
            path, name = self.archive.save_file(head, filename, content)
            saved.append({"filename": name, "sha256": hashlib.sha256(content).hexdigest(), "path": path})
        return {"ns_id": result["ns_id"], "files": saved}

    def _fail(self, document_id, message):
        try:
            with transaction(self.engine) as connection:
                declaration_document_dao.failed(connection, document_id, message, _now())
        except SQLAlchemyError:
            # 失败原因只用于展示；不能掩盖原始的下载或共享盘错误。
            pass

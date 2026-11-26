"""异步导入：暂存文件、登记队列、后台解析、原子保存回执与作业结果。"""

import logging
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy.exc import SQLAlchemyError

from backend.core import write_lock
from backend.core.errors import ApiError

from ..dao import customs_import_job_dao as dao
from ..vo.customs_import_vo import CustomsImportJob, CustomsImportJobs
from .customs_receipt_parser import decode, parse_bytes

logger = logging.getLogger(__name__)
LABELS = {
    "pending": "等待后台处理",
    "running": "正在解析与比对",
    "completed": "导入成功",
    "failed": "导入失败",
}


def _now():
    return datetime.now(UTC).replace(tzinfo=None)


def _view(row):
    return CustomsImportJob(
        id=str(row["id"]),
        fileName=row["file_name"],
        status=row["status"],
        statusLabel=LABELS[row["status"]],
        error=row["error_message"] or "",
        result=row["result"],
    )


class CustomsImportService:
    def __init__(self, engine, receipts, upload_root):
        self.engine, self.receipts, self.upload_root = engine, receipts, upload_root

    def _require(self):
        if self.engine is None:
            raise ApiError(503, "业务数据库未配置，未接收导入文件")

    def enqueue(self, body, owner):
        self._require()
        if owner.startswith("service:"):
            raise ApiError(403, "服务身份只读，不能导入海关回执")
        if not body.filename.lower().endswith((".xlsx", ".xls", ".csv")):
            raise ApiError(422, "请选择 .xlsx、.xls 或 .csv 格式的海关回执")
        raw = decode(body.filename, body.content)
        key = uuid4().hex
        path = self.upload_root / key
        try:
            self.upload_root.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
            with self.engine.begin() as connection:
                job_id = dao.enqueue(connection, body.filename, key, owner, _now())
                row = dao.get(connection, job_id)
        except OSError:
            path.unlink(missing_ok=True)
            raise ApiError(503, "导入文件未接收，请检查上传暂存目录后重试") from None
        except SQLAlchemyError:
            # 提交结果未知时保留暂存文件，不能让已经登记的作业失去输入。
            raise ApiError(
                503, "无法确认文件接收结果，请刷新后台导入记录核实，并检查数据库及迁移状态"
            ) from None
        return _view(row)

    def browse(self, owner):
        self._require()
        try:
            with self.engine.connect() as connection:
                return CustomsImportJobs(items=[_view(row) for row in dao.recent(connection, owner)])
        except SQLAlchemyError:
            raise ApiError(503, "导入进度暂时无法查询，请刷新核实，勿重复上传") from None

    def process_next(self):
        """调用方持有消费者命名锁；running 在重启后继续处理，按提交顺序执行。"""
        with self.engine.begin() as connection:
            job = dao.next_pending(connection)
            if not job:
                return
            dao.running(connection, job["id"], _now())
        path = self.upload_root / job["upload_key"]
        try:
            parsed = parse_bytes(job["file_name"], path.read_bytes())
            now = _now()
            # 作业完成与回执保存共用事务；进程中断不会出现“已写入但任务未完成”。
            with write_lock.transaction(self.engine) as connection:
                if dao.get(connection, job["id"])["status"] != "running":
                    return
                result = self.receipts.save_parsed(connection, parsed, job["file_name"], job["actor"], now)
                dao.finish(connection, job["id"], now, result=result.model_dump(mode="json"))
        except SQLAlchemyError:
            # 提交失败保留原文件和 running，下次检查恢复，不把结果未知标成成功或失败。
            raise
        except ApiError as error:
            if error.code in (write_lock.BUSY_CODE, write_lock.CONFLICT_CODE):
                return
            self._fail(job, error.message)
        except OSError:
            self._fail(job, "上传的暂存文件无法读取，请联系管理员检查存储后重新上传")
        except Exception:
            # 后台作业隔离边界：异常必须落入可见失败状态，不泄漏原文件内容。
            logger.exception("海关导入作业 %s 失败", job["id"])
            self._fail(job, "文件处理失败，请联系管理员检查服务日志后重新上传")
        path.unlink(missing_ok=True)

    def _fail(self, job, message):
        with self.engine.begin() as connection:
            dao.finish(connection, job["id"], _now(), error=message)

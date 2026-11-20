"""香港到账独立登记：核对、严格对平提交、银行水单原件绑定与读取。"""

import hashlib

from backend.core.errors import ApiError

from ..dao import batch_dao, hk_slip_dao
from ..policy.hk_receipt_policy import preview
from ..vo.hk_receipt_vo import HkRegistrationCheck
from .bank_slip_file import content_of
from .receivable_service import china_today


class HkReceiptService:
    def __init__(self, engine, candidates, batches, store, *, fee_alert, today=china_today):
        self.engine, self.candidates, self.batches, self.store = (
            engine,
            candidates,
            batches,
            store,
        )
        self.fee_alert, self.today = fee_alert, today

    def preview(self, body):
        if self.engine is None:
            raise ApiError(503, "业务数据库未配置")
        with self.engine.connect() as connection:
            rows = (
                self.candidates.load(connection, numbers=body.declarationNos, limit=None)
                if body.declarationNos
                else []
            )
            accounts = hk_slip_dao.accounts(connection)
        return HkRegistrationCheck(**preview(rows, body, self.fee_alert, accounts, self.today()))

    def register(self, body, owner):
        if owner.startswith("service:"):
            raise ApiError(403, "服务身份只读，不能登记香港回款")
        if self.engine is None:
            raise ApiError(503, "业务数据库未配置")
        with self.engine.connect() as connection:
            existing = batch_dao.by_request(connection, str(body.requestId))
        if existing:
            return self.batches.get(existing["id"])
        saved, values = None, None
        if body.bankSlip:
            content = content_of(body.bankSlip)
            file_id, sha256 = self.store.save(content, "pdf")
            saved = file_id
            values = dict(file_id=file_id, sha256=sha256, file_name=body.bankSlip.fileName)
        try:
            result = self.batches.create(body, owner, require_balance=True, slip=values)
        except Exception:
            if saved:
                self.store.remove(saved, "pdf")
            raise
        if saved:
            with self.engine.connect() as connection:
                attached = hk_slip_dao.get(connection, result.id)
            # 事务已提交后的读取失败不能清理已被引用的原件。
            if not attached or attached["file_id"] != saved:
                self.store.remove(saved, "pdf")
        return result

    def file(self, batch_id):
        if self.engine is None:
            raise ApiError(503, "业务数据库未配置")
        with self.engine.connect() as connection:
            slip = hk_slip_dao.get(connection, batch_id)
        if not slip:
            raise ApiError(404, "本批次没有留存银行水单")
        content = self.store.read(slip["file_id"], "pdf")
        if hashlib.sha256(content).hexdigest() != slip["sha256"]:
            raise ApiError(409, "银行水单原件与登记记录不一致，请核实资料目录")
        return slip["file_name"], content

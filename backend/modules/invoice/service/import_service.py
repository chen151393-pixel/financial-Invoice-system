"""柠檬云 Excel 导入：预览不写数据；确认时重新解析、复核去重并整批原子保存。

- 只导入业务类型为"采购固定资产"的发票；其他类型跳过，不改写原业务类型。
- 同账套同 invoice_key：原始内容相同则跳过；不同视为冲突，整批拒绝，不覆盖已存发票。
- 确认事务中发布 InvoicesImported，matching 订阅后在同一事务中生成比对建议；任何一方失败整批回滚。
"""

import hashlib
import hmac
import secrets
import time
from datetime import datetime, timezone

from sqlalchemy.exc import SQLAlchemyError

from backend.core import named_lock
from backend.core.errors import ApiError

from ..dao import header_dao, item_dao, raw_record_dao
from ..mapper import import_mapper
from ..public import InvoicesImported
from ..vo.import_vo import ImportConfiguration, ImportResult
from .excel_parser import parse_file

BUSINESS_TYPE = "采购固定资产"
MAX_BYTES = 4 * 1024 * 1024
TOKEN_SECONDS = 1800
WARNINGS = [
    "柠檬云 Excel 不含购买方与币种：币种按人民币保存，购买方在比对中记为发票未提供。",
    "仅导入采购固定资产发票；含税金额为筛选后的带符号合计，不代表可抵扣或已比对金额。",
]


class ImportService:
    def __init__(self, engine, events):
        self.engine, self.events = engine, events
        self.secret = secrets.token_bytes(32)

    def configuration(self):
        if self.engine is None:
            return ImportConfiguration(allowed=False, reason="业务数据库未配置", maxBytes=MAX_BYTES)
        return ImportConfiguration(
            allowed=True, reason="可导入柠檬云导出的进项XLS或XLSX文件", maxBytes=MAX_BYTES
        )

    def _signature(self, actor, filename, file_hash, deadline):
        message = f"{actor}\0{filename}\0{file_hash}\0{deadline}".encode()
        return hmac.new(self.secret, message, hashlib.sha256).hexdigest()

    def _verify_token(self, body, actor, file_hash):
        deadline, _, signature = (body.previewToken or "").partition(".")
        expected = self._signature(actor, body.filename, file_hash, deadline)
        if (
            not deadline.isdigit()
            or int(deadline) < time.time()
            or not hmac.compare_digest(signature, expected)
        ):
            raise ApiError(409, "预览已失效或文件发生变化，请重新预览")

    def process(self, body, actor, *, commit=False):
        if commit and actor.startswith("service:"):
            raise ApiError(403, "服务身份只读，不能导入发票")
        if self.engine is None:
            raise ApiError(503, "业务数据库未配置")
        parsed, file_hash = parse_file(body.filename, body.content)
        documents = [doc for doc in parsed if doc["head"]["business_type_name"] == BUSINESS_TYPE]
        if commit:
            self._verify_token(body, actor, file_hash)
            if not documents:
                raise ApiError(422, "文件中没有业务类型为“采购固定资产”的发票，未写入数据")
        prepared = [self._prepare(doc) for doc in documents]
        lock = hashlib.sha256(f"invoice-import:{self.engine.url.database}".encode()).hexdigest()
        try:
            with self.engine.connect() as connection:
                with connection.begin():
                    if not named_lock.acquire(connection, lock):
                        raise ApiError(409, "已有发票导入正在进行，请稍后重新预览")
                try:
                    with connection.begin():
                        existing = header_dao.by_keys(
                            connection, import_mapper.EXCEL_ACCOUNT, [item["key"] for item in prepared]
                        )
                        actions = [self._classify(item, existing.get(item["key"])) for item in prepared]
                        if commit and "conflict" in actions:
                            raise ApiError(409, "发现同票内容冲突，整批未写入，请重新预览并核实")
                        if commit:
                            self._save(connection, prepared, actions)
                finally:
                    try:
                        if connection.in_transaction():
                            connection.rollback()
                        with connection.begin():
                            named_lock.release(connection, lock)
                    except SQLAlchemyError:
                        connection.invalidate()
        except SQLAlchemyError:
            raise ApiError(
                503, "发票数据库操作失败或提交结果不明，请重新预览核实；系统不会覆盖已存发票"
            ) from None
        return self._result(body, actor, file_hash, len(parsed), prepared, actions, commit)

    @staticmethod
    def _prepare(document):
        # 预览即按入库规则校验金额精度与字段长度，确认时不会出现预览未提示的错误。
        import_mapper.header_values(document, None, None)
        import_mapper.item_values(document)
        payload = import_mapper.raw_payload(document)
        head = document["head"]
        return {
            "document": document,
            "key": import_mapper.invoice_key(head.get("invoice_code"), head["invoice_no"]),
            "payload": payload,
            "digest": import_mapper.payload_digest(payload),
        }

    @staticmethod
    def _classify(item, existing):
        if existing is None:
            return "new"
        return "unchanged" if existing["payload_sha256"] == item["digest"] else "conflict"

    def _save(self, connection, prepared, actions):
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        created = []
        for item, action in zip(prepared, actions, strict=True):
            if action != "new":
                continue
            raw_id = raw_record_dao.save(
                connection,
                {
                    "source": import_mapper.EXCEL_SOURCE,
                    "lemon_account": import_mapper.EXCEL_ACCOUNT,
                    "external_id": item["key"],
                    "payload": item["payload"],
                    "payload_sha256": item["digest"],
                },
                now,
            )
            invoice_id = header_dao.insert_header(
                connection, import_mapper.header_values(item["document"], raw_id, now), now
            )
            item_dao.insert_items(connection, invoice_id, import_mapper.item_values(item["document"]), now)
            created.append(invoice_id)
        if created:
            self.events.publish(connection, InvoicesImported(invoice_ids=tuple(created)))

    def _result(self, body, actor, file_hash, source_count, prepared, actions, commit):
        conflict = "conflict" in actions
        deadline = str(int(time.time()) + TOKEN_SECONDS)
        heads = [item["document"]["head"] for item in prepared]
        return ImportResult(
            filename=body.filename,
            invoiceCount=len(prepared),
            sourceInvoiceCount=source_count,
            excludedCount=source_count - len(prepared),
            businessType=BUSINESS_TYPE,
            lineCount=sum(len(item["document"]["lines"]) for item in prepared),
            created=actions.count("new"),
            unchanged=actions.count("unchanged"),
            conflicts=actions.count("conflict"),
            amount=format(sum(head["amount_including_tax"] for head in heads), "f") if heads else "0",
            saved=commit,
            allowed=bool(prepared) and not conflict,
            reason="没有采购固定资产发票，无需导入"
            if not prepared
            else "存在冲突，整批不能导入"
            if conflict
            else "校验通过，可确认导入",
            previewToken=None
            if commit
            else f"{deadline}.{self._signature(actor, body.filename, file_hash, deadline)}",
            message="导入完成，新增发票已提交并生成比对建议，重复记录已跳过"
            if commit
            else "预览完成，尚未写入数据库",
            warnings=WARNINGS,
            rows=[
                {
                    "number": head["invoice_no"],
                    "date": head["invoice_date"].isoformat(),
                    "seller": head["seller_name"],
                    "businessType": head["business_type_name"],
                    "status": head.get("invoice_status_raw") or "未知",
                    "amount": format(head["amount_including_tax"], "f"),
                    "lineCount": len(item["document"]["lines"]),
                    "action": action,
                }
                for item, head, action in zip(prepared, heads, actions, strict=True)
            ],
        )

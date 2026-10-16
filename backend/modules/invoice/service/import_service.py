"""柠檬云 Excel 导入：预览不写数据；确认时重新解析、复核去重并整批原子保存。

- 只导入业务类型为"采购固定资产"的发票；其他类型跳过，不改写原业务类型。
- 同账套同 invoice_key：业务内容相同则跳过；变化追加版本，不覆盖历史；跨来源冲突拒绝。
- 确认事务中发布 InvoicesImported，matching 订阅后在同一事务中生成比对建议；任何一方失败整批回滚。
"""

import hashlib
import hmac
import json
import secrets
import time
from datetime import datetime, timezone

from sqlalchemy.exc import SQLAlchemyError

from backend.core import named_lock, write_lock
from backend.core.errors import ApiError

from ..dao import header_dao, item_dao
from ..mapper import import_mapper
from ..policy.version_policy import digest as business_digest
from ..public import InvoicesImported
from ..vo.import_vo import ImportConfiguration, ImportResult
from .excel_parser import parse_file
from .version_service import save_version

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

    def _signature(self, actor, filename, file_hash, deadline, state_hash):
        message = f"{actor}\0{filename}\0{file_hash}\0{deadline}\0{state_hash}".encode()
        return hmac.new(self.secret, message, hashlib.sha256).hexdigest()

    def _verify_token(self, body, actor, file_hash):
        pieces = (body.previewToken or "").split(".")
        if len(pieces) != 3:
            raise ApiError(409, "预览已失效，请重新预览")
        deadline, state_hash, signature = pieces
        expected = self._signature(actor, body.filename, file_hash, deadline, state_hash)
        if (
            not deadline.isdigit()
            or int(deadline) < time.time()
            or not hmac.compare_digest(signature, expected)
        ):
            raise ApiError(409, "预览已失效或文件发生变化，请重新预览")
        return state_hash

    @staticmethod
    def _state_hash(prepared, existing):
        state = [
            (item["key"], (existing.get(item["key"]) or {}).get("current_version_id")) for item in prepared
        ]
        return hashlib.sha256(json.dumps(state, sort_keys=True).encode()).hexdigest()

    def process(self, body, actor, *, commit=False):
        if commit and actor.startswith("service:"):
            raise ApiError(403, "服务身份只读，不能导入发票")
        if self.engine is None:
            raise ApiError(503, "业务数据库未配置")
        parsed, file_hash = parse_file(body.filename, body.content)
        documents = [doc for doc in parsed if doc["head"]["business_type_name"] == BUSINESS_TYPE]
        expected_state = None
        if commit:
            expected_state = self._verify_token(body, actor, file_hash)
            if not documents:
                raise ApiError(422, "文件中没有业务类型为“采购固定资产”的发票，未写入数据")
        prepared = [self._prepare(doc) for doc in documents]
        lock = hashlib.sha256(f"invoice-import:{self.engine.url.database}".encode()).hexdigest()
        try:
            with write_lock.locked(self.engine) as connection:
                with connection.begin():
                    if not named_lock.acquire(connection, lock):
                        raise ApiError(409, "已有发票导入正在进行，请稍后重新预览")
                try:
                    with connection.begin():
                        existing = header_dao.by_keys(
                            connection, import_mapper.EXCEL_ACCOUNT, [item["key"] for item in prepared]
                        )
                        actions = [
                            self._classify(connection, item, existing.get(item["key"])) for item in prepared
                        ]
                        state_hash = self._state_hash(prepared, existing)
                        if (
                            commit
                            and expected_state != state_hash
                            and any(action != "unchanged" for action in actions)
                        ):
                            raise ApiError(409, "预览后发票版本已变化，请重新预览核实")
                        if commit and "conflict" in actions:
                            raise ApiError(409, "发现同票内容冲突，整批未写入，请重新预览并核实")
                        if commit:
                            self._save(connection, prepared, actions, existing)
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
                503, "发票数据库操作失败或提交结果不明，请重新预览核实；系统保留已有版本与分配占用"
            ) from None
        return self._result(body, actor, file_hash, len(parsed), prepared, actions, commit, state_hash)

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
    def _classify(connection, item, existing):
        if existing is None:
            return "new"
        if existing["source"] != import_mapper.EXCEL_SOURCE:
            return "conflict"
        if existing["payload_sha256"] == item["digest"]:
            return "unchanged"
        old = header_dao.by_ids(connection, [existing["id"]])[0]
        old_items = item_dao.by_invoices(connection, [existing["id"]])
        head = import_mapper.header_values(item["document"], None, None)
        rows = import_mapper.item_values(item["document"])
        return "unchanged" if business_digest(old, old_items) == business_digest(head, rows) else "updated"

    def _save(self, connection, prepared, actions, existing):
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        changed = [
            save_version(connection, item, existing.get(item["key"]), self.events, now)
            for item, action in zip(prepared, actions, strict=True)
            if action in ("new", "updated")
        ]
        if changed:
            self.events.publish(connection, InvoicesImported(invoice_ids=tuple(changed)))

    def _result(self, body, actor, file_hash, source_count, prepared, actions, commit, state_hash):
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
            updated=actions.count("updated"),
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
            else f"{deadline}.{state_hash}.{self._signature(actor, body.filename, file_hash, deadline, state_hash)}",
            message="导入完成，发票及新版本已提交，已确认分配的版本变化需复核，重复记录已跳过"
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

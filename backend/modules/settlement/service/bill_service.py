"""提单用例：上传并解析、人工修改字段、移除、读取文件。

顺序：事务外解码、解析并写文件 → 短事务内重新校验批次状态并登记；登记失败时删除刚写入的文件。
"""

import base64
import binascii
from datetime import UTC, datetime

from sqlalchemy.exc import SQLAlchemyError

from backend.core import write_lock
from backend.core.errors import ApiError

from ..dao import bill_dao
from ..dto.bill_dto import MAX_BILL_BYTES
from ..policy.bill_parse_policy import missing_fields, parse_bill
from .bill_text import extract_text
from .document_service import edit_reason, load


def _now():
    return datetime.now(UTC).replace(tzinfo=None)


def _require_operator(owner):
    if owner.startswith("service:"):
        raise ApiError(403, "服务身份只读，不能修改结汇资料")


def decode(content, limit, label):
    try:
        data = base64.b64decode(content, validate=True)
    except (binascii.Error, ValueError):
        raise ApiError(422, f"{label}内容无法读取，请重新选择文件") from None
    if not data:
        raise ApiError(422, f"{label}是空文件")
    if len(data) > limit:
        raise ApiError(413, f"{label}不能超过 {limit // (1024 * 1024)} MB")
    return data


def _numbers(requested, items):
    """提单对应的报关单须属于本批次；未指定时对应全部。"""
    allowed = [item["declaration_no"] for item in items]
    if not requested:
        return allowed
    unknown = [number for number in requested if number not in allowed]
    if unknown:
        raise ApiError(422, f"以下报关单不在本批次中：{'、'.join(unknown)}")
    return sorted(set(requested), key=allowed.index)


class BillService:
    def __init__(self, engine, store, documents):
        self.engine, self.store, self.documents = engine, store, documents

    def upload(self, batch_id, body, owner):
        _require_operator(owner)
        content = decode(body.content, MAX_BILL_BYTES, "提单")
        if not content.startswith(b"%PDF-"):
            raise ApiError(422, "提单须为 PDF 文件")
        parsed = parse_bill(extract_text(content))
        missing = missing_fields(parsed)
        note = f"未能自动识别：{'、'.join(missing)}，请人工填写" if missing else None
        file_id, sha256 = self.store.save(content, "pdf")
        now = _now()
        try:
            with write_lock.transaction(self.engine, "settlement") as connection:
                batch, items = self._editable(connection, batch_id)
                if any(row["sha256"] == sha256 for row in bill_dao.active(connection, batch_id)):
                    raise ApiError(409, "该提单文件已上传到本批次")
                bill_dao.insert_bill(
                    connection,
                    {
                        "batch_id": batch_id,
                        "file_id": file_id,
                        "file_name": body.fileName,
                        "sha256": sha256,
                        "size_bytes": len(content),
                        "bl_no": parsed["bl_no"] or None,
                        "port_of_loading": parsed["port_of_loading"] or None,
                        "port_of_discharge": parsed["port_of_discharge"] or None,
                        "on_board_date": parsed["on_board_date"],
                        "declaration_nos": _numbers(body.declarationNos, items),
                        "parse_note": note,
                        "uploaded_by": owner,
                        "uploaded_at": now,
                    },
                    now,
                )
                return self.documents.view(connection, batch, items)
        except ApiError:
            self.store.remove(file_id, "pdf")
            raise
        except SQLAlchemyError:
            self.store.remove(file_id, "pdf")
            raise ApiError(503, "提单保存失败，请检查业务数据库及迁移状态") from None

    def update(self, batch_id, bill_id, body, owner):
        """人工确认或修正提单字段及其对应的报关单。"""
        _require_operator(owner)
        with write_lock.transaction(self.engine, "settlement") as connection:
            batch, items = self._editable(connection, batch_id)
            self._active(connection, batch_id, bill_id)
            bill_dao.update_bill(
                connection,
                bill_id,
                {
                    "bl_no": body.blNo or None,
                    "port_of_loading": body.portOfLoading.upper() or None,
                    "port_of_discharge": body.portOfDischarge.upper() or None,
                    "on_board_date": body.onBoardDate,
                    "declaration_nos": _numbers(body.declarationNos, items),
                    "confirmed_by": owner,
                },
                _now(),
            )
            return self.documents.view(connection, batch, items)

    def remove(self, batch_id, bill_id, owner):
        _require_operator(owner)
        now = _now()
        with write_lock.transaction(self.engine, "settlement") as connection:
            batch, items = self._editable(connection, batch_id)
            row = self._active(connection, batch_id, bill_id)
            bill_dao.update_bill(connection, bill_id, {"removed_by": owner, "removed_at": now}, now)
            view = self.documents.view(connection, batch, items)
        self.store.remove(row["file_id"], "pdf")
        return view

    def file(self, batch_id, bill_id):
        """返回 (文件名, PDF 字节)。"""
        with self.engine.connect() as connection:
            row = self._active(connection, batch_id, bill_id)
        return row["file_name"], self.store.read(row["file_id"], "pdf")

    def _editable(self, connection, batch_id):
        batch, items = load(connection, batch_id, lock=True)
        reason = edit_reason(batch)
        if reason:
            raise ApiError(409, reason)
        return batch, items

    def _active(self, connection, batch_id, bill_id):
        row = bill_dao.get(connection, batch_id, bill_id)
        if row is None or row["removed_at"] is not None:
            raise ApiError(404, "提单不存在或已移除")
        return row

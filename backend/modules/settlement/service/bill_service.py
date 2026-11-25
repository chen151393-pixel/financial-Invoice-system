"""提单用例：上传并解析、人工修改字段、移除、读取文件。

顺序：事务外解码、解析（无文字层的扫描件走 OCR）并写文件 → 短事务内重新校验批次状态并登记；登记失败时删除刚写入的文件。
"""

import base64
import binascii
from datetime import UTC, datetime

from sqlalchemy.exc import SQLAlchemyError

from backend.core import write_lock
from backend.core.errors import ApiError

from ..dao import bill_dao
from ..dao.document_scope import values as scope_values
from ..dto.bill_dto import MAX_BILL_BYTES
from ..policy.bill_layout_policy import agreed, parse_words
from ..policy.bill_model_policy import merge
from ..policy.bill_parse_policy import missing_fields, parse_bill, retry_values
from .bill_text import extract_text
from .document_service import edit_reason
from .pdf_file import validate_pdf


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


def _numbers(requested, items, reference=None):
    """提单对应的报关单须属于本批次；未指定时对应全部。"""
    allowed = [item["declaration_no"] for item in items]
    if not requested:
        return allowed
    unknown = [number for number in requested if number not in allowed]
    if unknown:
        label = "本次资料范围" if isinstance(reference, str) else "本批次"
        raise ApiError(422, f"以下报关单不在{label}中：{'、'.join(unknown)}")
    return sorted(set(requested), key=allowed.index)


OCR_NOTE = "扫描件由系统识别，可能有错字，请对照原件核对"
MODEL_NOTE = "部分字段由识别模型给出，可能有误，请对照原件核对"
# 需要人工对照原件的提示；重复上传补空时沿用
CHECK_NOTES = (OCR_NOTE, MODEL_NOTE)


class BillService:
    def __init__(self, engine, store, documents, ocr=None, model=None):
        self.engine, self.store, self.documents, self.ocr = engine, store, documents, ocr
        # 识别模型（可选，SETTLEMENT_BILL_RECOGNIZER）：只在本地规则有字段没识别出来时调用
        self.model = model

    def _parse(self, content):
        """返回 (字段, 说明)。有文字层按文字解析；否则按扫描件识别，多次识别一致的字段才采用。

        本地规则仍缺字段且配置了识别模型时，再请模型补空；两边不一致的字段留空（见 bill_model_policy）。
        """
        text = extract_text(content)
        if text.strip() or self.ocr is None:
            parsed, scanned = parse_bill(text), False
        else:
            readings = self.ocr.readings(content)
            parsed = agreed([parse_words(words) for words in readings]) if readings else parse_bill("")
            scanned = bool(readings)
        ocr_used = scanned and len(missing_fields(parsed)) < 4
        taken, conflicts = [], []
        if self.model is not None and missing_fields(parsed):
            modeled = self.model.read(content, text)
            if modeled is not None:
                parsed, taken, conflicts = merge(parsed, modeled)
        missing = missing_fields(parsed)
        notes = [f"未能自动识别：{'、'.join(missing)}，请人工填写"] if missing else []
        if conflicts:
            notes.append("系统规则与识别模型的结果不一致的字段已留空")
        if ocr_used:
            notes.append(OCR_NOTE)
        if taken:
            notes.append(MODEL_NOTE)
        return parsed, "；".join(notes) or None

    def upload(self, batch_id, body, owner):
        _require_operator(owner)
        content = decode(body.content, MAX_BILL_BYTES, "提单")
        validate_pdf(content, "提单")
        parsed, note = self._parse(content)
        file_id, sha256 = self.store.save(content, "pdf")
        now = _now()
        try:
            with write_lock.transaction(self.engine, "settlement") as connection:
                batch, items = self._editable(connection, batch_id)
                duplicate = next(
                    (row for row in bill_dao.active(connection, batch_id) if row["sha256"] == sha256),
                    None,
                )
                if duplicate:
                    self._retry(connection, duplicate, parsed, note, now)
                else:
                    bill_dao.insert_bill(
                        connection,
                        {
                            **scope_values(batch_id),
                            "file_id": file_id,
                            "file_name": body.fileName,
                            "sha256": sha256,
                            "size_bytes": len(content),
                            "bl_no": parsed["bl_no"] or None,
                            "port_of_loading": parsed["port_of_loading"] or None,
                            "port_of_discharge": parsed["port_of_discharge"] or None,
                            "on_board_date": parsed["on_board_date"],
                            "declaration_nos": _numbers(body.declarationNos, items, batch_id),
                            "parse_note": note,
                            "uploaded_by": owner,
                            "uploaded_at": now,
                        },
                        now,
                    )
                view = self.documents.view(connection, batch, items)
            if duplicate:
                self.store.remove(file_id, "pdf")
            return view
        except ApiError:
            self.store.remove(file_id, "pdf")
            raise
        except SQLAlchemyError:
            self.store.remove(file_id, "pdf")
            raise ApiError(503, "提单保存失败，请检查业务数据库及迁移状态") from None

    def _retry(self, connection, saved, parsed, note, now):
        """复用上传入口重识别旧文件，事务内按最新字段补空，不改变原文件或关联。"""
        values = retry_values(saved, parsed)
        if not values:
            if missing_fields(saved):
                raise ApiError(409, "该提单文件已上传，本次仍未识别出缺失字段，请点击“修改”补填")
            raise ApiError(409, "该提单文件已上传到本次资料")
        missing = missing_fields({**saved, **values})
        notes = [f"未能自动识别：{'、'.join(missing)}，请人工填写"] if missing else []
        for check in CHECK_NOTES:
            if check in (note or "") or check in (saved["parse_note"] or ""):
                notes.append(check)
        bill_dao.update_bill(connection, saved["id"], {**values, "parse_note": "；".join(notes) or None}, now)

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
                    "declaration_nos": _numbers(body.declarationNos, items, batch_id),
                    "confirmed_by": owner,
                    # 人工保存即视为已核对，清除自动解析留下的提示
                    "parse_note": None,
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
            context, _ = self.documents.load(connection, batch_id)
            row = self._active(connection, context["id"], bill_id)
        return row["file_name"], self.store.read(row["file_id"], "pdf")

    def _editable(self, connection, batch_id):
        batch, items = self.documents.load(connection, batch_id, lock=True)
        reason = edit_reason(batch)
        if reason:
            raise ApiError(409, reason)
        return batch, items

    def _active(self, connection, batch_id, bill_id):
        row = bill_dao.get(connection, batch_id, bill_id)
        if row is None or row["removed_at"] is not None:
            raise ApiError(404, "提单不存在或已移除")
        return row

"""发票文件批量上传：按发票号码找到比对通过的子采购单，保存到所属报关单的共享盘文件夹。

- 发票号码取自文件名中的数字串（数电票 20 位、旧版 8 位等），也可人工指定；识别不了或命中多张时不猜测归属；
- 只认已通过且复核有效的分配；作废、红冲或待复核的发票不归档；
- 发票分配到多张报关单时，每个报关单文件夹各存一份「发票_发票号码」；
- 同一发票在同一报关单只保留一份：内容相同视为已上传，内容不同拒绝覆盖；
- 只归档文件，不改变比对、收票进度与任务状态；
- 顺序：事务外读取并写共享盘 → 短事务登记。
"""

import base64
import binascii
import hashlib
import re
from datetime import datetime, timezone
from pathlib import PurePath

from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from backend.core.errors import ApiError
from backend.core.write_lock import transaction
from backend.integrations.contract_archive import document_filename
from backend.modules.invoice.public import invoices_by_number
from backend.modules.source.public import line_declarations

from ..dao import allocation_dao, invoice_file_dao
from ..vo.invoice_file_vo import InvoiceFileItem, InvoiceFileResult

# 文件名中可能是发票号码的数字串长度；开票时间等其他数字串查不到发票，不影响识别
NUMBER = re.compile(r"\d{8,20}")
CANCELLED = {"void": "作废", "red_offset": "红冲"}
MAX_BYTES = 10 * 1024 * 1024
SIGNATURES = ((b"%PDF-", ".pdf"), (b"\xff\xd8\xff", ".jpg"), (b"\x89PNG\r\n\x1a\n", ".png"))


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _read(content):
    """返回 (文件字节, 扩展名, 不能归档的原因)；按文件头识别格式，不信任文件扩展名。"""
    try:
        data = base64.b64decode(content, validate=True)
    except (ValueError, binascii.Error):
        return None, None, "文件内容无法读取，请重新选择文件"
    extension = next((ext for signature, ext in SIGNATURES if data.startswith(signature)), None)
    if extension is None:
        return None, None, "仅支持 PDF、JPG、PNG 格式的发票"
    if len(data) > MAX_BYTES:
        return None, None, "单个文件不能超过 10 MB"
    return data, extension, ""


def _numbers(stem):
    """文件名中独立的 8–20 位数字串（前后不再紧跟数字）。"""
    return [match.group() for match in NUMBER.finditer(stem) if not _inside_longer(stem, match)]


def _inside_longer(text, match):
    before = match.start() > 0 and text[match.start() - 1].isdigit()
    after = match.end() < len(text) and text[match.end()].isdigit()
    return before or after


class InvoiceFileService:
    def __init__(self, engine, directory, archive):
        self.engine, self.directory, self.archive = engine, directory, archive

    def upload(self, body, actor):
        if actor.startswith("service:"):
            raise ApiError(403, "服务身份只读，不能上传发票文件")
        if self.archive is None or self.archive.root is None:
            raise ApiError(503, "合同共享盘路径尚未配置，发票文件未保存")
        return InvoiceFileResult(items=[self._one(item, actor) for item in body.files])

    def _one(self, item, actor):
        result = {"filename": item.filename, "invoiceNumber": item.invoiceNo}
        content, extension, problem = _read(item.content)
        if problem:
            return InvoiceFileItem(**result, status="failed", reason=problem)
        numbers = [item.invoiceNo] if item.invoiceNo else _numbers(PurePath(item.filename).stem)
        try:
            with self.engine.connect() as connection:
                invoices = invoices_by_number(connection, numbers)
                lines = allocation_dao.valid_confirmed_lines(connection, [row["id"] for row in invoices])
                orders = line_declarations(connection, set().union(*lines.values()))
        except SQLAlchemyError:
            raise ApiError(503, "发票或比对记录读取失败，请检查业务数据库") from None
        if not invoices:
            reason = (
                "未找到该发票号码，请确认发票已从柠檬云同步或导入"
                if item.invoiceNo
                else "未能从文件名识别发票号码，请指定发票号码后重新上传"
            )
            return InvoiceFileItem(**result, status="unmatched", reason=reason)
        found = sorted({row["invoice_no"] for row in invoices})
        if len(found) > 1:
            return InvoiceFileItem(
                **result,
                status="ambiguous",
                reason=f"文件名匹配到多张发票：{'、'.join(found)}，请指定发票号码",
            )
        result["invoiceNumber"] = found[0]
        cancelled = [CANCELLED[row["status"]] for row in invoices if row["status"] in CANCELLED]
        if len(cancelled) == len(invoices):
            return InvoiceFileItem(**result, status="not_ready", reason=f"发票已{cancelled[0]}，不归档")
        usable = [row for row in invoices if lines.get(row["id"]) and row["status"] not in CANCELLED]
        if len(usable) > 1:
            return InvoiceFileItem(
                **result,
                status="ambiguous",
                reason="该号码对应多张已比对通过的发票（不同账套或发票代码），请联系管理员核对",
            )
        if not usable:
            return InvoiceFileItem(
                **result,
                status="not_ready",
                reason="该发票尚未比对通过或分配待复核，比对通过后再上传",
            )
        invoice = usable[0]
        targets = [orders[line_id] for line_id in sorted(lines[invoice["id"]]) if line_id in orders]
        unlinked = sorted({o["order_no"] for o in targets if o["customs_declaration_id"] is None})
        heads = self.directory.declarations(
            {o["customs_declaration_id"] for o in targets if o["customs_declaration_id"] is not None}
        )
        if not heads:
            reason = f"子采购单{'、'.join(unlinked)}尚未关联报关单，无法确定归档文件夹"
            return InvoiceFileItem(**result, status="not_ready", reason=reason)
        return self._save(invoice, heads, content, extension, item.filename, actor, result, unlinked)

    def _save(self, invoice, heads, content, extension, original, actor, result, unlinked):
        digest = hashlib.sha256(content).hexdigest()
        try:
            with self.engine.connect() as connection:
                existing = {
                    declaration_id: invoice_file_dao.get(connection, invoice["id"], declaration_id)
                    for declaration_id in heads
                }
        except SQLAlchemyError:
            raise ApiError(503, "发票文件记录读取失败，请检查业务数据库") from None
        paths, conflicts, written = [], [], {}
        for declaration_id, head in sorted(heads.items()):
            row = existing[declaration_id]
            if row:
                if row["sha256"] == digest:
                    paths.append(row["archive_path"])
                else:
                    conflicts.append(head["record_no"])
                continue
            try:
                filename = document_filename("发票", invoice["invoice_no"], extension=extension)
                written[declaration_id] = self.archive.save_file(head, filename, content)
            except ApiError as error:
                return InvoiceFileItem(**result, status="failed", reason=error.message, archivePaths=paths)
        try:
            with transaction(self.engine) as connection:
                now = _now()
                for declaration_id, (path, name) in written.items():
                    row = invoice_file_dao.get(connection, invoice["id"], declaration_id, lock=True)
                    if row:
                        if row["sha256"] != digest:
                            conflicts.append(heads[declaration_id]["record_no"])
                        else:
                            paths.append(row["archive_path"])
                        continue
                    invoice_file_dao.insert_file(
                        connection,
                        {
                            "invoice_id": invoice["id"],
                            "customs_declaration_id": declaration_id,
                            "invoice_no": invoice["invoice_no"],
                            "original_filename": original[:255],
                            "filename": name,
                            "sha256": digest,
                            "archive_path": path,
                            "uploaded_by": actor,
                        },
                        now,
                    )
                    paths.append(path)
        except IntegrityError:
            return InvoiceFileItem(
                **result, status="conflict", reason="该发票文件正在被同时上传，请刷新后核对"
            )
        except SQLAlchemyError:
            raise ApiError(
                503, "文件已保存到共享盘，但记录保存失败；请重新上传，同内容文件不会重复覆盖"
            ) from None
        note = f"；子采购单{'、'.join(unlinked)}尚未关联报关单，未归档" if unlinked else ""
        if conflicts:
            return InvoiceFileItem(
                **result,
                status="conflict",
                reason=f"报关单{'、'.join(sorted(conflicts))}已有该发票的不同文件，未覆盖；如需更换请联系管理员核对{note}",
                archivePaths=paths,
            )
        if not written:
            reason = "已上传过相同文件"
        elif len(paths) > 1:
            reason = f"已保存到 {len(paths)} 个报关单文件夹"
        else:
            reason = "已保存到共享盘"
        return InvoiceFileItem(**result, status="saved", reason=reason + note, archivePaths=paths)

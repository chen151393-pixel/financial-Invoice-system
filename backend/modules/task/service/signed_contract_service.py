"""回签合同批量上传：按文件名识别子采购单号，保存到所属报关单的共享盘文件夹，数据库只记录路径与校验值。

- 回签合同不阻塞通知与收票，只是任务完结的必备资料（2026-10-23 业务确认）；
- 识别不了或匹配多个单号时逐个返回原因，可指定单号后重新上传，不猜测归属；
- 同一子采购单只保留一份：内容相同视为已上传，内容不同拒绝覆盖；
- 顺序：事务外写共享盘 → 短事务登记并重算含该子采购单任务的完结状态。
"""

import base64
import binascii
import hashlib
from datetime import datetime, timezone
from pathlib import PurePath

from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from backend.core.errors import ApiError
from backend.core.write_lock import transaction
from backend.integrations.contract_archive import document_filename

from ..dao import signed_contract_dao, task_dao
from ..vo.signed_contract_vo import SignedUploadItem, SignedUploadResult
from .progress_service import refresh_tasks

MAX_BYTES = 10 * 1024 * 1024
SIGNATURES = ((b"%PDF-", ".pdf"), (b"\xff\xd8\xff", ".jpg"), (b"\x89PNG\r\n\x1a\n", ".png"))


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _extension(content):
    return next((extension for signature, extension in SIGNATURES if content.startswith(signature)), None)


class SignedContractService:
    def __init__(self, engine, directory, archive):
        self.engine, self.directory, self.archive = engine, directory, archive

    def upload(self, body, actor):
        if actor.startswith("service:"):
            raise ApiError(403, "服务身份只读，不能上传回签合同")
        if self.archive is None or self.archive.root is None:
            raise ApiError(503, "合同共享盘路径尚未配置，回签合同未保存")
        return SignedUploadResult(items=[self._one(item, actor) for item in body.files])

    def _one(self, item, actor):
        result = {"filename": item.filename, "orderNumber": item.orderNo}
        try:
            content = base64.b64decode(item.content, validate=True)
        except (ValueError, binascii.Error):
            return SignedUploadItem(**result, status="failed", reason="文件内容无法读取，请重新选择文件")
        extension = _extension(content)
        if extension is None:
            return SignedUploadItem(**result, status="failed", reason="仅支持 PDF、JPG、PNG 格式的回签合同")
        if len(content) > MAX_BYTES:
            return SignedUploadItem(**result, status="failed", reason="单个文件不能超过 10 MB")
        orders = (
            self.directory.orders_by_number(item.orderNo)
            if item.orderNo
            else self._match(PurePath(item.filename).stem)
        )
        if not orders:
            reason = (
                "未找到该子采购单号，请核对后重试"
                if item.orderNo
                else "未能从文件名识别子采购单号，请指定单号后重新上传"
            )
            return SignedUploadItem(**result, status="unmatched", reason=reason)
        if len(orders) > 1:
            numbers = "、".join(sorted(order["order_no"] for order in orders))
            return SignedUploadItem(
                **result, status="ambiguous", reason=f"文件名匹配到多个子采购单：{numbers}，请指定单号"
            )
        order = orders[0]
        result["orderNumber"] = order["order_no"]
        if order["customs_declaration_id"] is None:
            return SignedUploadItem(
                **result, status="unmatched", reason="该子采购单尚未关联报关单，无法确定归档文件夹"
            )
        return self._save(order, content, extension, item.filename, actor, result)

    def _match(self, stem):
        """文件名中出现的子采购单号；一个单号包含另一个时取较长者（如 X-1 与 X-10）。"""
        found = self.directory.orders_in_text(stem)
        return [
            order
            for order in found
            if not any(
                other["order_no"] != order["order_no"] and order["order_no"] in other["order_no"]
                for other in found
            )
        ]

    def _save(self, order, content, extension, original, actor, result):
        digest = hashlib.sha256(content).hexdigest()
        try:
            with self.engine.connect() as connection:
                existing = signed_contract_dao.get(connection, order["id"])
        except SQLAlchemyError:
            raise ApiError(503, "回签合同记录读取失败，请检查业务数据库") from None
        if existing:
            return self._existing(existing, digest, result)
        head = self.directory.declarations([order["customs_declaration_id"]]).get(
            order["customs_declaration_id"]
        )
        if head is None:
            return SignedUploadItem(
                **result, status="unmatched", reason="所属报关单不存在，无法确定归档文件夹"
            )
        try:
            filename = document_filename("回签合同", order["order_no"], extension=extension)
            path, name = self.archive.save_file(head, filename, content)
        except ApiError as error:
            return SignedUploadItem(**result, status="failed", reason=error.message)
        try:
            with transaction(self.engine) as connection:
                existing = signed_contract_dao.get(connection, order["id"], lock=True)
                if existing:
                    return self._existing(existing, digest, result)
                now = _now()
                signed_contract_dao.insert_contract(
                    connection,
                    {
                        "purchase_order_id": order["id"],
                        "customs_declaration_id": order["customs_declaration_id"],
                        "order_no": order["order_no"],
                        "original_filename": original[:255],
                        "filename": name,
                        "sha256": digest,
                        "archive_path": path,
                        "uploaded_by": actor,
                    },
                    now,
                )
                refresh_tasks(
                    connection,
                    task_dao.current_ids_by_orders(connection, [order["id"]]),
                    actor,
                    "回签合同已上传",
                    now,
                )
        except IntegrityError:
            return SignedUploadItem(
                **result, status="conflict", reason="该子采购单的回签合同正在被同时上传，请刷新后核对"
            )
        except SQLAlchemyError:
            raise ApiError(
                503, "文件已保存到共享盘，但记录保存失败；请重新上传，同内容文件不会重复覆盖"
            ) from None
        return SignedUploadItem(**result, status="saved", reason="已保存到共享盘", archivePath=path)

    @staticmethod
    def _existing(existing, digest, result):
        if existing["sha256"] == digest:
            return SignedUploadItem(
                **result, status="saved", reason="已上传过相同文件", archivePath=existing["archive_path"]
            )
        return SignedUploadItem(
            **result,
            status="conflict",
            reason="该子采购单已上传过不同的回签合同，未覆盖；如需更换请联系管理员核对",
            archivePath=existing["archive_path"],
        )

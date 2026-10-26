"""报关资料、回签合同与资料齐全情况的展示转换，不读取数据库。"""

from ..policy.document_policy import DECLARATION_DOCUMENTS, missing_documents
from ..vo.capability import Capability
from ..vo.task_vo import ArchivedFile, DeclarationDocument, SignedContract, TaskCompletion
from .task_mapper import iso

STATUS = {"pending": "待下载", "archived": "已保存到共享盘", "failed": "下载失败"}


def declaration_documents(rows, task, unavailable):
    """rows：{资料类型: 记录}；没有记录（本功能上线前的任务）显示为未登记，可人工下载。"""
    superseded = task["status"] == "superseded"
    result = []
    for doc_type, label in DECLARATION_DOCUMENTS.items():
        row = rows.get(doc_type)
        status = row["status"] if row else "unregistered"
        block = "任务已被新审核版本替代" if superseded else unavailable
        result.append(
            DeclarationDocument(
                type=doc_type,
                label=label,
                status=status,
                statusLabel=STATUS.get(status, "尚未登记下载"),
                files=[
                    ArchivedFile(filename=f["filename"], path=f["path"])
                    for f in (row or {}).get("files") or []
                ],
                error=(row["error_message"] or "") if row and status != "archived" else "",
                attempts=row["attempts"] if row else 0,
                archivedAt=iso(row["archived_at"]) if row else None,
                retry=Capability(
                    allowed=not block,
                    reason=block
                    or (
                        "重新从 NS 下载；内容不同时不覆盖已归档文件"
                        if status == "archived"
                        else "从 NS 下载并保存到共享盘"
                    ),
                ),
            )
        )
    return result


def signed_contracts(order_ids, rows, names):
    result = []
    for order_id in order_ids:
        row = rows.get(order_id)
        result.append(
            SignedContract(
                orderId=str(order_id),
                orderNumber=names["orders"].get(order_id) or "",
                uploaded=row is not None,
                filename=row["filename"] if row else "",
                archivePath=row["archive_path"] if row else None,
                uploadedAt=iso(row["created_at"]) if row else None,
                uploadedBy=row["uploaded_by"] if row else "",
            )
        )
    return result


def completion(order_ids, documents, declaration_rows, signed_rows):
    archived = {int(doc.orderId) for doc in documents if doc.status == "ready"}
    return completion_of(order_ids, archived, declaration_rows, signed_rows)


def completion_of(order_ids, archived, declaration_rows, signed_rows):
    """archived：已归档子采购合同的子采购单 ID 集合；详情页与采购任务台共用同一口径。"""
    missing = missing_documents(order_ids, archived, declaration_rows, signed_rows)
    return TaskCompletion(
        ready=not missing,
        missing=missing,
        reason="资料已全部归档"
        if not missing
        else f"尚缺：{'、'.join(missing)}；发票收齐且资料到齐后任务完结",
    )

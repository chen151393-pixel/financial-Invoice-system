"""冻结通知依据与已校验合同字节，文件操作均在数据库事务之外。"""

import hashlib
import json
from pathlib import Path

from backend.core.errors import ApiError

from ..dao import document_dao, notification_dao, supplier_group_dao, task_dao, task_line_dao
from .basis_guard import reason as basis_reason


def digest(value):
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def evidence_warning(connection, row):
    block = basis_reason(connection, row["task_id"])
    binding = supplier_group_dao.by_supplier(connection, row["snapshot_json"]["supplierId"])
    if not binding or not binding["enabled"] or binding["version"] != row["group_binding_version"]:
        return block or "提交后供应商群绑定已变化；此回执仅证明原快照目标的发送事实，请人工核对"
    return block


def load(connection, task_id, *, lock_binding=False):
    task = task_dao.get(connection, task_id)
    if task is None:
        raise ApiError(404, "开票任务不存在")
    return {
        "task": task,
        "latest": notification_dao.latest(connection, task_id),
        "binding": supplier_group_dao.by_supplier(connection, task["supplier_id"], lock=lock_binding),
        "documents": document_dao.by_task(connection, task_id),
        "lines": task_line_dao.by_tasks(connection, [task_id]),
    }


def snapshot(data, corp_id, group, files):
    task, latest, binding = data["task"], data["latest"], data["binding"]
    return {
        "taskId": task["id"],
        "account": task["ns_account"],
        "supplierId": task["supplier_id"],
        "companyId": task["company_id"],
        "currency": task["currency"],
        "reviewRevision": task["review_revision"],
        "notificationId": latest["id"],
        "revision": latest["version"],
        "message": latest["content"],
        "bindingId": binding["id"],
        "groupRevision": binding["version"],
        "corpId": corp_id,
        "chatId": binding["chat_id"],
        "groupName": group["groupName"],
        "employee": group["employee"],
        "userid": group["userid"],
        "bases": [[row["purchase_line_id"], row["purchase_basis_id"]] for row in data["lines"]],
        "documents": [
            {
                "id": row["id"],
                "orderId": row["purchase_order_id"],
                "status": row["status"],
                "filename": row["filename"],
                "sha256": row["sha256"],
                "path": row["archive_path"],
            }
            for row in data["documents"]
        ],
        "files": files,
    }


def read_files(data, root):
    orders = {row["purchase_order_id"] for row in data["lines"]}
    documents = data["documents"]
    if not orders or orders != {row["purchase_order_id"] for row in documents}:
        raise ApiError(409, "本任务合同不齐全，请先完成归档")
    if not root:
        raise ApiError(409, "合同共享盘路径尚未配置")
    if len(documents) > 9:
        raise ApiError(409, "本次合同超过 9 个附件，不能自动拆分发送，请使用人工流程")
    files, contents = [], []
    try:
        resolved_root = Path(root).resolve(strict=True)
        for row in documents:
            if row["status"] != "archived" or not row["archive_path"]:
                raise ApiError(409, "合同尚未全部归档")
            path = Path(row["archive_path"]).resolve(strict=True)
            if not path.is_relative_to(resolved_root) or not path.is_file():
                raise ApiError(409, "合同路径不在归档目录内或不是文件")
            if not row["filename"] or Path(row["filename"]).name != row["filename"]:
                raise ApiError(409, "合同文件名无效")
            with path.open("rb") as stream:
                content = stream.read(20 * 1024 * 1024 + 1)
            if len(content) <= 5 or len(content) > 20 * 1024 * 1024:
                raise ApiError(409, "合同必须大于 5 字节且不超过 20 MB，不能自动发送")
            if hashlib.sha256(content).hexdigest() != row["sha256"]:
                raise ApiError(409, "合同内容已变化，请核实归档文件")
            files.append({"filename": row["filename"], "sha256": row["sha256"], "size": len(content)})
            contents.append(content)
    except (OSError, RuntimeError):
        raise ApiError(409, "合同文件不存在或不可读，请检查共享盘权限") from None
    return files, contents

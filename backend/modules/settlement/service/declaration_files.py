"""批次内报关单文件的现状与读取：文件由 task 模块从 NS 下载并归档到共享盘，这里只读，不下载、不改归档记录。

报关单文件按原件格式（PDF 或 NS 打印模板的 xls）放入资料包；未归档时只提示，不阻止出资料。
"""

import hashlib
from pathlib import Path

from backend.modules.source.public import declaration_refs_by_number
from backend.modules.task.public import archived_declaration_files

MAX_FILE_BYTES = 20 * 1024 * 1024
STATUS_LABELS = {
    "archived": "已归档",
    "pending": "待下载",
    "failed": "下载失败",
    "unregistered": "未登记下载",
    "not_found": "来源中未找到",
    "ambiguous": "来源中有重号",
}
HINT = "资料包暂不含该报关单；请在“开票跟进”的任务详情中下载报关单后重新打包"


class DeclarationFiles:
    def __init__(self, root):
        self.root = Path(root) if root else None

    def state(self, connection, items):
        """按批次明细顺序返回 [{declaration_no, record_no, status, label, files, note}]。"""
        heads = declaration_refs_by_number(connection, [item["declaration_no"] for item in items])
        ids = {number: group[0]["id"] for number, group in heads.items() if len(group) == 1}
        archived = archived_declaration_files(connection, ids.values())
        result = []
        for item in items:
            number = item["declaration_no"]
            group = heads.get(number, [])
            if len(group) != 1:
                status, files = ("ambiguous" if group else "not_found"), []
            else:
                row = archived.get(ids[number])
                status, files = (row["status"], row["files"]) if row else ("unregistered", [])
            if status == "archived" and not files:
                status = "pending"
            label = STATUS_LABELS.get(status, status)
            result.append(
                {
                    "declaration_no": number,
                    "record_no": item.get("record_no") or "",
                    "status": status,
                    "label": label,
                    "files": files,
                    "note": "" if status == "archived" else f"报关单 {number} 的文件{label}，{HINT}",
                }
            )
        return result

    def read(self, file):
        """读取一个已归档文件并核对校验值；返回 (字节, 空字符串) 或 (None, 未能读取的原因)。"""
        if self.root is None:
            return None, "共享盘路径未配置"
        try:
            root = self.root.resolve(strict=True)
            target = Path(file["path"]).resolve(strict=True)
            if not target.is_relative_to(root) or not target.is_file():
                return None, "归档路径不在共享盘目录内"
            if target.stat().st_size > MAX_FILE_BYTES:
                return None, "文件超过 20 MB"
            content = target.read_bytes()
        except (OSError, KeyError, TypeError, ValueError):
            return None, "共享盘上的文件无法读取"
        if hashlib.sha256(content).hexdigest() != file.get("sha256"):
            return None, "共享盘上的文件与归档记录不一致"
        return content, ""

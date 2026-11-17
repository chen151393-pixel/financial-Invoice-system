"""报关资料归档现状（只读）：供 settlement 经 public 读取已归档的报关单文件路径，不触发下载。"""

from ..dao import declaration_document_dao


def archived_declaration_files(connection, declaration_ids, doc_type="customs_declaration"):
    """返回 {报关单 ID: {status, files}}；status 为 archived / pending / failed，未登记的报关单不出现。

    files：[{filename, sha256, path}]，仅 archived 时有内容。
    """
    rows = declaration_document_dao.by_declarations(connection, sorted(set(declaration_ids)))
    result = {}
    for declaration_id, by_type in rows.items():
        row = by_type.get(doc_type)
        if row is not None:
            archived = row["status"] == "archived"
            result[declaration_id] = {
                "status": row["status"],
                "files": (row["files"] or []) if archived else [],
            }
    return result

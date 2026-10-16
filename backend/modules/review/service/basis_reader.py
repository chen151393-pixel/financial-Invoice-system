"""只读开票依据门面：确认时重新核对来源摘要；不使用任务缓存作为审核依据。"""

from backend.modules.source.public import purchase_lines

from ..dao import purchase_basis_dao


def current_bases(connection, line_ids, *, lock=False):
    sources = purchase_lines(connection, line_ids, lock=lock)
    found = purchase_basis_dao.current(connection, line_ids, lock=lock)
    for line_id, basis in found.items():
        source = sources.get(line_id)
        reason = ""
        if basis["status"] != "active":
            reason = "开票依据待复核，请重新进行财务审核"
        elif not source or not source["active"] or source["digest"] != basis["source_sha256"]:
            reason = "采购来源已变化，请重新审核开票依据"
        source_current = not reason
        if source_current and not basis["currency"]:
            reason = "子采购币种待核实，请在财务审核时补充结算证据"
        basis.update(allowed=not reason, reason=reason, source_current=source_current)
    return found


def basis_versions(connection, ids):
    return purchase_basis_dao.by_ids(connection, ids)

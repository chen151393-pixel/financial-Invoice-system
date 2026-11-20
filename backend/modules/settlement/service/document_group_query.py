"""资料组列表：先筛类型和关键词，默认仅加载当前页资料；进度筛选批量计算。"""

from backend.core.names import normalize_name

from ..dao import document_group_dao as dao
from ..vo.document_group_vo import DocumentGroupList


def _search_text(group, numbers, found):
    parts = [group["group_no"], group["consignee"]]
    for number in numbers:
        row = found.get(number, {})
        parts.extend(
            [number, row.get("record_no", ""), row.get("export_company", ""), *row.get("sales_orders", [])]
        )
    return normalize_name(" ".join(parts))


def query_groups(service, body):
    keyword, consignee = normalize_name(body.keyword), normalize_name(body.consignee)
    start = (body.page - 1) * body.pageSize
    with service.engine.connect() as connection:
        heads = [
            group
            for group in dao.all_groups(connection, body.grouping)
            if not consignee or consignee in normalize_name(group["consignee"])
        ]
        if not heads:
            return DocumentGroupList(items=[], total=0, page=body.page, pageSize=body.pageSize)
        # 无关键词和进度筛选时，先分页再加载成员及当前资料。
        total = len(heads)
        if not keyword and body.status == "all":
            heads = heads[start : start + body.pageSize]
        members = dao.numbers_by_groups(connection, [group["id"] for group in heads])
        rows = service.candidates.load(
            connection, numbers=[number for numbers in members.values() for number in numbers], limit=None
        )
        found = {row["declaration_no"]: row for row in rows}
        if keyword:
            heads = [group for group in heads if keyword in _search_text(group, members[group["id"]], found)]
            total = len(heads)
            if body.status == "all":
                heads = heads[start : start + body.pageSize]
        contexts = {
            group["id"]: service.source.context(group, members[group["id"]], found) for group in heads
        }
        states = service.reader.group_states(connection, contexts)
        result = [
            service._view(connection, group, loaded=contexts[group["id"]], state=states[group["id"]])
            for group in heads
        ]
        if body.status != "all":
            result = [view for view in result if view.status == body.status]
            total = len(result)
            result = result[start : start + body.pageSize]
        return DocumentGroupList(items=result, total=total, page=body.page, pageSize=body.pageSize)

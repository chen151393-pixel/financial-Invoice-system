"""把大集合拆成不重叠的 ID 范围，绕过单次集合查询的页数上限。

NS 列表不保证 ID 排序，不能直接把当前页最大 ID 当作已读游标。
缩小范围后必须从该范围第一页重新读取，范围读完后才能推进下界。
"""

import re

from backend.core.errors import ApiError


def read_cursor_page(ns, record_type, query_params, cursor):
    lower = int(cursor.afterId)
    upper = int(cursor.throughId) if cursor.throughId is not None else None
    offset, limit = cursor.offset, query_params["limit"]
    while True:
        params = _query(query_params, lower, upper, offset)
        data = ns.request("GET", record_type, query_params=params, exact_numbers=True)["data"]
        ids = _validate(data, lower, upper, offset, limit)
        total = data.get("totalResults")
        # 留一页余量；总数缺失时以 ID 区间宽度保证单个查询不会超页。
        oversized = data["hasMore"] and (
            total >= limit * 999 if total is not None else upper is None or upper - lower >= limit * 999
        )
        if offset == 0 and oversized:
            boundary = max(ids)
            if upper is not None:
                boundary = min(boundary, (lower + upper) // 2)
            if boundary <= lower:
                raise ApiError(502, "NS 分页范围无法继续拆分，请核实来源响应")
            upper = boundary
            continue
        if data["hasMore"]:
            if offset + limit >= limit * 1000:
                raise ApiError(502, "NS 查询期间数据范围发生变化，本次未完整拉取，请重新查询")
            following = {
                "afterId": str(lower),
                "throughId": str(upper) if upper is not None else None,
                "offset": offset + limit,
            }
        elif upper is not None:
            following = {"afterId": str(upper), "throughId": None, "offset": 0}
        else:
            following = None
        return data, following


def _query(base, lower, upper, offset):
    conditions = [base["q"]] if base.get("q") else []
    if lower:
        conditions.append(f"id GREATER {lower}")
    if upper is not None:
        conditions.append(f"id LESS_OR_EQUAL {upper}")
    return {
        "limit": base["limit"],
        "offset": offset,
        **({"q": " AND ".join(conditions)} if conditions else {}),
    }


def _validate(data, lower, upper, offset, limit):
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        raise ApiError(502, "NS 列表响应不完整")
    items, more, total = data["items"], data.get("hasMore"), data.get("totalResults")
    if not isinstance(more, bool) or len(items) > limit or (more and len(items) != limit):
        raise ApiError(502, "NS 分页响应无效，未返回不完整结果")
    # 页内短缺、偏移不符或提前结束都可能漏单，不能继续推进范围。
    for field, expected in (("offset", offset), ("count", len(items))):
        if field in data and (type(data[field]) is not int or data[field] != expected):
            raise ApiError(502, "NS 分页位置或条数不一致，本次未完整拉取")
    if total is not None:
        if type(total) is not int or total < offset + len(items):
            raise ApiError(502, "NS 列表总数无效，未返回不完整结果")
        if more != (offset + len(items) < total):
            raise ApiError(502, "NS 分页结束标记与总数不一致，本次未完整拉取")
    ids = []
    for item in items:
        value = str(item.get("id", "")) if isinstance(item, dict) else ""
        if not re.fullmatch(r"[1-9][0-9]{0,39}", value):
            raise ApiError(502, "NS 列表包含无效的内部 ID")
        number = int(value)
        if number <= lower or (upper is not None and number > upper) or number in ids:
            raise ApiError(502, "NS 列表包含范围外或重复的内部 ID")
        ids.append(number)
    return ids

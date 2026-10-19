"""按已发现的记录 ID 批量读取指定字段，保持 REST 引用形状和 Decimal 精度。"""

import re

from backend.core.errors import ApiError

from .relation_sources import read_suiteql_rows

IDENTIFIER = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,99}")


def read_projected_records(ns, record_type, ids, fields):
    """fields 来自服务端字段清单；不接受任意表达式，不在查询失败后逐条重发。"""
    ns.validate(record_type)
    if (
        not record_type.startswith("customrecord_")
        or not isinstance(ids, list)
        or not 1 <= len(ids) <= 300
        or any(not isinstance(value, str) or not re.fullmatch(r"[1-9][0-9]{0,19}", value) for value in ids)
        or len(set(ids)) != len(ids)
        or not isinstance(fields, dict)
        or not 1 <= len(fields) <= 80
        or any(
            not isinstance(field, str) or not IDENTIFIER.fullmatch(field) or type(reference) is not bool
            for field, reference in fields.items()
        )
        or "id" in fields
    ):
        raise ApiError(422, "NS 批量字段读取范围无效")
    columns = ["id"]
    for index, (field, reference) in enumerate(fields.items()):
        columns.append(f"{field} AS f{index}")
        if reference:
            columns.append(f"CASE WHEN {field} IS NOT NULL THEN BUILTIN.DF({field}) END AS t{index}")
    query = f"SELECT {','.join(columns)} FROM {record_type} WHERE id IN ({','.join(ids)}) ORDER BY id"
    rows = read_suiteql_rows(ns, query)
    if {str(row["id"]) for row in rows} != set(ids) or len(rows) != len(ids):
        raise ApiError(502, "NS 批量明细返回范围缺失或不一致，未保存")
    return {str(row["id"]): project(row, fields) for row in rows}


def project(row, fields):
    record = {"id": str(row["id"])}
    for index, (field, reference) in enumerate(fields.items()):
        # SuiteQL 与 REST 都可能省略空字段；保持缺字段语义，让原映射规则处理可选项或拒绝保存。
        value = row.get(f"f{index}")
        if value is None and field != "isInactive":
            continue
        if reference and value is not None:
            value = {"id": str(value), "refName": row.get(f"t{index}") or ""}
        if field == "isInactive":
            if type(value) is not bool and (not isinstance(value, str) or value not in ("T", "F")):
                raise ApiError(502, "NS 明细有效状态缺失或无效，未保存")
            value = value in ("T", True)
        record[field] = value
    return record

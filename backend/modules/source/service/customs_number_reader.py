"""按真实报关单号读取 NS 报关单及报关行（review 海关回执比对经 public 使用）。

只返回报关口径：报关品名、规格、报关数量、报关单位（按单位字典显示名称）；不判断是否一致。
"""

from ..dao import customs_declaration_dao, unit_dictionary_dao
from ..policy.unit_policy import unit_label

# 单次 IN 查询的单号数量上限，避免超长 SQL
_CHUNK = 500


def declarations_by_number(connection, numbers):
    """返回 {真实报关单号: [报关单, ...]}；未找到的单号不出现在结果中。"""
    wanted = sorted({str(number).strip() for number in numbers if str(number or "").strip()})
    heads = []
    for start in range(0, len(wanted), _CHUNK):
        heads.extend(customs_declaration_dao.active_by_numbers(connection, wanted[start : start + _CHUNK]))
    if not heads:
        return {}
    names = unit_dictionary_dao.unit_names(connection)
    result = {}
    for head in heads:
        lines = [
            {
                "id": line["id"],
                "line_no": line["line_no"] or "",
                "item_code": line["item_code"] or "",
                "name": line["declaration_name"] or "",
                "specification": line["specification"] or "",
                "quantity": line["declared_quantity"],
                "unit": unit_label(line["declared_unit"], names).strip(),
            }
            for line in customs_declaration_dao.lines(connection, head["id"])
        ]
        result.setdefault(head["declaration_no"], []).append(
            {
                "id": head["id"],
                "record_no": head["record_no"] or "",
                "declaration_date": head["declaration_date"],
                "lines": lines,
            }
        )
    return result

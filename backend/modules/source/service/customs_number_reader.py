"""按真实报关单号读取 NS 报关单及报关行（review 海关回执比对经 public 使用）。

只返回报关口径：报关品名、规格、数量、单位、行金额及币种。
"""

from ..dao import customs_declaration_dao, unit_dictionary_dao
from ..policy.currency_policy import currency_code
from ..policy.unit_policy import unit_label

# 单次 IN 查询的单号数量上限，避免超长 SQL
_CHUNK = 500


def declaration_refs_by_number(connection, numbers):
    """批量读取有效报关单头，保留重号与当前来源摘要。"""
    wanted = sorted({str(number).strip() for number in numbers if str(number or "").strip()})
    result = {}
    for start in range(0, len(wanted), _CHUNK):
        for head in customs_declaration_dao.active_by_numbers(connection, wanted[start : start + _CHUNK]):
            result.setdefault(head["declaration_no"], []).append(head)
    return result


def declarations_by_number(connection, numbers):
    """返回 {真实报关单号: [报关单, ...]}；未找到的单号不出现在结果中。"""
    refs = declaration_refs_by_number(connection, numbers)
    if not refs:
        return {}
    names = unit_dictionary_dao.unit_names(connection)
    result = {}
    for head in (head for group in refs.values() for head in group):
        lines = [
            {
                "id": line["id"],
                "line_no": line["line_no"] or "",
                "item_code": line["item_code"] or "",
                "name": line["declaration_name"] or "",
                "specification": line["specification"] or "",
                "quantity": line["declared_quantity"],
                "unit": unit_label(line["declared_unit"], names).strip(),
                "amount": line["amount"],
                "currency": currency_code({"currencyname": line["currency"]}) or line["currency"] or "",
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

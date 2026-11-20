"""销售合同生成规则（纯函数）：按出口合同号把批次内海关回执明细组成合同，并给出不能生成的原因。

金额只取海关回执成交总价，单价 = 成交总价 ÷ 成交数量（四位小数，仅展示）；
签订日期 = 该合同下最早出口日期往前推 lead_days 天；装运口岸、目的口岸取自对应提单。
"""

import hashlib
import json
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from backend.core.names import normalize_name

from .amount_policy import money

UNIT_PRICE_STEP = Decimal("0.0001")


def unit_price(total, quantity):
    if not quantity:
        return None
    return (Decimal(total) / Decimal(quantity)).quantize(UNIT_PRICE_STEP, rounding=ROUND_HALF_UP)


def _ports(bills, numbers):
    """覆盖这些报关单的提单口岸；返回 (装运口岸, 目的口岸, 最早装船日期, 问题)。"""
    covering = [bill for bill in bills if set(bill["declaration_nos"] or []) & set(numbers)]
    ready = [bill for bill in covering if bill["port_of_loading"] and bill["port_of_discharge"]]
    if not ready:
        return "", "", None, "缺少已填写装运口岸和目的口岸的提单"
    destinations = {normalize_name(bill["port_of_discharge"]) for bill in ready}
    loadings = {normalize_name(bill["port_of_loading"]) for bill in ready}
    if len(destinations) > 1 or len(loadings) > 1:
        return "", "", None, "对应的多张提单口岸不一致，请核对提单或拆分批次"
    dates = [bill["on_board_date"] for bill in ready if bill["on_board_date"]]
    return ready[0]["port_of_loading"], ready[0]["port_of_discharge"], min(dates, default=None), ""


def contract_label(contract):
    suffix = f"（{contract['seller_name']}）" if contract.get("seller_name") else ""
    return contract["contract_no"] + suffix


def document_key(contract):
    """旧单票与香港按合同号；资料组按申报抬头与合同号区分。"""
    return contract.get("document_key") or contract["contract_no"]


def plan(batch, items, lines_by_declaration, bills, *, lead_days):
    """返回 (合同列表, 问题列表)。合同按合同号排序，每份含明细、金额、日期与口岸。"""
    issues, groups = [], {}
    for item in items:
        number = item["declaration_no"]
        lines = lines_by_declaration.get(number) or []
        if not lines:
            issues.append(f"报关单 {number} 没有可用的海关回执明细")
            continue
        for line in lines:
            contract_no = (line["contract_no"] or "").strip()
            if not contract_no:
                issues.append(f"报关单 {number} 第 {line['item_no']} 项缺少出口合同号")
            elif line["total"] is None or (line["currency"] or "").strip().upper() != batch["currency"]:
                issues.append(f"报关单 {number} 第 {line['item_no']} 项成交总价或币制与批次不符")
            else:
                key = contract_no
                if batch.get("document_group_id"):
                    seller = normalize_name(item.get("export_company", ""))
                    key = (contract_no, seller)
                group = groups.setdefault(
                    key, {"numbers": set(), "lines": [], "dates": [], "contract_no": contract_no}
                )
                group["numbers"].add(number)
                group["lines"].append(line)
                if item["export_date"]:
                    group["dates"].append(item["export_date"])
    contracts = []
    for key in sorted(groups):
        group = groups[key]
        contract_no = group["contract_no"]
        seller_name = (
            next(
                (
                    item.get("export_company", "")
                    for item in items
                    if item["declaration_no"] in group["numbers"]
                ),
                "",
            )
            if batch.get("document_group_id")
            else ""
        )
        label = contract_no + (f"（{seller_name}）" if seller_name else "")
        numbers = sorted(group["numbers"])
        loading, destination, on_board, port_issue = _ports(bills, numbers)
        if port_issue:
            issues.append(f"销售合同 {label}：{port_issue}")
        if not group["dates"]:
            issues.append(f"销售合同 {label}：报关单缺少出口日期，无法确定签订日期")
        contracts.append(
            {
                "contract_no": contract_no,
                **({"seller_name": seller_name} if batch.get("document_group_id") else {}),
                **(
                    {"document_key": hashlib.sha256(json.dumps(key, ensure_ascii=False).encode()).hexdigest()}
                    if batch.get("document_group_id")
                    else {}
                ),
                "declaration_nos": numbers,
                "contract_date": min(group["dates"]) - timedelta(days=lead_days) if group["dates"] else None,
                "port_of_loading": loading,
                "port_of_destination": destination,
                "on_board_date": on_board,
                "amount": sum((Decimal(line["total"]) for line in group["lines"]), Decimal(0)),
                "lines": [
                    {
                        "seq": index,
                        "name": line["name"],
                        "specification": line["specification"] or "",
                        "quantity": Decimal(line["quantity"]),
                        "unit": line["unit"],
                        "unit_price": unit_price(line["total"], line["quantity"]),
                        "amount": Decimal(line["total"]),
                    }
                    for index, line in enumerate(group["lines"], start=1)
                ],
            }
        )
    total = sum((contract["amount"] for contract in contracts), Decimal(0))
    if not issues and money(total) != money(batch["declared_total"]):
        if batch.get("document_kind") == "direct":
            return contracts, ["海关回执当前明细合计与报关应收不一致，请核对回执后重新生成"]
        issues.append(
            f"海关回执当前成交总价合计 {money(total)} 与建批次时的报关合计 {money(batch['declared_total'])} "
            "不一致（回执已更新），请作废批次后重新建批次"
        )
    return contracts, issues


def _party_facts(party):
    fields = ("name_cn", "name_en", "address_cn", "address_en", "phone", "stamp_sha256")
    return {field: party.get(field) or "" for field in fields}


def digest(contract, buyer, seller, terms):
    """合同输入内容摘要：明细、日期、口岸、双方抬头与印章、条款任一变化即不同。"""
    payload = {
        "contract": {
            **{key: str(value) for key, value in contract.items() if key != "lines"},
            "lines": [{key: str(value) for key, value in line.items()} for line in contract["lines"]],
        },
        "buyer": _party_facts(buyer),
        "seller": _party_facts(seller),
        "terms": terms,
    }
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(text.encode()).hexdigest()

"""合同双方取当前关联报关单：买方为境外收货人，卖方为唯一 NS 报关申报抬头。"""

from backend.core.names import normalize_name
from backend.modules.review.public import settlement_declarations
from backend.modules.source.public import declarant_names_by_number, declaration_refs_by_number

from ..dao import party_dao


def _unique(names):
    return {normalize_name(name): name for name in names if normalize_name(name)}


def resolve(connection, items, planned):
    numbers = [item["declaration_no"] for item in items]
    receipts = {
        row["declaration_no"]: row for row in settlement_declarations(connection, numbers=numbers, limit=None)
    }
    refs = declaration_refs_by_number(connection, numbers)
    declarants = declarant_names_by_number(connection, numbers)
    parties = {row["name_key"]: row for row in party_dao.all_parties(connection)}
    bindings, issues = {}, []
    for contract in planned:
        linked = contract["declaration_nos"]
        buyers = _unique([receipts[number]["consignee"] for number in linked if number in receipts])
        sellers = _unique([declarants.get(number, "") for number in linked])
        missing_buyers = [number for number in linked if not receipts.get(number, {}).get("consignee")]
        missing_sellers = [
            number for number in linked if len(refs.get(number, [])) != 1 or not declarants.get(number)
        ]
        prefix = f"销售合同 {contract['contract_no']}："
        problems = []
        if missing_buyers:
            problems.append("报关单缺少当前境外收货人：" + "、".join(missing_buyers))
        elif len(buyers) != 1:
            problems.append("关联报关单的境外收货人不一致，请拆分资料范围或核对回执")
        if missing_sellers:
            problems.append("NS 报关单申报抬头缺失或报关单重号：" + "、".join(missing_sellers))
        elif len(sellers) != 1:
            problems.append("关联 NS 报关单的申报抬头不一致，请拆分资料范围或核对来源")
        buyer_key = next(iter(buyers)) if len(buyers) == 1 and not missing_buyers else None
        seller_key = next(iter(sellers)) if len(sellers) == 1 and not missing_sellers else None
        buyer = parties.get(buyer_key)
        seller = parties.get(seller_key)
        if buyer_key and buyer is None:
            problems.append(f"未维护买方合同抬头：{buyers[buyer_key]}，请在合同抬头中补齐")
        if seller_key and seller is None:
            problems.append(f"未维护卖方合同抬头：{sellers[seller_key]}，须与 NS 申报抬头一致")
        if buyer and seller and buyer["id"] == seller["id"]:
            problems.append("买卖方不能相同，请核对境外收货人与 NS 申报抬头")
        messages = [prefix + problem for problem in problems]
        bindings[contract["contract_no"]] = {
            "buyer": buyer,
            "seller": seller,
            "buyer_name": "、".join(buyers.values()),
            "seller_name": "、".join(sellers.values()),
            "issues": messages,
        }
        issues.extend(messages)
    return bindings, issues

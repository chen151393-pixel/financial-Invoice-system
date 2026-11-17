"""结汇资料齐全度（纯函数）：提单覆盖每张报关单且字段完整，每个出口合同号都有当前有效的销售合同。

销售合同即形式发票，由平台按报关单（海关回执）生成。报关单文件取自 NS 报关资料归档，
未归档只作提示、不计入缺项（见 service/declaration_files.py）。
"""

from .bill_parse_policy import missing_fields
from .contract_policy import digest


def checklist(items, bills, planned, plan_issues, contract_rows, parties, buyer):
    """返回 {issues, warnings, stale}；issues 非空时不能确认资料已出、不能打包。"""
    issues, warnings = [], []
    covered = {number for bill in bills for number in bill["declaration_nos"] or []}
    for item in items:
        if item["declaration_no"] not in covered:
            issues.append(f"报关单 {item['declaration_no']} 缺提单")
    for bill in bills:
        missing = missing_fields(bill)
        if missing:
            issues.append(f"提单 {bill['bl_no'] or bill['file_name']} 待补：{'、'.join(missing)}")
    issues.extend(plan_issues)
    if buyer is None:
        issues.append("未维护买方合同抬头（名称须与境外收货人一致），请先在“合同抬头”中添加")
    rows = {row["contract_no"]: row for row in contract_rows}
    stale = set()
    for contract in planned:
        row = rows.get(contract["contract_no"])
        if row is None:
            issues.append(f"销售合同 {contract['contract_no']} 尚未生成")
            continue
        seller = parties.get(row["seller_party_id"])
        terms = contract_terms(row)
        current = buyer is not None and seller is not None and not plan_issues
        if not current or digest(contract, buyer, seller, terms) != row["source_digest"]:
            stale.add(row["contract_no"])
            issues.append(f"销售合同 {row['contract_no']} 的生成依据已变化，需重新生成")
        elif row["stamp_note"]:
            warnings.append(f"销售合同 {row['contract_no']}：{row['stamp_note']}")
    for contract_no in rows.keys() - {contract["contract_no"] for contract in planned}:
        stale.add(contract_no)
        issues.append(f"销售合同 {contract_no} 已不在批次的出口合同号中，需重新生成")
    return {"issues": issues, "warnings": warnings, "stale": stale}


def contract_terms(row):
    return {
        "trade_term": row["trade_term"],
        "payment_terms_cn": row["payment_terms_cn"],
        "payment_terms_en": row["payment_terms_en"],
    }

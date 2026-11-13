"""海关回执数据行 → 页面 VO 的纯转换；比对结论取自保存的比对结果，不在此重算。"""

from datetime import UTC
from decimal import Decimal

from ..policy.customs_match_policy import CONSISTENT, STATUS_LABELS, text
from ..vo.customs_receipt_vo import CompareGroup, Consignee, CustomsItem, CustomsReceipt, NsLine


def _amount(value):
    return "" if value is None else format(Decimal(value).quantize(Decimal("0.01")), "f")


def _iso(value):
    return value.replace(tzinfo=UTC).isoformat() if value else ""


def item(row):
    return CustomsItem(
        itemNo=row["item_no"],
        hsCode=row["hs_code"] or "",
        name=row["name"],
        specification=row["specification"] or "",
        contractNo=row["contract_no"] or "",
        taxType=row["tax_type"] or "",
        checkStatus=row["check_status"] or "",
        quantity=text(row["deal_quantity"]),
        unit=row["deal_unit"],
        currency=row["currency"] or "",
        total=_amount(row["deal_total"]),
        usdFob=_amount(row["usd_fob"]),
        legalQuantity=text(row["legal_quantity"]),
        legalUnit=row["legal_unit"] or "",
        customsDoc=row["customs_doc"] or "",
        usageFlag=row["usage_flag"] or "",
    )


def consignee(head, ns_record_no=""):
    value = head["consignee"] or ""
    if not value:
        return Consignee(value="", state="empty", label="回执未提供", note="海关回执该列为空")
    if head["ns_declaration_id"]:
        note = f"已随 NS 报关单 {ns_record_no} 保存" if ns_record_no else "已随 NS 报关单保存"
        return Consignee(value=value, state="saved", label="已保存", note=note)
    return Consignee(
        value=value, state="pending", label="待关联", note="保留在回执中，匹配到 NS 报关单后关联"
    )


def _joined(rows, key):
    return "、".join(dict.fromkeys(row[key] for row in rows if row[key]))


def receipt(head, rows, approval):
    result = head["match_result"] or {}
    items = {row["item_no"]: item(row) for row in rows}
    groups = [
        CompareGroup(
            status=group["status"],
            label=group["label"],
            note=group["note"],
            consistent=group["status"] in CONSISTENT,
            nsLines=[NsLine(**line) for line in group["nsLines"]],
            items=[items[number] for number in group["items"] if number in items],
        )
        for group in result.get("groups", [])
    ]
    # 未找到 NS 报关单时没有分组，仍逐项展示海关明细
    if not groups:
        groups = [
            CompareGroup(
                status="missing_in_ns",
                label="NS 无对应行",
                note="无可对应的 NS 报关单",
                consistent=False,
                nsLines=[],
                items=list(items.values()),
            )
        ]
    ns_record_no = result.get("nsRecordNo", "")
    status = head["match_status"]
    return CustomsReceipt(
        id=head["id"],
        declarationNo=head["declaration_no"],
        exportDate=head["export_date"].isoformat() if head["export_date"] else "",
        taxType=_joined(rows, "tax_type"),
        customsDoc=_joined(rows, "customs_doc"),
        usageFlag=_joined(rows, "usage_flag"),
        itemCount=len(rows),
        nsLineCount=result.get("nsLineCount"),
        nsRecordNo=ns_record_no,
        consignee=consignee(head, ns_record_no),
        status=status,
        statusLabel=STATUS_LABELS[status],
        statusNote=_status_note(status, result, groups),
        matchedAt=_iso(head["matched_at"]),
        importedAt=_iso(head["imported_at"]),
        fileName=head["file_name"],
        revision=head["revision"],
        groups=groups,
        approval=approval,
    )


def _status_note(status, result, groups):
    if status in {"ns_missing", "ns_duplicate"}:
        return result.get("note", "")
    if status == "matched":
        return "品名、单位、数量均一致"
    if status == "split_matched":
        return "；".join(g.note for g in groups if g.status in {"split", "merged"})
    return "；".join(dict.fromkeys(g.label for g in groups if not g.consistent))

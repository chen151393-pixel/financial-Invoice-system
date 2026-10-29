"""整票就绪规则：金额、数量和有效审核版本都完整，才允许形成回写任务。"""

import hashlib
import json
import re
from decimal import Decimal, localcontext

from backend.modules.source.public import unit_label

from .approval_version import effective_basis, effective_invoice
from .comparison_policy import same_unit


def canonical(value):
    if isinstance(value, Decimal):
        return format(value, "f")
    if hasattr(value, "isoformat"):
        return value.isoformat()
    raise TypeError(type(value).__name__)


def assess(invoice, allocations, bases, contexts, units):
    if not invoice:
        return {"ready": False, "reason": "发票不存在"}
    active = [item for item in invoice["items"] if item["is_active"]]
    confirmed = [row for row in allocations if row["status"] == "confirmed"]
    reason = _reason(invoice, active, allocations, confirmed, bases, contexts, units)
    if reason:
        return {"ready": False, "reason": reason}
    snapshot = {
        "invoice": invoice,
        "allocations": confirmed,
        "sources": {str(row["purchase_line_id"]): contexts[row["purchase_line_id"]] for row in confirmed},
        "basisIds": {str(row["purchase_line_id"]): effective_basis(row) for row in confirmed},
    }
    encoded = json.dumps(snapshot, sort_keys=True, ensure_ascii=False, default=canonical)
    return {
        "ready": True,
        "reason": "整票已完整审核",
        "snapshot": json.loads(encoded),
        "fingerprint": hashlib.sha256(encoded.encode()).hexdigest(),
    }


def _reason(invoice, items, allocations, confirmed, bases, contexts, units):
    if invoice["status"] != "normal" or invoice["currency"] != "CNY":
        return "首期只接收正常人民币发票"
    # 2026-10-28 确认：采购税额为 0 也须登记，零税额发票照常回写；税额缺失或为负仍须核实。
    if invoice.get("tax_amount") is None or invoice["tax_amount"] < 0:
        return "税额不明或为负，须专项核实"
    if invoice["detail_status"] != "complete" or not invoice["current_version_id"] or not items:
        return "发票明细或版本尚不完整"
    if not invoice["invoice_no"] or not invoice["invoice_date"]:
        return "发票号码或开票日期缺失"
    total = invoice["amount_including_tax"]
    if (
        total is None
        or total <= 0
        or any(item["amount_including_tax"] is None or item["amount_including_tax"] <= 0 for item in items)
    ):
        return "发票金额或明细金额无效，折扣及负行须另行核实"
    if sum((item["amount_including_tax"] for item in items), Decimal(0)) != total:
        return "发票票头与明细金额不一致"
    if any(row["status"] == "proposed" for row in allocations):
        return "仍有待审核分配"
    if {row["invoice_item_id"] for row in confirmed} - {item["id"] for item in items}:
        return "已审核分配包含失效发票行"
    for item in items:
        rows = [row for row in confirmed if row["invoice_item_id"] == item["id"]]
        if sum((row["amount"] for row in rows), Decimal(0)) != item["amount_including_tax"]:
            return "发票每一行的含税金额必须全部分配并审核通过"
        if (
            item["quantity"] is not None
            and sum((row["quantity"] for row in rows), Decimal(0)) != item["quantity"]
        ):
            return "发票每一行的数量必须完整分配"
    for row in confirmed:
        basis, source = bases.get(row["purchase_line_id"]), contexts.get(row["purchase_line_id"])
        if (
            row["verification_status"] != "valid"
            or row["verification_issues"]
            or effective_invoice(row) != invoice["current_version_id"]
        ):
            return "分配尚待复核或发票版本已变化"
        if not basis or not basis["allowed"] or basis["id"] != effective_basis(row):
            return "开票依据已变化或尚待审核"
        if row["amount"] <= 0 or row["amount"] != row["amount"].quantize(Decimal("0.01")):
            return "分配金额必须为正数且精确到分，不能自动舍入"
        if (
            row["purchase_quantity"] is None
            or not row["conversion_numerator"]
            or not row["conversion_denominator"]
        ):
            return "缺少有效的数量换算证据"
        item = next(item for item in items if item["id"] == row["invoice_item_id"])
        if row["quantity"] <= 0 or row["conversion_numerator"] <= 0 or row["conversion_denominator"] <= 0:
            return "数量与换算比例必须为正数"
        with localcontext() as ctx:
            ctx.prec = 64
            if (
                row["quantity"] * row["conversion_numerator"] / row["conversion_denominator"]
                != row["purchase_quantity"]
            ):
                return "数量换算结果与审核记录不一致"
        if (
            row["invoice_unit"] != item["unit"]
            or row["purchase_unit"] != basis["unit"]
            or basis["currency"] != "CNY"
        ):
            return "单位或币种与当前开票依据不一致"
        if same_unit(item["unit"], unit_label(basis["unit"], units)):
            if (row["conversion_numerator"], row["conversion_denominator"]) != (Decimal(1), Decimal(1)):
                return "相同单位的换算比例必须为一"
        elif not (row["conversion_evidence"] or {}).get("reference"):
            return "不同单位缺少换算证据"
        if not source or not all(
            source[k]
            for k in ("line_active", "order_active", "parent_active", "vendor_active", "company_active")
        ):
            return "采购来源或主体已失效"
        if (
            source["parent_relation_status"] != "linked"
            or source["parent_supplier_id"] != source["supplier_id"]
        ):
            return "母采购或供应商关系尚待核实"
        if any(
            not re.fullmatch(r"[1-9][0-9]{0,19}", str(source[k] or ""))
            for k in ("vendor_id", "parent_id", "subpo_id", "currency_id")
        ):
            return "缺少明确的 NS 供应商、母采购或币种内部 ID"
        if (
            len({source[k] for k in ("ns_account", "parent_account", "vendor_account", "company_account")})
            != 1
        ):
            return "来源身份跨 NS 账套"
        if (
            not invoice["seller_name_normalized"]
            or invoice["seller_name_normalized"] != source["vendor_name_normalized"]
        ):
            return "票面销售方与 NS 供应商身份待核实"
        # 导入文件可能缺少购买方；缺失不单独阻断，有名称时仍须与采购公司一致。
        if (
            invoice["buyer_name_normalized"]
            and invoice["buyer_name_normalized"] != source["company_name_normalized"]
        ):
            return "票面购买方与采购公司身份待核实"
    if len({(s["ns_account"], s["vendor_id"], s["company_id"]) for s in contexts.values()}) != 1:
        return "整张发票须属于同一 NS 账套、供应商和采购公司"
    if len({s["parent_id"] for s in contexts.values()}) > 20:
        return "整张发票涉及母采购超过 20 张，需专项处理"
    return ""

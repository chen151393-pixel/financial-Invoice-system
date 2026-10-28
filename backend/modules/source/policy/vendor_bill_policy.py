"""查询结果一致性与展示规则；查询唯一不等于允许自动回写。"""

from datetime import datetime
from decimal import Decimal

from .currency_policy import currency_code

REASONS = {
    "OK": "查询完成，请按母采购核对账单及问题提示；本次查询不允许回写",
    "VENDOR_NOT_FOUND": "未找到有效供应商，请核对 NS 供应商 ID、所属账套及当前身份可见范围",
    "PO_NOT_FOUND": "未找到母采购单，请核对 NS 内部 ID 及当前身份可见范围",
    "VENDOR_MISMATCH": "母采购单供应商与指定供应商不一致，未查询账单",
    "NO_BILLS": "当前身份可见范围内，该母采购单尚未查询到账单",
    "FOUND": "已找到候选账单，仍需核实发票归属及分配金额",
}

WARNINGS = [
    "按母采购内部 ID 返回全部可见账单，不按日期、税额或可收金额过滤",
    "金额与有效明细合计来自本次读取，不是跨表原子快照；非人民币金额口径仍待核实",
    "按母采购找到的账单不代表子采购精确归属；查询不占用额度，也不是审核或回写凭据",
]


def validate_result(result, criteria, account):
    if result.account.lower().replace("_", "-") != account.lower().replace("_", "-"):
        raise ValueError("账套不一致")
    if result.query != criteria:
        raise ValueError("查询条件不一致")
    times = [
        datetime.fromisoformat(t.replace("Z", "+00:00"))
        for t in (result.readStartedAt, result.readCompletedAt)
    ]
    if any(t.utcoffset() is None for t in times) or times[1] < times[0]:
        raise ValueError("读取时间无效")
    if result.status == "VENDOR_NOT_FOUND":
        if result.vendor is not None or result.purchaseOrders:
            raise ValueError("未确认供应商就返回母采购")
        return
    if result.vendor is None or result.vendor.id != criteria.vendorId:
        raise ValueError("NS 供应商 ID 不一致")
    # 必须按请求顺序完整返回，缺单、重复、额外母单均不能伪装成查询成功。
    if [order.id for order in result.purchaseOrders] != criteria.purchaseOrderIds:
        raise ValueError("母采购范围或顺序不一致")
    bill_ids = set()
    for order in result.purchaseOrders:
        if order.status == "PO_NOT_FOUND":
            continue
        if order.vendorId != criteria.vendorId:
            if order.status != "VENDOR_MISMATCH" or order.bills:
                raise ValueError("供应商冲突却返回账单")
            continue
        expected = "FOUND" if order.bills else "NO_BILLS"
        if order.status != expected:
            raise ValueError("母采购状态与结果不一致")
        for bill in order.bills:
            if bill.billId in bill_ids:
                raise ValueError("账单身份重复")
            bill_ids.add(bill.billId)
            if (
                bill.vendorId != criteria.vendorId
                or bill.purchaseOrderId != order.id
                or bill.subsidiaryId != order.subsidiaryId
                or bill.currencyId != order.currencyId
                or bill.currencyName != order.currencyName
            ):
                raise ValueError("账单供应商、母采购、公司或币种越界")
            validate_amounts(bill)
    if len(bill_ids) > 200:
        raise ValueError("整次查询账单数量超限")


def validate_amounts(bill):
    amounts = bill.amounts
    if Decimal(amounts.remaining) + Decimal(amounts.applied) != Decimal(amounts.payable):
        raise ValueError("应收金额与剩余、核销金额不一致")
    if Decimal(amounts.payable) - Decimal(amounts.received) != Decimal(amounts.available):
        raise ValueError("可收金额与应收、已收金额不一致")
    total = Decimal(bill.details.total)
    if bill.details.count == 0 and total != 0:
        raise ValueError("明细为空却返回非零合计")
    if bill.consistent != (total == Decimal(amounts.received)):
        raise ValueError("明细一致性标志与金额不一致")


def describe_bill(bill):
    currency = currency_code({"currencyname": bill.currencyName})
    raw = bill.amounts
    total, received, available = map(Decimal, (raw.payable, raw.received, raw.available))
    issues = []
    if bill.voided:
        issues.append("账单已作废")
    if bill.approvalStatus != "2":
        issues.append("账单尚未批准或审批状态待核实")
    if currency != "CNY":
        issues.append("币种不是已核实人民币，暂不纳入首期回写")
    if not bill.hasTax:
        issues.append("账单税额为零，暂不纳入首期回写")
    if total <= 0 or received < 0 or available <= 0:
        issues.append("账单应收、已收或可收金额不满足正向收票条件")
    if not bill.consistent:
        issues.append("账单累计已收与有效明细合计不一致，须由财务核实")
    if not bill.subPurchaseOrderId:
        issues.append("缺少 NS 子采购精确关联，需审核确认账单归属")
    return {
        **bill.model_dump(),
        "currency": currency,
        "totalInvoiceAmount": raw.payable,
        "receivedInvoiceAmount": raw.received,
        "availableInvoiceAmount": raw.available,
        "issues": issues,
    }

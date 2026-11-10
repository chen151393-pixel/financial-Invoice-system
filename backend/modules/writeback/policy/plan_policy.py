"""候选归属及分配守恒；查询结果不代表预留额度。"""

from collections import defaultdict
from decimal import Decimal

from backend.core.errors import ApiError

from .order_policy import require_whole_orders
from .registration_policy import require_clear_registration


def candidates(task, result):
    sources = task["snapshot"]["sources"]
    expected = {s["parent_id"] for s in sources.values()}
    orders = result["purchaseOrders"]
    # 查询适配器已按当前连接校验返回账套；来源账套仅用于追溯，不作为任务隔离条件。
    if result["status"] != "OK" or not result["vendor"] or result["vendor"]["id"] != task["vendor_id"]:
        raise ApiError(409, "NS 供应商身份不一致或不存在")
    if {o["id"] for o in orders} != expected or len(orders) != len(expected):
        raise ApiError(409, "母采购候选范围不完整")
    if any(o["status"] in ("PO_NOT_FOUND", "VENDOR_MISMATCH") for o in orders):
        raise ApiError(409, "母采购不存在或供应商不一致")
    for source in sources.values():
        order = next(o for o in orders if o["id"] == source["parent_id"])
        if order["vendorId"] != task["vendor_id"] or order["currencyId"] != source["currency_id"]:
            raise ApiError(409, "母采购供应商或币种与审核来源不一致")
        company = source["company_ns_id"] or ""
        if company.startswith("subsidiary:") and company.split(":", 1)[1] != order["subsidiaryId"]:
            raise ApiError(409, "母采购子公司与业务公司映射不一致")
    if len({o["subsidiaryId"] for o in orders}) != 1:
        raise ApiError(409, "不支持跨采购子公司登记")
    return {bill["billId"]: bill for order in orders for bill in order["bills"]}


def validate_plan(task, result, targets):
    require_clear_registration(task, result)
    bills = candidates(task, result)
    require_whole_orders(task, targets)
    allocations = {str(row["id"]): row for row in task["snapshot"]["allocations"]}
    allocation_sums, bill_sums = defaultdict(Decimal), defaultdict(Decimal)
    seen, prepared = set(), []
    for target in targets:
        key = (target["allocationId"], target["billId"])
        if key in seen:
            raise ApiError(422, "同一分配与账单不能重复填写")
        seen.add(key)
        row, bill = allocations.get(key[0]), bills.get(key[1])
        if not row or not bill:
            raise ApiError(409, "分配或账单不属于当前审核与查询快照")
        source = task["snapshot"]["sources"][str(row["purchase_line_id"])]
        if (
            bill["purchaseOrderId"] != source["parent_id"]
            or bill["vendorId"] != source["vendor_id"]
            or bill["currencyId"] != source["currency_id"]
        ):
            raise ApiError(409, "账单与子采购的母单、供应商或币种不一致")
        if bill["subPurchaseOrderId"] and bill["subPurchaseOrderId"] != source["subpo_id"]:
            raise ApiError(409, "账单已明确关联其他子采购，不能人工覆盖")
        # 累计与明细不一致的账单不在此阻断，冻结后生成回写预览交人工确认（方案第 1.1 节）。
        if (
            bill["approvalStatus"] != "2"
            or bill["voided"]
            or bill["currency"] != "CNY"
            or Decimal(bill["amounts"]["received"]) < 0
        ):
            raise ApiError(409, "账单未批准、作废或历史金额存在问题，不能确认")
        amount = Decimal(target["amount"])
        if amount <= 0 or amount != amount.quantize(Decimal("0.01")):
            raise ApiError(422, "分配金额必须为正数且精确到分")
        allocation_sums[key[0]] += amount
        bill_sums[key[1]] += amount
        prepared.append(
            {**target, "purchaseOrderId": source["parent_id"], "subPurchaseOrderId": source["subpo_id"]}
        )
    if set(allocation_sums) != set(allocations) or any(
        allocation_sums[key] != Decimal(row["amount"]) for key, row in allocations.items()
    ):
        raise ApiError(422, "每条审核分配的目标金额之和必须等于原金额")
    if any(amount > Decimal(bills[key]["availableInvoiceAmount"]) for key, amount in bill_sums.items()):
        raise ApiError(409, "同一账单本次合计超过可收发票额度")
    return prepared


# 自动冻结方案的依据，写入方案证据
EXACT_BASIS = "精确子采购关联及真实子公司映射唯一，所有金额校验通过"
SINGLE_BASIS = (
    "母单仅一张账单且仅一张子采购单，账单未填子采购单时直接对应；真实子公司映射唯一，所有金额校验通过"
)


def _target_bill(bills, source, sub_counts):
    parent_bills = [b for b in bills.values() if b["purchaseOrderId"] == source["parent_id"]]
    exact = [b for b in parent_bills if b["subPurchaseOrderId"] == source["subpo_id"]]
    if len(exact) == 1:
        return exact[0], EXACT_BASIS
    # NS 账单 2026-04 起不再填写子采购单；母单只有一张账单、一张有效子采购单时归属唯一
    if (
        not exact
        and len(parent_bills) == 1
        and not parent_bills[0]["subPurchaseOrderId"]
        and sub_counts.get(str(source["parent_id"])) == 1
    ):
        return parent_bills[0], SINGLE_BASIS
    return None, ""


def automatic_targets(task, result, sub_counts=None):
    """归属唯一时自动生成整单方案，返回 (分配目标, 依据)；不唯一或历史任务返回 (None, "")。

    sub_counts：NS 母单内部 ID → 本地有效子采购单张数（含未进入本票的子单）。
    """
    bills = candidates(task, result)
    if task["historical"] or any(
        not (s["company_ns_id"] or "").startswith("subsidiary:") for s in task["snapshot"]["sources"].values()
    ):
        return None, ""
    targets, bases = [], set()
    for row in task["snapshot"]["allocations"]:
        source = task["snapshot"]["sources"][str(row["purchase_line_id"])]
        bill, basis = _target_bill(bills, source, sub_counts or {})
        if not bill:
            return None, ""
        bases.add(basis)
        targets.append(
            {
                "allocationId": str(row["id"]),
                "billId": bill["billId"],
                "amount": format(Decimal(row["amount"]), ".2f"),
            }
        )
    return validate_plan(task, result, targets), "；".join(sorted(bases))

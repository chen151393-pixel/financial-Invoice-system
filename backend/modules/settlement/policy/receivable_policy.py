"""报关应收汇逐单状态规则（纯函数）：已收金额、结汇阶段、账龄与资料状态。

业务规则（2026-11-20 确认）：
- 香港中转：登记回款建批次后，批次“到账 + 手续费”按出口日期先后冲抵批次内报关单（冻结金额）；
  未建有效批次的报关单为“待登记回款”。阶段跟随批次状态：香港已收 → 资料已出待汇回 → 已结汇。
- 直接收汇：不分配到单张报关单，按“同一境外收货人、同一收款抬头、同一币种，先出口的先冲抵”
  推算已收，口径与直接收汇明细（按收款抬头拆分）一致；推算结果只用于展示，不写入任何表。
- 金额一律 Decimal，不使用浮点。
"""

from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from backend.core.names import normalize_name

from .route_policy import HK_TRANSIT

ZERO = Decimal(0)

UNREGISTERED = "unregistered"
COLLECTED = "collected"
REMIT = "remit"
UNPAID = "unpaid"
PARTIAL = "partial"
SETTLED = "settled"
ISSUE = "issue"
STAGES = (UNREGISTERED, COLLECTED, REMIT, UNPAID, PARTIAL, SETTLED, ISSUE)
STAGE_LABELS = {
    UNREGISTERED: "待登记回款",
    COLLECTED: "香港已收·办资料",
    REMIT: "资料已出·待汇回",
    UNPAID: "未收汇",
    PARTIAL: "部分收汇",
    SETTLED: "已结汇",
    ISSUE: "数据待处理",
}
# 香港到账后超过该天数仍未汇回，提示滞留
HK_STRANDED_DAYS = 30

DOCUMENT_LABELS = {
    "after_batch": "登记回款后办理",
    "pending": "资料未齐",
    "stale": "合同需重新生成",
    "complete": "资料齐全待确认",
    "ready": "资料已出",
    "none": "未办理",
    "pending_bill": "待上传或核对提单",
    "pending_contract": "待生成或核对合同",
    "kept": "资料齐全",
    "unavailable": "—",
}


def usable(row):
    """金额、币制、收货人齐全的报关单才参与应收与已收计算。"""
    return row["amount"] is not None and not row["currency_issue"] and bool(row["consignee"])


def direct_key(consignee, currency, company):
    return normalize_name(consignee), currency, normalize_name(company)


def _apply(rows, credit):
    """按顺序冲抵：返回 [(报关单号, 冲抵金额)] 与剩余（超收）金额。"""
    applied = []
    for number, amount in rows:
        used = min(amount, credit) if credit > 0 else ZERO
        applied.append((number, used))
        credit -= used
    return applied, credit


def direct_received(declarations, receipts):
    """直接收汇推算已收。

    declarations: 直接收汇且 usable 的候选报关单；receipts: 实际客户为直接收汇的银行收汇。
    返回 ({报关单号: 已收}, {(收货人键, 币种, 抬头键): 超收})。
    """
    credits = {}
    for row in receipts:
        key = (row["customer_key"], row["currency"], normalize_name(row["receiving_company"]))
        credits[key] = credits.get(key, ZERO) + Decimal(row["amount"])
    groups = {}
    for row in declarations:
        key = direct_key(row["consignee"], row["currency"], row.get("export_company") or "")
        groups.setdefault(key, []).append(row)
    received, overpaid = {}, {}
    for key, rows in groups.items():
        rows.sort(key=lambda r: (r["export_date"] or date.min, r["declaration_no"]))
        applied, left = _apply(
            [(r["declaration_no"], Decimal(r["amount"])) for r in rows], credits.get(key, ZERO)
        )
        received.update(applied)
        if left > 0:
            overpaid[key] = left
    # 只有收汇、没有出口的客户全部算超收
    for key, credit in credits.items():
        if key not in groups and credit > 0:
            overpaid[key] = credit
    return received, overpaid


def hk_received(batch, items):
    """香港批次“到账 + 手续费”按出口日期先后冲抵批次内报关单冻结金额：{报关单号: 已收}。"""
    credit = Decimal(batch["received_amount"]) + Decimal(batch["received_fee"] or 0)
    ordered = sorted(items, key=lambda i: (i["export_date"] or date.min, i["declaration_no"]))
    applied, _ = _apply([(i["declaration_no"], Decimal(i["declared_amount"])) for i in ordered], credit)
    return dict(applied)


def stage_of(row, received, batch_status):
    """逐单结汇阶段；batch_status 为所在有效香港批次的状态，没有批次为 None。"""
    if not usable(row):
        return ISSUE
    if row["route"] == HK_TRANSIT:
        if batch_status is None:
            return UNREGISTERED
        return {"collected": COLLECTED, "documents_ready": REMIT, "settled": SETTLED}.get(
            batch_status, COLLECTED
        )
    if received <= 0:
        return UNPAID
    return SETTLED if received >= row["amount"] else PARTIAL


def aging_days(row, stage, today):
    """未结汇报关单自出口日起的天数；已结汇或缺出口日期为 None。"""
    if stage == SETTLED or row["export_date"] is None:
        return None
    return max((today - row["export_date"]).days, 0)


def alert_of(row, stage, batch, today):
    """需要关注的情况：香港到账后滞留超期。"""
    if row["route"] == HK_TRANSIT and stage == REMIT and batch and batch["received_on"]:
        days = (today - batch["received_on"]).days
        if days > HK_STRANDED_DAYS:
            return f"香港滞留 {days} 天"
    return ""


def hk_document_status(batch_status, state):
    """香港中转资料状态：资料挂在批次下；state 为 collected 批次的资料现状（DocumentReader.state）。"""
    if batch_status is None:
        return "after_batch", ""
    if batch_status in ("documents_ready", "settled"):
        return "ready", ""
    if state is None:
        return "unavailable", ""
    if state["stale"]:
        return "stale", "合同依据变化，需重新生成"
    if state["issues"]:
        more = f" 等 {len(state['issues'])} 项" if len(state["issues"]) > 1 else ""
        return "pending", f"{state['issues'][0]}{more}"
    return "complete", "可确认资料已出"


def direct_document_status(has_documents, state):
    """直接收汇资料状态：留存用，不影响结汇阶段。"""
    if not has_documents:
        return "none", ""
    if state is None:
        return "unavailable", ""
    if state["stale"]:
        return "stale", "合同依据变化，需重新生成"
    if not state["issues"]:
        return "kept", ""
    if (
        not state["bills"]
        or any(bill["parse_note"] for bill in state["bills"])
        or any("提单" in issue for issue in state["issues"])
    ):
        return "pending_bill", state["issues"][0]
    return "pending_contract", state["issues"][0]


def received_percent(received, amount):
    """收汇进度：(进度条宽度 0–100 的整数, 实际百分比文本)。金额为 0 时视为无进度。"""
    if not amount or amount <= 0:
        return 0, "—"
    ratio = received / amount * 100
    width = int(min(max(ratio, ZERO), Decimal(100)))
    return width, f"{ratio.quantize(Decimal(1), rounding=ROUND_HALF_UP)}%"

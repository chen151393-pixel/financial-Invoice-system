"""香港中转工作区纯规则：阶段统计、关键字匹配与资料/流程状态。"""

from .amount_policy import money
from .bill_parse_policy import missing_fields
from .receivable_policy import HK_STRANDED_DAYS

OPEN = ("collected", "documents_ready")
STAGES = (
    ("open", "进行中", "primary", "未结汇的报关单与批次"),
    ("register", "待登记回款", "warning", "勾选报关单，登记香港到账"),
    ("collected", "香港已收 · 办资料", "progress", "上传提单、生成销售合同"),
    ("documents_ready", "资料已出 · 待汇回", "info", "登记汇回境内并核对"),
    ("settled", "已结汇", "success", "累计已完成批次"),
)


def matches(row, keyword, fields):
    text = keyword.casefold()
    return not text or any(text in str(row.get(field) or "").casefold() for field in fields)


def stages(pending, batches):
    result = []
    for key, label, tone, note in STAGES:
        count = sum(batch["status"] in OPEN if key == "open" else batch["status"] == key for batch in batches)
        value = (
            f"{len(pending)} 票 · {count} 批"
            if key == "open"
            else (f"{len(pending)} 票" if key == "register" else f"{count} 批")
        )
        result.append(dict(key=key, label=label, value=value, note=note, tone=tone))
    return result


def pending(row, today):
    reason = row["blocked"]
    if row["amount"] is None and not reason:
        reason = "海关回执没有可用金额"
    days = max(0, (today - row["export_date"]).days) if row["export_date"] else None
    return dict(
        declarationNo=row["declaration_no"],
        recordNo=row["record_no"],
        consignee=row["consignee"],
        exportCompany=row["export_company"],
        currency=row["currency"],
        amount=str(money(row["amount"])) if row["amount"] is not None else "",
        exportDate=str(row["export_date"]) if row["export_date"] else "",
        waitingLabel=f"出口 {days} 天" if days is not None else "出口日期待补",
        select=dict(allowed=not reason, reason=reason),
    )


def batch_state(batch, items, state, today):
    status = batch["status"]
    complete = not state["issues"]
    exported = {item["declaration_no"] for item in items}
    covered = {no for bill in state["bills"] for no in bill["declaration_nos"] or []}
    bill_ok = bool(items) and exported <= covered and all(not missing_fields(bill) for bill in state["bills"])
    required = {row["contract_no"] for row in state["planned"]}
    generated = {row["contract_no"] for row in state["contracts"]}
    contract_ok = (
        bool(required)
        and required <= generated
        and not (state["stale"] or state["plan_issues"] or state["party_issues"])
    )
    originals = state["declaration_files"]
    original_ok = bool(originals) and all(row["status"] == "archived" for row in originals)
    days = max(0, (today - batch["received_on"]).days)
    overdue = status == "documents_ready" and days > HK_STRANDED_DAYS
    label = f"香港已收 {days} 天"
    if status == "settled":
        label = f"{batch['remitted_on']} 结汇"
    elif status == "cancelled":
        label = "批次已作废"
    elif status == "documents_ready":
        label = f"滞留香港 {days} 天"
    states = ["done", "done" if complete else "current", "waiting", "waiting"]
    if status == "collected" and complete:
        states[2] = "current"
    if status in ("documents_ready", "settled"):
        states = ["done", "done", "done", "done" if status == "settled" else "current"]
    if status == "cancelled":
        states = ["done", "skipped", "skipped", "skipped"]
    descriptions = [
        str(batch["received_on"]),
        "资料齐全" if complete else "待补齐资料",
        str(batch["documents_ready_at"].date()) if batch["documents_ready_at"] else "待确认",
        str(batch["remitted_on"]) if batch["remitted_on"] else "待登记",
    ]
    action, primary = {
        "collected": ("documents", "办理资料"),
        "documents_ready": ("remit", "登记汇回"),
        "settled": ("package", "下载资料包"),
    }.get(status, ("view", "查看批次"))
    return dict(
        waitingLabel=label,
        overdue=overdue,
        issue="；".join(state["issues"][:2]),
        notice=f"香港到账后已 {days} 天未汇回，请跟进境内到账。"
        if overdue
        else "；".join(state["warnings"][:1]),
        documents=[
            dict(label="提单", ready=bill_ok, description="已齐全" if bill_ok else "待上传或核对"),
            dict(
                label="合同",
                ready=bool(contract_ok),
                description="齐全且最新" if contract_ok else "待生成或更新",
            ),
            dict(label="原件", ready=original_ok, description="已归档" if original_ok else "未齐，仅提示"),
        ],
        steps=[
            dict(key=key, label=name, state=step, description=desc)
            for key, name, step, desc in zip(
                ("received", "documents", "ready", "remitted"),
                ("香港到账", "资料齐全", "资料已出", "汇回结汇"),
                states,
                descriptions,
                strict=True,
            )
        ],
        primaryLabel=primary,
        primaryAction=action,
    )

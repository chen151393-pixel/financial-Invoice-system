"""独立登记页核对规则：严格对平才允许提交，手续费超预警仅提醒。"""

from backend.core.errors import ApiError

from .amount_policy import balance_check, money
from .batch_selection_policy import validate_selection
from .consignee_policy import consignee_key
from .hk_workbench_policy import pending


def preview(rows, body, fee_alert, accounts, today):
    reason, selection = "", None
    if not body.declarationNos:
        reason = "请至少选择一张报关单"
    else:
        try:
            selection = validate_selection(rows, body.declarationNos)
        except ApiError as error:
            reason = error.message
    names = {consignee_key(row["consignee"]) for row in rows if row["consignee"]}
    currencies = {row["currency"] for row in rows if row["currency"]}
    valid_scope = selection is not None
    total = selection[3] if selection else None
    currency = selection[2] if selection else next(iter(currencies)) if len(currencies) == 1 else ""
    consignee = selection[1] if selection else ""
    check = balance_check(total or 0, body.receivedAmount, body.receivedFee, fee_alert)
    balanced = valid_scope and check["balanced"] and body.receivedAmount > 0

    def item(key, label, ok, detail, warning=False):
        return dict(
            key=key, label=label, detail=detail, state="success" if ok else "warning" if warning else "error"
        )

    checks = [
        item(
            "selection",
            "至少选择一张有效报关单",
            valid_scope,
            reason or f"已选 {len(body.declarationNos)} 张",
        ),
        item(
            "consignee",
            "同一境外收货人",
            valid_scope and len(names) == 1,
            consignee or "请核对已选报关单的收货人",
        ),
        item("currency", "同一币种", valid_scope and len(currencies) == 1, currency or "请核对币种"),
        item(
            "balance",
            "到账 + 手续费 = 报关合计",
            balanced,
            "严格对平"
            if balanced
            else f"差额 {money(check['difference'])}"
            if valid_scope
            else "选单有效后核对",
        ),
        item(
            "date",
            "已填写到账日期",
            body.receivedOn is not None,
            str(body.receivedOn or "请选择实际到账日期"),
        ),
        item(
            "fee",
            "手续费在预警线内",
            body.receivedFee <= fee_alert,
            f"{money(body.receivedFee)} ≤ {money(fee_alert)}"
            if body.receivedFee <= fee_alert
            else f"{money(body.receivedFee)} 超过 {money(fee_alert)}，请对照水单核对",
            warning=True,
        ),
    ]
    if not reason and body.receivedAmount <= 0:
        reason = "请填写正数到账金额"
    if not reason and not balanced:
        reason = "到账加手续费与报关合计未对平"
    if not reason and body.receivedOn is None:
        reason = "请选择实际到账日期"
    found = {r["declaration_no"]: r for r in rows}
    selected = []
    for number in body.declarationNos:
        if number in found:
            selected.append(pending(found[number], today))
        else:
            selected.append(
                dict(
                    declarationNo=number,
                    recordNo="",
                    consignee="",
                    exportCompany="",
                    currency="",
                    amount="",
                    exportDate="",
                    waitingLabel="来源待核对",
                    select=dict(allowed=False, reason="未找到当前可用报关依据"),
                )
            )
    return dict(
        rows=selected,
        currency=currency,
        consignee=consignee,
        declaredTotal=str(money(total)) if total is not None else "",
        amount=str(money(body.receivedAmount)),
        fee=str(money(body.receivedFee)),
        arrivedTotal=str(money(body.receivedAmount + body.receivedFee)),
        difference=str(money(check["difference"])) if valid_scope else "",
        balanced=balanced,
        accounts=accounts,
        checks=checks,
        warnings=check["warnings"] if valid_scope else [],
        submit=dict(allowed=not reason, reason=reason),
    )

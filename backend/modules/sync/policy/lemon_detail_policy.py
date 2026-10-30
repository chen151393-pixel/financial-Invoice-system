"""补拉限定原来源与当前授权账套；同一请求保持相同选择范围。"""

import hashlib

from backend.core.errors import ApiError


def account_namespace(host, asid, professional=True):
    return ("professional:" if professional else "open2:") + hashlib.sha256(
        f"{host}|{asid}".encode()
    ).hexdigest()


# 账套版本决定能拉到的内容：专业版有商品明细接口，免费版（open2 默认版）只返回票头。
EDITIONS = {
    "professional": ("专业版", "票头 + 商品明细"),
    "free": ("免费版", "仅票头；商品明细与附件尚未接入"),
}


def edition_view(account):
    edition = "professional" if account.get("edition") == "professional" else "free"
    label, content = EDITIONS[edition]
    return {"edition": edition, "editionLabel": label, "content": content}


def refresh_action(row, account):
    if row is None:
        reason = "发票不存在，请刷新列表"
    elif row["source"] != "lemon_professional":
        reason = "仅支持柠檬云专业版接口发票；Excel 或默认版请使用原导入方式"
    elif row["lemon_account"] != account:
        reason = "当前账套与发票原账套不一致，请到柠檬云同步页选择原账套"
    elif not row["external_id"] or not row["invoice_date"]:
        reason = "发票缺少来源编号或开票日期，无法补拉"
    else:
        return {"allowed": True, "reason": "从原账套重新拉取商品明细"}
    return {"allowed": False, "reason": reason}


def selected_records(records, targets):
    if targets is None:
        return records
    expected = {str(row["external_id"]) for row in targets}
    selected = [row for row in records if str(row.get("InvoiceId")) in expected]
    if len(selected) != len(expected) or {str(row["InvoiceId"]) for row in selected} != expected:
        raise ApiError(409, "部分所选发票已不在原日期范围或来源返回不完整，本次未保存，请核实原票")
    return selected

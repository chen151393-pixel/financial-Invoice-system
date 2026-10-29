"""解释写入 RESTlet 的返回；无法确认是否写入时一律按结果不明处理。"""

import re

PROBLEMS = {
    "BILL_NOT_FOUND": "账单不存在或不可见",
    "VENDOR_MISMATCH": "账单供应商与发票不一致",
    "ORDER_MISMATCH": "账单不属于该母采购",
    "NOT_APPROVED": "账单未批准",
    "VOIDED": "账单已作废",
    "STALE": "账单累计已变化，请重新查询账单后再确认",
    "OVER_AVAILABLE": "本次金额超过账单可收额度",
}
ERRORS = {
    "INVALID_REQUEST": "NS 拒绝了写入正文，未写入",
    "INVALID_RESULT": "NS 账单数据异常，未写入",
    "QUERY_LIMIT": "NS 脚本额度不足，未写入",
    "WRITE_FAILED": "NS 保存发票记录失败，未写入",
}
ID = re.compile(r"[1-9][0-9]{0,19}")


def unknown(reason):
    return {"state": "unknown", "reason": reason, "release": False, "record": None}


def _same_account(left, right):
    return str(left).lower().replace("-", "_") == str(right).lower().replace("-", "_")


def interpret(request, response, account):
    payload = request["payload"]
    if (
        not isinstance(response, dict)
        or response.get("contractVersion") != 1
        or response.get("source") != "vendor-bill-writeback"
        or not _same_account(response.get("account"), account)
        or response.get("requestId") != payload["requestId"]
        or not isinstance(response.get("written"), bool)
    ):
        return unknown("NS 返回格式无法核对，写入结果不明，请在 NS 核实")
    record = response.get("invoiceRecordId")
    if response["written"] and not (isinstance(record, str) and ID.fullmatch(record)):
        return unknown("NS 表示已写入但未返回发票记录 ID，请在 NS 核实")
    status = response.get("status") if response.get("complete") is True else None
    if status == "APPLIED":
        expected = {line["billId"]: line for line in payload["bills"]}
        bills = response.get("bills")
        if (
            not response["written"]
            or not isinstance(bills, list)
            or {item.get("billId") for item in bills} != set(expected)
            or len(bills) != len(expected)
            or any(
                item.get("status") != "UPDATED"
                or item.get("verified") is not True
                or item.get("amount") != expected[item["billId"]]["amount"]
                or item.get("before") != expected[item["billId"]]["expectedBefore"]
                for item in bills
            )
        ):
            return unknown("NS 返回的账单结果与请求不符，请在 NS 核实")
        return {
            "state": "applied",
            "reason": f"NS 已登记，发票记录 ID {record}",
            "release": True,
            "record": record,
        }
    if response["written"]:
        return {
            "state": "partial",
            "reason": f"NS 已建发票记录 {record}，但账单累计未全部更新，请在 NS 核实并补齐后标记结果",
            "release": False,
            "record": record,
        }
    if status == "CONFLICT":
        existing = "、".join(str(item.get("id")) for item in response.get("existing") or [])
        return {
            "state": "conflict",
            "reason": f"NS 已有同号发票登记（记录 ID {existing or '未知'}），未写入，请财务核对",
            "release": True,
            "record": None,
        }
    if status == "REJECTED":
        problems = response.get("problems") or []
        detail = "；".join(
            f"账单 {item.get('billId')}：{PROBLEMS.get(item.get('code'), '未通过 NS 复核')}"
            for item in problems
        )
        return {
            "state": "rejected",
            "reason": detail or "未通过 NS 复核，未写入",
            "release": True,
            "record": None,
        }
    if response.get("complete") is False:
        code = (response.get("error") or {}).get("code")
        return {"state": "rejected", "reason": ERRORS.get(code, "NS 未写入"), "release": True, "record": None}
    return unknown("NS 返回状态无法识别，请在 NS 核实")

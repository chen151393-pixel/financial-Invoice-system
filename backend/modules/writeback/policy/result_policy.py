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
    # 账单补写（2026-11-10）
    "INVOICE_MISMATCH": "NS 发票记录不存在、已停用，或号码、供应商与本次回写不一致",
    "DETAIL_MISMATCH": "NS 发票记录明细的账单或金额与本次回写不一致",
}
ERRORS = {
    "INVALID_REQUEST": "NS 拒绝了写入正文，未写入",
    "INVALID_RESULT": "NS 账单数据异常，未写入",
    "QUERY_LIMIT": "NS 脚本额度不足，未写入",
    "WRITE_FAILED": "NS 保存发票记录失败，未写入",
}
# 补写在改动账单前失败时的原因；INVALID_REQUEST 多为 NS 脚本仍是不支持补写的旧版本
REPAIR_ERRORS = {
    "INVALID_REQUEST": "NS 回写脚本尚未更新到支持账单补写的版本，账单未补写",
    "INVALID_RESULT": "NS 发票记录或账单数据异常，账单未补写",
    "QUERY_LIMIT": "NS 脚本额度不足，账单未补写，可稍后再次补写",
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


def interpret_repair(request, response, account):
    """解释账单补写（action=repair）的返回。

    返回 state：applied（全部账单已补齐）、partial（仍有账单未补齐，发票记录不变）、unknown（无法核对），
    或 not_written（NS 复核未通过或拒绝正文，未改动任何账单）。补写不新建发票记录，record 始终为原记录 ID。
    """
    payload, record = request["payload"], request["ns_record_id"]
    if (
        not isinstance(response, dict)
        or response.get("contractVersion") != 1
        or response.get("source") != "vendor-bill-writeback"
        or not _same_account(response.get("account"), account)
        or response.get("requestId") != payload["requestId"]
        or not isinstance(response.get("written"), bool)
    ):
        return unknown("NS 补写返回格式无法核对，账单补写结果不明，请在 NS 核实")
    if response.get("complete") is False and not response["written"]:
        code = (response.get("error") or {}).get("code")
        reason = REPAIR_ERRORS.get(code, "NS 补写失败，账单未改动，可稍后再次补写")
        return {"state": "not_written", "reason": reason, "release": False, "record": record}
    status = response.get("status") if response.get("complete") is True else None
    if status == "REJECTED" and not response["written"]:
        detail = "；".join(
            (f"账单 {item.get('billId')}：" if item.get("billId") else "")
            + PROBLEMS.get(item.get("code"), "未通过 NS 复核")
            for item in response.get("problems") or []
        )
        return {
            "state": "not_written",
            "reason": f"账单补写未通过 NS 复核，未改动账单：{detail or '原因未提供'}",
            "release": False,
            "record": record,
        }
    if response.get("action") != "repair" or response.get("invoiceRecordId") != record:
        return unknown("NS 补写返回的发票记录与本任务不一致，请在 NS 核实")
    expected = {line["billId"]: line for line in payload["bills"]}
    bills = response.get("bills")
    if (
        not isinstance(bills, list)
        or len(bills) != len(expected)
        or {item.get("billId") for item in bills} != set(expected)
    ):
        return unknown("NS 补写返回的账单与请求不符，请在 NS 核实")
    if status == "APPLIED" and all(
        item.get("status") in ("UPDATED", "ALREADY_UPDATED")
        and item.get("verified") is True
        and item.get("amount") == expected[item["billId"]]["amount"]
        and item.get("before") == expected[item["billId"]]["expectedBefore"]
        for item in bills
    ):
        return {
            "state": "applied",
            "reason": f"账单已补写，NS 已完整登记，发票记录 ID {record}",
            "release": True,
            "record": record,
        }
    if status in ("APPLIED", "PARTIAL"):
        pending = [
            item.get("billNumber") or item.get("billId") for item in bills if item.get("verified") is not True
        ]
        return {
            "state": "partial",
            "reason": f"账单补写未全部完成（未补齐：{'、'.join(map(str, pending)) or '未知'}），"
            f"发票记录 {record} 不变，请处理 NS 原因后再次补写或核实后标记结果",
            "release": False,
            "record": record,
        }
    return unknown("NS 补写返回状态无法识别，请在 NS 核实")

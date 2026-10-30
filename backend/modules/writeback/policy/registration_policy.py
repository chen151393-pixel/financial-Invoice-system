"""已有登记核对必须明确完成；未知不能当作未登记，不按可收金额推断本张发票已登记。"""

from backend.core.errors import ApiError


def require_clear_registration(task, result):
    check = (result or {}).get("registrationCheck")
    if (
        not isinstance(check, dict)
        or check.get("invoiceNumber") != task["invoice_no"]
        or not isinstance(check.get("records"), list)
    ):
        raise ApiError(409, "尚未完成本张发票的同号登记核对，请升级只读查询脚本并重新查询账单")
    if check["records"]:
        raise ApiError(409, "NS 已有同号发票登记，已拦截重复回写，请核对已有登记")

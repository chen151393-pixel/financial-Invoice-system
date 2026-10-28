"""实时查询 NS 候选账单；不连接数据库，不生成分配或审核结论。"""

from uuid import uuid4

from pydantic import ValidationError

from backend.core.errors import ApiError

from ..dto.vendor_bill_query import VendorBillQuery
from ..policy.vendor_bill_policy import REASONS, WARNINGS, describe_bill, validate_result
from ..vo.vendor_bill_query import NsBillResult, VendorBillResult


class VendorBillQueryService:
    def __init__(self, ns):
        self.ns = ns

    def query_ids(self, vendor_id, purchase_order_ids):
        return self.query(VendorBillQuery(vendorId=vendor_id, purchaseOrderIds=purchase_order_ids))

    def query(self, criteria):
        data = self.ns.vendor_bill_query(criteria.model_dump())
        if isinstance(data, dict) and data.get("complete") is False:
            code = data.get("error", {}).get("code") if isinstance(data.get("error"), dict) else ""
            reason = {
                "QUERY_LIMIT": "账单查询超出单次范围或执行额度，请缩小范围后重查",
                "INVALID_REQUEST": "NS 账单查询参数契约不一致，请核对部署版本",
                "INVALID_RESULT": "NS 返回的账单或金额不完整，请核实脚本及数据",
            }.get(code, "NS 账单查询失败，请核对部署受众及查询权限")
            raise ApiError(502, reason)
        try:
            result = NsBillResult.model_validate(data)
            validate_result(result, criteria, self.ns.settings.account)
            return VendorBillResult.model_validate(
                {
                    **result.model_dump(),
                    "purchaseOrders": [
                        {
                            **order.model_dump(),
                            "bills": [describe_bill(bill) for bill in order.bills],
                            "reason": REASONS[order.status],
                        }
                        for order in result.purchaseOrders
                    ],
                    "queryId": str(uuid4()),
                    "reason": REASONS[result.status],
                    "warnings": WARNINGS,
                }
            )
        except (ValidationError, ValueError):
            raise ApiError(502, "NS 账单查询结果契约或完整性校验失败，未返回部分候选") from None

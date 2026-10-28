"""部署后只读抽样：调用已运行后端的账单查询接口，核对 NS 网页人工参考值。"""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import httpx
from pydantic import Field, ValidationError, model_validator

from backend.core.config import load_settings
from backend.core.dto import StrictModel
from backend.core.errors import ApiError
from backend.modules.source.dto.vendor_bill_query import NsId, VendorBillQuery
from backend.modules.source.policy.vendor_bill_policy import validate_result
from backend.modules.source.vo.vendor_bill_query import Money, VendorBillResult


class QueryApi:
    def __init__(self, settings, client):
        self.settings, self.client = settings, client

    def query(self, criteria):
        try:
            with self.client.stream(
                "POST",
                f"{self.settings.origin}/api/source/vendor-bills/query",
                headers={"Authorization": f"Bearer {self.settings.service_key}"},
                json=criteria.model_dump(),
                follow_redirects=False,
            ) as response:
                if not response.is_success:
                    raise ApiError(
                        502,
                        f"后端账单查询失败（HTTP {response.status_code}），未自动重试",
                    )
                chunks, size = [], 0
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > 8 * 1024 * 1024:
                        raise ApiError(502, "后端查询响应超限")
                    chunks.append(chunk)
            result = VendorBillResult.model_validate_json(b"".join(chunks))
            validate_result(result, criteria, self.settings.account)
            return result
        except httpx.HTTPError:
            raise ApiError(502, "后端账单查询连接失败或超时，未自动重试") from None
        except (ValidationError, ValueError):
            raise ApiError(
                502, "后端账单查询响应或账套不一致，不能标记核对通过"
            ) from None


class ExpectedBill(StrictModel):
    billId: NsId
    totalInvoiceAmount: Money
    receivedInvoiceAmount: Money
    availableInvoiceAmount: Money


class ExpectedPurchase(StrictModel):
    id: NsId
    status: Literal["FOUND", "NO_BILLS", "PO_NOT_FOUND", "VENDOR_MISMATCH"]
    bills: list[ExpectedBill] = Field(max_length=200)

    @model_validator(mode="after")
    def unique_ids(self):
        if len({b.billId for b in self.bills}) != len(self.bills):
            raise ValueError("参考账单 ID 重复")
        return self


class Expected(StrictModel):
    status: Literal["OK", "VENDOR_NOT_FOUND"]
    purchaseOrders: list[ExpectedPurchase] = Field(max_length=20)

    @model_validator(mode="after")
    def unique_ids(self):
        if len({p.id for p in self.purchaseOrders}) != len(self.purchaseOrders):
            raise ValueError("参考母采购 ID 重复")
        return self


class Case(StrictModel):
    name: str = Field(min_length=1, max_length=100)
    query: VendorBillQuery
    expected: Expected | None = None


def compare(actual, expected):
    if expected is None:
        return "NOT_COMPARED", ["未提供 NS 人工核对值，仅收集查询结果"]
    differences = []
    if actual.status != expected.status:
        differences.append(f"状态不一致：参考 {expected.status}，实际 {actual.status}")
    left_orders = {p.id: p for p in actual.purchaseOrders}
    right_orders = {p.id: p for p in expected.purchaseOrders}
    if left_orders.keys() != right_orders.keys():
        differences.append("母采购 ID 集合不一致")
    for order_id in sorted(left_orders.keys() & right_orders.keys()):
        left_order, right_order = left_orders[order_id], right_orders[order_id]
        if left_order.status != right_order.status:
            differences.append(f"母采购 {order_id} 的状态与参考值不一致")
        differences.extend(compare_bills(left_order.bills, right_order.bills))
    return ("DIFFERENT" if differences else "MATCH"), differences


def compare_bills(actual, expected):
    from decimal import Decimal

    differences = []
    left = {b.billId: b for b in actual}
    right = {b.billId: b for b in expected}
    if left.keys() != right.keys():
        differences.append("候选账单 ID 集合不一致")
    for bill_id in sorted(left.keys() & right.keys()):
        for field in (
            "totalInvoiceAmount",
            "receivedInvoiceAmount",
            "availableInvoiceAmount",
        ):
            if Decimal(getattr(left[bill_id], field)) != Decimal(
                getattr(right[bill_id], field)
            ):
                differences.append(f"账单 {bill_id} 的 {field} 与参考值不一致")
    return differences


def run(service, cases):
    results = []
    for case in cases:
        try:
            actual = service.query(case.query)
            verdict, differences = compare(actual, case.expected)
            results.append(
                {
                    "name": case.name,
                    "query": case.query.model_dump(),
                    "verdict": verdict,
                    "differences": differences,
                    "result": actual.model_dump(),
                }
            )
        except ApiError as error:
            results.append(
                {
                    "name": case.name,
                    "query": case.query.model_dump(),
                    "verdict": "ERROR",
                    "error": error.message,
                }
            )
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--expect-account",
        required=True,
        help="人工核对的目标 NS 账套，防止误用其他连接",
    )
    args = parser.parse_args()
    try:
        raw = json.loads(args.cases.read_text(encoding="utf-8-sig"))
        if not isinstance(raw, list) or not 1 <= len(raw) <= 20:
            raise ValueError("样本应为 1 至 20 项 JSON 数组")
        cases = [Case.model_validate(item) for item in raw]
        settings = load_settings()
        if len(settings.service_key) < 32:
            raise ValueError("核对工具需要现有 SERVICE_API_KEY，未发起请求")
        if settings.account != args.expect_account.strip().lower().replace("_", "-"):
            raise ValueError("配置账套与 --expect-account 不一致，未发起请求")
        if (
            not settings.vendor_bill_query_script
            or not settings.vendor_bill_query_deploy
        ):
            raise ValueError("只读账单 RESTlet 尚未配置，未发起请求")
        if args.output.exists() or not args.output.parent.is_dir():
            raise ValueError("输出文件必须不存在且父目录已存在，未发起请求")
    except (OSError, ValueError, ValidationError):
        # 不打印可能带连接凭证的配置异常、输入正文或异常对象。
        parser.exit(
            2,
            "参数、样本或配置不符合要求；核对账套、RESTlet 编号和输出路径。未发起请求。\n",
        )
    with httpx.Client(timeout=90, follow_redirects=False, trust_env=False) as client:
        results = run(QueryApi(settings, client), cases)
    report = {
        "account": settings.account,
        "readOnly": True,
        "writebackEnabled": False,
        "completedAt": datetime.now(timezone.utc).isoformat(),
        "cases": results,
    }
    with args.output.open("x", encoding="utf-8") as output:
        json.dump(report, output, ensure_ascii=False, indent=2)
    print(f"已完成 {len(results)} 个只读样本，核对结果保存至指定文件；未写入 NS。")
    return 0 if all(row["verdict"] == "MATCH" for row in results) else 2


if __name__ == "__main__":
    raise SystemExit(main())

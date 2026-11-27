"""直接收汇资料组当前依据；成员独占，跨抬头允许，跨客户或币种禁止。"""

from decimal import Decimal

from backend.core.errors import ApiError

from ..dao import document_group_dao as dao
from ..dao.document_scope import DocumentGroupRef
from ..policy.consignee_policy import consignee_key
from ..policy.route_policy import DIRECT


class DocumentGroupSource:
    def __init__(self, candidates):
        self.candidates = candidates

    def load(self, connection, reference, *, lock=False):
        group_id = reference.id if isinstance(reference, DocumentGroupRef) else reference
        group = dao.resolve(connection, group_id)
        if group and lock and group["id"] != group_id:
            raise ApiError(409, f"资料组已合并至 {group['group_no']}，请刷新后在新组办理")
        if group:
            group_id = group["id"]
        if group is None:
            raise ApiError(404, "直接收汇资料组不存在")
        numbers = dao.numbers(connection, group_id)
        found = {
            r["declaration_no"]: r for r in self.candidates.load(connection, numbers=numbers, limit=None)
        }
        return self.context(group, numbers, found)

    @staticmethod
    def context(group, numbers, found):
        group_id = group["id"]
        issues, rows = [], []
        for number in numbers:
            row = found.get(number)
            if row is None:
                issues.append(f"报关单 {number} 已没有当前有效的 NS 关联回执")
                row = dict(
                    declaration_no=number,
                    record_no="",
                    consignee="",
                    export_company="",
                    currency="",
                    amount=None,
                    sales_orders=[],
                    export_date=None,
                )
            elif (
                row["route"] != DIRECT
                or consignee_key(row["consignee"]) != consignee_key(group["consignee"])
                or row["currency"] != group["currency"]
                or row["currency_issue"]
            ):
                issues.append(f"报关单 {number} 的客户、币种或收汇路径已变化，请核对来源")
            rows.append(row)
        return dict(
            id=DocumentGroupRef(group_id),
            document_group_id=group_id,
            group_no=group["group_no"],
            document_kind="direct",
            document_issue="；".join(issues),
            route=DIRECT,
            status="documents",
            consignee=group["consignee"],
            currency=group["currency"],
            declared_total=sum(
                (r["amount"] or Decimal(0) for r in rows if r["currency"] == group["currency"]), Decimal(0)
            ),
        ), rows

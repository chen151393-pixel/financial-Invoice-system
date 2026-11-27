"""直接收汇资料的当前报关依据；不创建收款批次，不读写到账金额。"""

from backend.core.errors import ApiError

from ..dao import document_group_dao
from ..policy.route_policy import DIRECT


class DirectDocumentSource:
    def __init__(self, candidates):
        self.candidates = candidates

    def load(self, connection, number, *, lock=False):
        grouped = document_group_dao.by_numbers(connection, [number]).get(number)
        if grouped:
            raise ApiError(409, f"报关单已在资料组 {grouped['group_no']} 中，请在直接收汇的资料组中办理")
        rows = self.candidates.load(connection, numbers=[number], limit=None)
        if len(rows) != 1:
            raise ApiError(404, "未找到已关联 NS 报关单的当前海关回执")
        row = rows[0]
        if row["route"] != DIRECT:
            raise ApiError(409, "该报关单为香港中转，请在对应香港批次办理资料")
        return self.context(row)

    def for_row(self, connection, row):
        """只读调用方跟随资料组；单票编辑入口不允许绕过组作用域。"""
        group = document_group_dao.by_numbers(connection, [row["declaration_no"]]).get(row["declaration_no"])
        if group:
            from .document_group_source import DocumentGroupSource

            return DocumentGroupSource(self.candidates).load(connection, group["id"])
        return self.context(row)

    def for_rows(self, connection, rows, groups):
        """列表批量组装直接收汇资料依据；组内未出现在筛选结果中的成员仍完整参与。"""
        from .document_group_source import DocumentGroupSource

        resolved = {}
        for group in groups.values():
            identity = group["id"]
            if identity not in resolved:
                resolved[identity] = (
                    document_group_dao.resolve(connection, identity) if group["merged_into_id"] else group
                )
        members = document_group_dao.numbers_by_groups(
            connection, sorted({group["id"] for group in resolved.values() if group})
        )
        numbers = [number for group in members.values() for number in group]
        found = (
            {
                row["declaration_no"]: row
                for row in self.candidates.load(connection, numbers=numbers, limit=None)
            }
            if numbers
            else {}
        )
        contexts = {}
        for row in rows:
            group = groups.get(row["declaration_no"])
            if group:
                current = resolved[group["id"]]
                if current is None:
                    raise ApiError(404, "直接收汇资料组不存在")
                contexts[row["declaration_no"]] = DocumentGroupSource.context(
                    current, members[current["id"]], found
                )
            else:
                contexts[row["declaration_no"]] = self.context(row)
        return contexts

    @staticmethod
    def context(row):
        number = row["declaration_no"]
        context = {
            "id": number,
            "direct_declaration_no": number,
            "document_kind": "direct",
            "document_issue": row["currency_issue"]
            or ("海关回执没有境外收货人" if not row["consignee"] else ""),
            "route": DIRECT,
            "status": "documents",
            "consignee": row["consignee"],
            "currency": row["currency"],
            "declared_total": row["amount"] or 0,
        }
        return context, [row]

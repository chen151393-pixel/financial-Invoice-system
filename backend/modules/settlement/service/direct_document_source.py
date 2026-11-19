"""直接收汇资料的当前报关依据；不创建收款批次，不读写到账金额。"""

from backend.core.errors import ApiError

from ..policy.route_policy import DIRECT


class DirectDocumentSource:
    def __init__(self, candidates):
        self.candidates = candidates

    def load(self, connection, number, *, lock=False):
        rows = self.candidates.load(connection, numbers=[number], limit=None)
        if len(rows) != 1:
            raise ApiError(404, "未找到已关联 NS 报关单的当前海关回执")
        row = rows[0]
        if row["route"] != DIRECT:
            raise ApiError(409, "该报关单为香港中转，请在对应香港批次办理资料")
        return self.context(row)

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

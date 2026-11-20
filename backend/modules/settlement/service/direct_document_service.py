"""直接收汇资料列表：状态、搜索、分页在后端处理，资料编辑复用既有用例。"""

from backend.core.errors import ApiError
from backend.core.names import normalize_name

from ..dao import document_group_dao
from ..policy.amount_policy import money
from ..policy.route_policy import DIRECT
from ..vo.batch_vo import Action
from ..vo.direct_document_vo import DirectDocumentList, DirectDocumentRow
from .direct_document_source import DirectDocumentSource
from .document_group_source import DocumentGroupSource


def progress(state):
    if state["stale"]:
        return "stale", "依据变化待更新"
    if not state["issues"]:
        return "complete", "资料齐全"
    if (
        not state["bills"]
        or any(bill["parse_note"] for bill in state["bills"])
        or any("提单" in issue for issue in state["issues"])
    ):
        return "pending_bill", "待上传或核对提单"
    return "pending_contract", "待生成或核对合同"


class DirectDocumentService:
    def __init__(self, engine, candidates, reader):
        self.engine, self.candidates, self.reader = engine, candidates, reader

    def query(self, body):
        if self.engine is None:
            raise ApiError(503, "业务数据库未配置")
        items = []
        start = (body.page - 1) * body.pageSize
        keyword = normalize_name(body.keyword)
        with self.engine.connect() as connection:
            rows = self.candidates.load(connection, consignee=body.consignee, limit=None)
            candidates = []
            for row in rows:
                if row["route"] != DIRECT:
                    continue
                search = " ".join(
                    [row["declaration_no"], row["record_no"], row["consignee"], *row["sales_orders"]]
                )
                if keyword and keyword not in normalize_name(search):
                    continue
                candidates.append(row)
            grouped = document_group_dao.by_numbers(connection, [r["declaration_no"] for r in candidates])
            states = {}
            counts = document_group_dao.member_counts(connection, {g["id"] for g in grouped.values()})
            if body.grouping != "all":
                candidates = [
                    r
                    for r in candidates
                    if (
                        "multiple"
                        if r["declaration_no"] in grouped
                        and counts.get(grouped[r["declaration_no"]]["id"], 0) > 1
                        else "single"
                    )
                    == body.grouping
                ]
            total = len(candidates)
            selected = candidates[start : start + body.pageSize] if body.status == "all" else candidates
            for row in selected:
                group = grouped.get(row["declaration_no"])
                if group:
                    context, linked = DocumentGroupSource(self.candidates).load(connection, group["id"])
                    if group["id"] not in states:
                        states[group["id"]] = self.reader.state(connection, context, linked)
                    state = states[group["id"]]
                else:
                    context, linked = DirectDocumentSource.context(row)
                    state = self.reader.state(connection, context, linked)
                status, label = progress(state)
                if body.status != "all" and body.status != status:
                    continue
                reason = context["document_issue"]
                items.append(
                    DirectDocumentRow(
                        groupId=group["id"] if group else None,
                        groupNo=group["group_no"] if group else "",
                        createGroup=Action(
                            allowed=not group and not reason,
                            reason=f"已在资料组 {group['group_no']}" if group else reason,
                        ),
                        declarationNo=row["declaration_no"],
                        recordNo=row["record_no"],
                        salesOrders=row["sales_orders"],
                        consignee=row["consignee"],
                        exportCompany=row["export_company"],
                        currency=row["currency"],
                        amount=str(money(row["amount"])) if row["amount"] is not None else "",
                        billLabel="已上传" if state["bills"] else "待上传",
                        contractLabel="需重新生成"
                        if state["stale"]
                        else ("已生成" if state["contracts"] else "待生成"),
                        status=status,
                        statusLabel=label,
                        edit=Action(allowed=not reason, reason=reason),
                    )
                )
        return DirectDocumentList(
            items=items if body.status == "all" else items[start : start + body.pageSize],
            total=total if body.status == "all" else len(items),
            page=body.page,
            pageSize=body.pageSize,
        )

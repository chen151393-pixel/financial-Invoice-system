"""手动创建资料组、查询与详情；同客户同币种，可跨 NS 申报抬头，不写收款表。"""

from datetime import UTC, datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy.exc import IntegrityError

from backend.core import write_lock
from backend.core.errors import ApiError
from backend.core.names import normalize_name

from ..dao import document_group_dao as dao
from ..policy.amount_policy import money
from ..policy.document_group_basis_policy import update_reason
from ..policy.route_policy import DIRECT
from ..vo.batch_vo import Action
from ..vo.document_group_vo import DocumentGroup, DocumentGroupMember
from .direct_document_service import progress
from .document_group_source import DocumentGroupSource


class DocumentGroupService:
    def __init__(self, engine, candidates, reader):
        self.engine, self.candidates, self.reader = engine, candidates, reader
        self.source = DocumentGroupSource(candidates)

    def _require_engine(self):
        if self.engine is None:
            raise ApiError(503, "业务数据库未配置")

    def create(self, body, owner):
        self._require_engine()
        if owner.startswith("service:"):
            raise ApiError(403, "服务身份只读，不能创建资料组")
        numbers = sorted(set(body.declarationNos))
        if len(numbers) != len(body.declarationNos):
            raise ApiError(422, "报关单不能重复选择")
        now = datetime.now(UTC).replace(tzinfo=None)
        try:
            with write_lock.transaction(self.engine, "settlement") as connection:
                previous = dao.by_request(connection, body.requestId)
                if previous:
                    if (
                        sorted(previous["initial_declaration_nos"] or dao.numbers(connection, previous["id"]))
                        != numbers
                    ):
                        raise ApiError(409, "创建请求已用于另一组报关单，请重新打开创建窗口")
                    return self._view(connection, previous)
                rows = self.candidates.load(connection, numbers=numbers, limit=None)
                if {r["declaration_no"] for r in rows} != set(numbers):
                    raise ApiError(409, "部分报关单已没有有效的 NS 关联海关回执，请刷新后重新选择")
                if any(r["route"] != DIRECT for r in rows):
                    raise ApiError(422, "资料组只适用于直接收汇，香港中转请在香港批次办理")
                if any(r["currency_issue"] or r["amount"] is None or not r["consignee"] for r in rows):
                    raise ApiError(422, "所选报关单的收货人、币种或金额依据不完整，请先核对回执")
                if len({normalize_name(r["consignee"]) for r in rows}) != 1:
                    raise ApiError(422, "同一资料组的报关单必须对应同一个境外收货人")
                if len({r["currency"] for r in rows}) != 1:
                    raise ApiError(422, "同一资料组不能跨币种合并")
                occupied = dao.by_numbers(connection, numbers)
                if occupied:
                    first = next(iter(occupied.values()))
                    raise ApiError(409, f"报关单已在资料组 {first['group_no']} 中，请进入该组办理")
                group_id = dao.create(
                    connection,
                    dict(
                        group_no="pending-" + uuid4().hex,
                        request_id=body.requestId,
                        consignee=rows[0]["consignee"],
                        currency=rows[0]["currency"],
                        created_by=owner,
                    ),
                    numbers,
                    now,
                )
                group_no = f"DG{datetime.now(ZoneInfo('Asia/Shanghai')):%Y%m%d}-{group_id:05d}"
                dao.rename(connection, group_id, group_no)
                dao.adopt_documents(connection, group_id, numbers, now)
                return self._view(connection, dao.get(connection, group_id))
        except IntegrityError:
            raise ApiError(409, "报关单或创建请求已被其他操作使用，请刷新后查看资料组") from None

    def get(self, group_id):
        self._require_engine()
        with self.engine.connect() as connection:
            group = dao.get(connection, group_id)
            if group is None:
                raise ApiError(404, "直接收汇资料组不存在")
            return self._view(connection, group)

    def query(self, body):
        self._require_engine()
        from .document_group_query import query_groups

        return query_groups(self, body)

    def _view(self, connection, group, *, loaded=None, state=None):
        if loaded is None:
            group = dao.resolve(connection, group["id"])
        if group is None:
            raise ApiError(404, "资料组不存在或后继关系异常")
        context, rows = loaded if loaded is not None else self.source.load(connection, group["id"])
        state = state if state is not None else self.reader.state(connection, context, rows)
        status, label = progress(state)
        if context["document_issue"]:
            status, label = "stale", "依据变化待更新"
        return DocumentGroup(
            id=group["id"],
            groupNo=group["group_no"],
            consignee=group["consignee"],
            currency=group["currency"],
            amount=str(money(context["declared_total"])),
            members=[
                DocumentGroupMember(
                    declarationNo=r["declaration_no"],
                    recordNo=r["record_no"],
                    exportDate=str(r["export_date"]) if r["export_date"] else "",
                    consignee=r["consignee"],
                    exportCompany=r["export_company"],
                    currency=r["currency"],
                    amount=str(money(r["amount"])) if r["amount"] is not None else "",
                    salesOrders=r["sales_orders"],
                )
                for r in rows
            ],
            kind="single" if len(rows) == 1 else "multiple",
            merge=Action(
                allowed=len(rows) == 1 and not context["document_issue"],
                reason=context["document_issue"]
                or ("多票资料组不能再次并入其他组" if len(rows) != 1 else ""),
            ),
            package=Action(allowed=not state["issues"], reason=state["issues"][0] if state["issues"] else ""),
            packageUrl=f"/api/settlement/direct-document-groups/{group['id']}/package",
            status=status,
            statusLabel=label,
            edit=Action(allowed=not context["document_issue"], reason=context["document_issue"]),
            updateSource=Action(
                allowed=bool(context["document_issue"]) and not update_reason(rows),
                reason=update_reason(rows)
                or ("当前来源一致，无需更新" if not context["document_issue"] else ""),
            ),
            createdBy=group["created_by"],
            createdAt=group["created_at"].isoformat(),
        )

    def ensure_single(self, number, owner):
        """首次办理时建单票组；并发、重试和旧单票入口均返回当前归属。"""
        self._require_engine()
        if owner.startswith("service:"):
            raise ApiError(403, "服务身份只读，不能办理资料")
        from ..dto.document_group_dto import CreateDocumentGroup

        with self.engine.connect() as connection:
            existing = dao.by_numbers(connection, [number]).get(number)
            if existing:
                return self._view(connection, existing)
        try:
            return self.create(CreateDocumentGroup(requestId=str(uuid4()), declarationNos=[number]), owner)
        except ApiError as error:
            if error.status != 409:
                raise
            with self.engine.connect() as connection:
                existing = dao.by_numbers(connection, [number]).get(number)
                if existing:
                    return self._view(connection, existing)
            raise

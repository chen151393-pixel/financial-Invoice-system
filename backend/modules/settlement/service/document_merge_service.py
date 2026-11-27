"""从单票发起资料合并：不可变预览 → 短事务复核 → 保留旧组与资料并创建后继组。"""

import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy.exc import IntegrityError

from backend.core import write_lock
from backend.core.errors import ApiError
from backend.core.names import normalize_name
from backend.modules.review.public import settlement_declaration_lines

from ..dao import bill_dao, contract_dao
from ..dao import document_group_dao as dao
from ..dto.document_reference import DocumentGroupRef
from ..policy import document_merge_policy as rules
from ..policy.amount_policy import money
from ..policy.consignee_policy import consignee_key
from ..policy.contract_policy import document_key, plan
from ..vo.batch_vo import Action
from ..vo.document_group_vo import DocumentGroupMember
from ..vo.document_merge_vo import DocumentMergeCandidates, DocumentMergePreview, MergeCandidate


def member(row):
    return dict(
        declarationNo=row["declaration_no"],
        recordNo=row["record_no"],
        consignee=row["consignee"],
        exportCompany=row["export_company"],
        currency=row["currency"],
        amount=str(money(row["amount"])) if row["amount"] is not None else "",
        salesOrders=row["sales_orders"],
        exportDate=str(row["export_date"]) if row["export_date"] else "",
    )


class DocumentMergeService:
    def __init__(self, groups):
        self.groups = groups
        self.engine, self.candidates, self.reader = groups.engine, groups.candidates, groups.reader

    def _source(self, connection, number):
        rows = self.candidates.load(connection, numbers=[number], limit=None)
        if len(rows) != 1:
            raise ApiError(404, "未找到本单的当前有效 NS 关联海关回执")
        if rows[0]["route"] != "direct":
            raise ApiError(409, "香港中转请在香港批次办理资料")
        return rows[0]

    def query(self, body):
        self.groups._require_engine()
        with self.engine.connect() as connection:
            display = self.candidates.display_names(connection)
            source = self._source(connection, body.sourceDeclarationNo)
            rows = [
                r
                for r in self.candidates.load(connection, consignee=source["consignee"], limit=None)
                if r["route"] == "direct"
                and consignee_key(r["consignee"]) == consignee_key(source["consignee"])
                and r["currency"] == source["currency"]
            ]
            occupied = dao.by_numbers(connection, [r["declaration_no"] for r in rows])
            counts = dao.member_counts(connection, {g["id"] for g in occupied.values()})
            source_scope = (
                DocumentGroupRef(occupied[body.sourceDeclarationNo]["id"])
                if body.sourceDeclarationNo in occupied
                else body.sourceDeclarationNo
            )
            source_bills = bill_dao.active(connection, source_scope)
            source_shas = {b["sha256"] for b in source_bills}
            source_nos = {normalize_name(b["bl_no"]) for b in source_bills if b["bl_no"]}
            keyword = normalize_name(body.keyword)
            items = []
            source_view = None
            for row in rows:
                number = row["declaration_no"]
                group = occupied.get(number)
                reason = rules.eligibility(row, group, counts.get(group["id"], 0) if group else 0)
                scope = DocumentGroupRef(group["id"]) if group else number
                shared = any(
                    b["sha256"] in source_shas or normalize_name(b["bl_no"]) in source_nos
                    for b in bill_dao.active(connection, scope)
                )
                item = MergeCandidate(
                    **member(display.display_consignee(row)),
                    groupId=group["id"] if group else None,
                    groupNo=group["group_no"] if group else "",
                    source=number == body.sourceDeclarationNo,
                    sharedBill=shared,
                    select=Action(allowed=not reason, reason=reason),
                )
                if item.source:
                    source_view = item
                search = " ".join(
                    [number, row["record_no"], row["consignee"], row["export_company"], *row["sales_orders"]]
                )
                if keyword and keyword not in normalize_name(search):
                    continue
                if body.exportFrom and (not row["export_date"] or row["export_date"] < body.exportFrom):
                    continue
                if body.exportTo and (not row["export_date"] or row["export_date"] > body.exportTo):
                    continue
                items.append(item)
            if source_view is None:
                raise ApiError(409, "本单收货人或币种依据不完整，请先核对")
            items.sort(key=lambda r: (not r.source, not r.sharedBill, r.exportDate, r.declarationNo))
            start = (body.page - 1) * body.pageSize
            return DocumentMergeCandidates(
                source=source_view,
                items=items[start : start + body.pageSize],
                total=len(items),
                page=body.page,
                pageSize=body.pageSize,
            )

    def preview(self, body):
        self.groups._require_engine()
        with self.engine.connect() as connection:
            return self._preview(connection, body)[0]

    def _preview(self, connection, body):
        display = self.candidates.display_names(connection)
        source = self._source(connection, body.sourceDeclarationNo)
        numbers = sorted(set(body.declarationNos))
        rows = self.candidates.load(connection, numbers=numbers, limit=None)
        rows.sort(key=lambda r: r["declaration_no"])
        owned = dao.by_numbers(connection, list(set(numbers + [body.sourceDeclarationNo])))
        counts = dao.member_counts(connection, {g["id"] for g in owned.values()})
        source_scope = (
            DocumentGroupRef(owned[body.sourceDeclarationNo]["id"])
            if body.sourceDeclarationNo in owned
            else body.sourceDeclarationNo
        )
        source_bills = bill_dao.active(connection, source_scope)
        shared = body.sharedBillId
        if shared is None:
            shared = source_bills[0]["id"] if len(source_bills) == 1 else 0
        chosen = next((b for b in source_bills if b["id"] == shared), None)
        conditions = rules.checks(
            source, numbers, len(body.declarationNos), rows, owned, counts, not shared or chosen is not None
        )
        allowed = all(c["passed"] for c in conditions)
        bills, contracts = [], []
        scopes = {DocumentGroupRef(owned[n]["id"]) if n in owned else n for n in numbers}
        for scope in sorted(scopes, key=str):
            bills.extend(bill_dao.active(connection, scope))
            contracts.extend(contract_dao.of_batch(connection, scope))
        bills.sort(key=lambda r: r["id"])
        contracts.sort(key=lambda r: r["id"])
        common = len(rows) == len(numbers) and all(
            r["currency"] == source["currency"] and r["amount"] is not None for r in rows
        )
        total = sum((r["amount"] for r in rows), Decimal(0)) if common else None
        planned = []
        if common:
            shared_bills = [{**b, "declaration_nos": numbers} if b["id"] == shared else b for b in bills]
            lines = settlement_declaration_lines(connection, numbers)
            planned, _ = plan(
                dict(
                    currency=source["currency"],
                    declared_total=total,
                    document_kind="direct",
                    document_group_id=True,
                ),
                rows,
                lines,
                shared_bills,
                lead_days=self.reader.lead_days,
            )
        signature = dict(
            source=source,
            numbers=numbers,
            owned=owned,
            counts=counts,
            bills=bills,
            contracts=contracts,
            planned=planned,
            sharedBillId=shared,
        )
        token = hashlib.sha256(
            json.dumps(signature, ensure_ascii=False, sort_keys=True, default=str).encode()
        ).hexdigest()
        preview = DocumentMergePreview(
            selected=[DocumentGroupMember(**member(display.display_consignee(r))) for r in rows],
            selectedCount=len(numbers),
            currency=source["currency"],
            amount=str(money(total)) if total is not None else "",
            checks=conditions,
            merge=Action(
                allowed=allowed,
                reason="；".join(c["label"] + "：" + c["detail"] for c in conditions if not c["passed"]),
            ),
            token=token,
            sourceBills=[
                dict(id=b["id"], blNo=b["bl_no"] or "", fileName=b["file_name"]) for b in source_bills
            ],
            sharedBillId=shared,
            existingBillCount=len(bills),
            existingContractCount=len(contracts),
            contracts=[
                dict(
                    key=document_key(p),
                    contractNo=p["contract_no"],
                    sellerName=p.get("seller_name", ""),
                    declarationNos=p["declaration_nos"],
                    currency=source["currency"],
                    amount=str(money(p["amount"])),
                )
                for p in planned
            ],
        )
        return preview, rows, owned

    def result(self, request_id):
        """按原请求查已提交结果；未查到返回空，客户端仍应使用原请求重试。"""
        self.groups._require_engine()
        with self.engine.connect() as connection:
            group = dao.by_request(connection, request_id)
            return self.groups._view(connection, group) if group else None

    def merge(self, body, owner):
        self.groups._require_engine()
        if owner.startswith("service:"):
            raise ApiError(403, "服务身份只读，不能合并资料组")
        numbers = sorted(set(body.declarationNos))
        now = datetime.now(UTC).replace(tzinfo=None)
        try:
            with write_lock.transaction(self.engine, "settlement") as connection:
                previous = dao.by_request(connection, body.requestId)
                if previous:
                    original = previous["initial_declaration_nos"] or dao.numbers(connection, previous["id"])
                    if sorted(original) != numbers:
                        raise ApiError(409, "该合并请求已用于其他报关单，请重新核对")
                    return self.groups._view(connection, previous)
                preview, rows, owned = self._preview(connection, body)
                if not preview.merge.allowed:
                    raise ApiError(409, "不能合并资料：" + preview.merge.reason)
                if preview.token != body.previewToken:
                    raise ApiError(409, "预览后报关依据、资料或归属已变化，请刷新预览后再合并")
                ungrouped = [n for n in numbers if n not in owned]
                target = dao.create(
                    connection,
                    dict(
                        group_no="pending-" + uuid4().hex,
                        request_id=body.requestId,
                        consignee=rows[0]["consignee"],
                        currency=rows[0]["currency"],
                        created_by=owner,
                        initial_declaration_nos=numbers,
                    ),
                    ungrouped,
                    now,
                )
                dao.rename(
                    connection, target, f"DG{datetime.now(ZoneInfo('Asia/Shanghai')):%Y%m%d}-{target:05d}"
                )
                dao.move_single_groups(
                    connection, target, sorted({g["id"] for g in owned.values()}), now, owner
                )
                dao.adopt_documents(connection, target, ungrouped, now)
                if preview.sharedBillId:
                    dao.share_bill(connection, preview.sharedBillId, numbers, now, owner)
                return self.groups._view(connection, dao.get(connection, target))
        except IntegrityError:
            raise ApiError(409, "资料归属已被其他操作修改，请刷新后重新核对") from None

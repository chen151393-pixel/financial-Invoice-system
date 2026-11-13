"""海关回执用例：导入（解析 → 保存/换版 → 比对）、列表查询与重新匹配。

文件解析在事务外完成；写入只涉及 review 自己的回执表，与海关审核共用账本锁，防止导入换版与双审核放行交错。
NS 报关单经 source 公开门面在同一连接中只读获取。
"""

import math
from datetime import UTC, datetime

from sqlalchemy.exc import SQLAlchemyError

from backend.core import write_lock
from backend.core.errors import ApiError
from backend.core.search_terms import search_terms
from backend.modules.source.public import declarations_by_number

from ..dao import customs_receipt_dao as dao
from ..mapper.customs_receipt_mapper import consignee, receipt
from ..policy.customs_match_policy import STATUS_LABELS, compare
from ..vo.customs_receipt_vo import (
    CustomsCounts,
    CustomsImportResult,
    CustomsReceiptList,
    ImportedDeclaration,
    RematchResult,
)
from .customs_approval_service import approval_view
from .customs_receipt_parser import parse

STATUS_FILTERS = {
    "all": (),
    "matched": ("matched", "split_matched"),
    "different": ("different",),
    "ns_missing": ("ns_missing", "ns_duplicate"),
}
RESULT_LABELS = {"created": "新增", "replaced": "已更新", "unchanged": "内容未变"}
REMATCH_BATCH = 200


def _now():
    return datetime.now(UTC).replace(tzinfo=None)


def _require_operator(owner):
    if owner.startswith("service:"):
        raise ApiError(403, "服务身份只读，不能导入或重新匹配海关回执")


def _match_values(ns_by_number, number, items, now):
    status, ns_id, result = compare(ns_by_number.get(number, []), items)
    return {"ns_declaration_id": ns_id, "match_status": status, "match_result": result, "matched_at": now}


class CustomsReceiptService:
    def __init__(self, engine):
        self.engine = engine

    def _require_engine(self):
        if self.engine is None:
            raise ApiError(503, "业务数据库未配置")

    def import_file(self, body, owner):
        _require_operator(owner)
        self._require_engine()
        parsed = parse(body.filename, body.content)
        now = _now()
        try:
            with write_lock.transaction(self.engine) as connection:
                outcomes = self._save(connection, parsed["declarations"], body.filename, owner, now)
        except SQLAlchemyError:
            raise ApiError(503, "海关回执保存失败，请检查业务数据库及迁移状态") from None
        counts = {key: sum(1 for o in outcomes if o.result == key) for key in RESULT_LABELS}
        return CustomsImportResult(
            fileName=body.filename,
            rows=parsed["rows"],
            columns=parsed["columns"],
            ignoredColumns=parsed["ignored"],
            declarations=outcomes,
            **counts,
        )

    def _save(self, connection, declarations, filename, owner, now):
        numbers = [d["declaration_no"] for d in declarations]
        heads = dao.heads_by_numbers(connection, numbers, lock=True)
        ns_by_number = declarations_by_number(connection, numbers)
        outcomes = []
        for declaration in declarations:
            number = declaration["declaration_no"]
            head = heads.get(number)
            match = _match_values(ns_by_number, number, declaration["lines"], now)
            if head and head["content_sha256"] == declaration["content_sha256"]:
                result, revision = "unchanged", head["revision"]
                dao.update_head(connection, head["id"], match, now)
            else:
                values = {
                    "content_sha256": declaration["content_sha256"],
                    "export_date": declaration["export_date"],
                    "consignee": declaration["consignee"],
                    "file_name": filename,
                    "imported_by": owner,
                    "imported_at": now,
                    **match,
                }
                if head:
                    result, revision = "replaced", head["revision"] + 1
                    dao.update_head(connection, head["id"], {**values, "revision": revision}, now)
                    receipt_id = head["id"]
                else:
                    result, revision = "created", 1
                    receipt_id = dao.insert_head(
                        connection, {**values, "declaration_no": number, "revision": revision}, now
                    )
                dao.insert_lines(connection, receipt_id, revision, declaration["lines"], now)
            saved = {
                "consignee": declaration["consignee"] if result != "unchanged" else head["consignee"],
                "ns_declaration_id": match["ns_declaration_id"],
            }
            outcomes.append(
                ImportedDeclaration(
                    declarationNo=number,
                    itemCount=len(declaration["lines"]),
                    result=result,
                    resultLabel=RESULT_LABELS[result],
                    status=match["match_status"],
                    statusLabel=STATUS_LABELS[match["match_status"]],
                    consignee=consignee(saved, match["match_result"].get("nsRecordNo", "")),
                )
            )
        return outcomes

    def browse(self, query):
        self._require_engine()
        filters = {
            "numbers": search_terms(query.declarationNo),
            "name": query.name.strip(),
            "consignee": query.consignee.strip(),
            "export_from": query.exportFrom,
            "export_to": query.exportTo,
        }
        try:
            with self.engine.connect() as connection:
                counts = dao.status_counts(connection, filters)
                items = dao.item_count(connection, filters)
                total, heads = dao.page(
                    connection,
                    filters,
                    STATUS_FILTERS[query.status],
                    (query.page - 1) * query.pageSize,
                    query.pageSize,
                )
                lines = dao.current_lines(connection, [head["id"] for head in heads])
                views = []
                for head in heads:
                    view, ns_id, _, status, result = approval_view(connection, head, lines[head["id"]])
                    current = {
                        **head,
                        "ns_declaration_id": ns_id,
                        "match_status": status,
                        "match_result": result,
                    }
                    views.append(receipt(current, lines[head["id"]], view))
        except SQLAlchemyError:
            raise ApiError(503, "海关回执读取失败，请检查业务数据库及迁移状态") from None
        return CustomsReceiptList(
            items=views,
            counts=CustomsCounts(
                receipts=sum(counts.values()),
                items=items,
                # 明细一致含拆行/合并一致，与 status=matched 筛选范围相同；splitMatched 为其中拆行部分
                matched=counts.get("matched", 0) + counts.get("split_matched", 0),
                splitMatched=counts.get("split_matched", 0),
                different=counts.get("different", 0),
                nsMissing=counts.get("ns_missing", 0) + counts.get("ns_duplicate", 0),
            ),
            total=total,
            page=query.page,
            pageSize=query.pageSize,
            pages=max(1, math.ceil(total / query.pageSize)),
        )

    def rematch(self, body, owner):
        """按当前 NS 报关单重新比对；不改动回执内容与版本。"""
        _require_operator(owner)
        self._require_engine()
        try:
            with self.engine.connect() as connection:
                targets = dao.ids(connection, body.ids or None)
            if body.ids and len(targets) != len(body.ids):
                raise ApiError(404, "部分海关回执不存在，请刷新列表")
            # 分批短事务，避免全部重新匹配长时间占用账本锁。
            for start in range(0, len(targets), REMATCH_BATCH):
                batch = [row["id"] for row in targets[start : start + REMATCH_BATCH]]
                with write_lock.transaction(self.engine) as connection:
                    self._rematch_batch(connection, batch, _now())
        except SQLAlchemyError:
            raise ApiError(503, "重新匹配失败，请检查业务数据库及迁移状态") from None
        return RematchResult(rematched=len(targets))

    def _rematch_batch(self, connection, receipt_ids, now):
        heads = dao.ids(connection, receipt_ids, lock=True)
        lines = dao.current_lines(connection, [head["id"] for head in heads])
        ns_by_number = declarations_by_number(connection, [head["declaration_no"] for head in heads])
        for head in heads:
            match = _match_values(ns_by_number, head["declaration_no"], lines[head["id"]], now)
            dao.update_head(connection, head["id"], match, now)

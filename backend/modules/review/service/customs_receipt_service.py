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
from backend.modules.identity.public import actor_names
from backend.modules.source.public import declarations_by_number

from ..dao import customs_receipt_dao as dao
from ..mapper.customs_receipt_mapper import consignee, import_source, receipt
from ..policy.customs_match_policy import DIFFERENCE_KINDS, STATUS_LABELS, compare, difference_kinds
from ..vo.customs_receipt_vo import (
    CustomsCounts,
    CustomsImportHistory,
    CustomsImportResult,
    CustomsReceiptList,
    ImportedDeclaration,
    RematchResult,
)
from .approval_progress_reader import read_progress
from .customs_approval_service import approval_views, approved_receipt_ids
from .customs_receipt_parser import parse

STATUS_FILTERS = {
    "all": (),
    "matched": ("matched", "split_matched"),
    "different": ("different",),
    "ns_missing": ("ns_missing", "ns_duplicate"),
    "approved": (),
}
# 差异类型：数量、单位、总价不一致及品名缺行，一张回执可同时出现在多类中。
KIND_FILTERS = tuple(DIFFERENCE_KINDS)
RESULT_LABELS = {"created": "新增", "replaced": "已更新", "unchanged": "内容未变"}
REMATCH_BATCH = 200


def _now():
    return datetime.now(UTC).replace(tzinfo=None)


def _require_operator(owner):
    if owner.startswith("service:"):
        raise ApiError(403, "服务身份只读，不能导入或重新匹配海关回执")


def _match_values(ns_by_number, number, items, now):
    status, ns_id, result = compare(ns_by_number.get(number, []), items)
    return {
        "ns_declaration_id": ns_id,
        "match_status": status,
        "match_result": result,
        "matched_at": now,
        **difference_kinds(result),
    }


def _changed(head, match):
    """保存的比对结论与本次结果是否不同（比对时间不算变化）。"""
    return any(head[key] != value for key, value in match.items() if key != "matched_at")


def refresh_matches(engine):
    """后台计算调用：按当前 NS 来源与比对规则刷新全部回执的保存结论，只写有变化的回执。

    列表逐行实时比对，但概况计数与状态筛选读取保存的结论；NS 同步或规则升级后由此保持一致。
    返回更新的回执张数。
    """
    with engine.connect() as connection:
        targets = [row["id"] for row in dao.ids(connection)]
    changed = 0
    for start in range(0, len(targets), REMATCH_BATCH):
        with write_lock.transaction(engine) as connection:
            changed += _rematch_batch(
                connection, targets[start : start + REMATCH_BATCH], _now(), only_changed=True
            )
    return changed


def _rematch_batch(connection, receipt_ids, now, *, only_changed=False):
    heads = dao.ids(connection, receipt_ids, lock=True)
    full = dao.heads_by_numbers(connection, [head["declaration_no"] for head in heads])
    lines = dao.current_lines(connection, [head["id"] for head in heads])
    ns_by_number = declarations_by_number(connection, [head["declaration_no"] for head in heads])
    changed = 0
    for head in heads:
        match = _match_values(ns_by_number, head["declaration_no"], lines[head["id"]], now)
        if only_changed and not _changed(full[head["declaration_no"]], match):
            continue
        dao.update_head(connection, head["id"], match, now)
        changed += 1
    return changed


class CustomsReceiptService:
    def __init__(self, engine, *, task_reader=None, events=None):
        self.engine = engine
        self.task_reader = task_reader
        self.events = events

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
                return self.save_parsed(connection, parsed, body.filename, owner, now)
        except SQLAlchemyError:
            raise ApiError(503, "海关回执保存失败，请检查业务数据库及迁移状态") from None

    def save_parsed(self, connection, parsed, filename, owner, now):
        """复用同步入库规则；异步作业将回执与完成结果放在同一事务中提交。"""
        outcomes = self._save(connection, parsed["declarations"], filename, owner, now)
        if self.events is not None:
            # 局部导入避免 public 门面加载其他 review 服务时形成初始化环。
            from ..public import CustomsReceiptsSaved

            self.events.publish(
                connection,
                CustomsReceiptsSaved(
                    consignees=tuple(declaration["consignee"] for declaration in parsed["declarations"]),
                    saved_at=now,
                ),
            )
        counts = {key: sum(1 for o in outcomes if o.result == key) for key in RESULT_LABELS}
        return CustomsImportResult(
            fileName=filename,
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
            "exact_number": query.exactDeclarationNo,
            "numbers": search_terms(query.declarationNo),
            "name": query.name.strip(),
            "consignee": query.consignee.strip(),
            "export_from": query.exportFrom,
            "export_to": query.exportTo,
        }
        try:
            with self.engine.connect() as connection:
                # 审核、回执和任务必须来自同一读视图。
                if connection.dialect.name == "mysql":
                    connection = connection.execution_options(isolation_level="REPEATABLE READ")
                counts = dao.status_counts(connection, filters)
                kinds = dao.difference_counts(connection, filters, KIND_FILTERS)
                items = dao.item_count(connection, filters)
                approved_ids = approved_receipt_ids(connection, filters)
                total, heads = dao.page(
                    connection,
                    filters,
                    STATUS_FILTERS[query.status],
                    (query.page - 1) * query.pageSize,
                    query.pageSize,
                    kind=query.difference or None,
                    approved_ids=approved_ids if query.status == "approved" else None,
                )
                lines = dao.current_lines(connection, [head["id"] for head in heads])
                progress = read_progress(
                    connection,
                    {head["id"]: (head["declaration_no"], None) for head in heads},
                    self.task_reader,
                )
                views = []
                approvals = approval_views(connection, heads, lines)
                for head in heads:
                    view, ns_id, _, status, result = approvals[head["id"]]
                    current = {
                        **head,
                        "ns_declaration_id": ns_id,
                        "match_status": status,
                        "match_result": result,
                    }
                    item = receipt(current, lines[head["id"]], view)
                    item.approvalProgress = progress[head["id"]]
                    views.append(item)
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
                approved=len(approved_ids),
                quantityMismatch=kinds["quantity_mismatch"],
                unitMismatch=kinds["unit_mismatch"],
                totalMismatch=kinds["total_mismatch"],
                lineMissing=kinds["line_missing"],
            ),
            total=total,
            page=query.page,
            pageSize=query.pageSize,
            pages=max(1, math.ceil(total / query.pageSize)),
        )

    def import_history(self, page=1, page_size=5):
        """只读导入来源记录；不受主列表筛选影响，不重算比对或审核。"""
        self._require_engine()
        try:
            with self.engine.connect() as connection:
                if connection.dialect.name == "mysql":
                    connection = connection.execution_options(isolation_level="REPEATABLE READ")
                total, rows = dao.import_history(connection, page, page_size)
                names = actor_names(connection, [row["imported_by"] for row in rows])
                items = [import_source(row, names) for row in rows]
        except SQLAlchemyError:
            raise ApiError(503, "导入记录暂时无法读取，请稍后重试") from None
        return CustomsImportHistory(
            items=items,
            total=total,
            page=page,
            pageSize=page_size,
            pages=max(1, math.ceil(total / page_size)),
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
                    _rematch_batch(connection, batch, _now())
        except SQLAlchemyError:
            raise ApiError(503, "重新匹配失败，请检查业务数据库及迁移状态") from None
        return RematchResult(rematched=len(targets))

"""手动整单关联：一张子采购单只由一张发票开具（2026-10-30 业务规则），整单保存并通过。

- 候选：不带关键字时只返回置信度最高的一张可选候选（页面默认展示其整单比对）；带关键字（至少 3 个字符）时
  返回匹配的候选列表，供用户按单号改选。有效任务行按关键字筛选后按子采购单归并，再读取整单全部有效来源行及其任务行。
  整单任一明细不在有效应开范围、开票依据变化、已有收票或已结束时整单不可选，原因显示在候选上。
- 对应：发票只有一行时整单明细都对应该行；多行时按品名等综合得分逐条定位发票行（order_group_policy.order_parts）。
- 比对：所选发票行对其对应明细的整单应开做整单比对，不再有部分开票。
- 保存：记账数量与金额由后端生成（发票少时按明细顺序记到发票为止），同一事务内写入整组分配并通过；
  发票少的明细随即按差异结束。须说明而未填写或任一校验失败时全部回滚。可选原子替换同票一条已确认分配。
"""

import hashlib
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from backend.core.errors import ApiError
from backend.modules.invoice.public import read_invoice_paper, read_invoices
from backend.modules.source.public import purchase_lines, purchase_order_lines
from backend.modules.task.public import open_lines

from ..dao import allocation_dao
from ..dto.matching_dto import GroupConfirmBody
from ..mapper import allocation_mapper as mapper
from ..policy.comparison_policy import order_reference, text, tier
from ..policy.group_comparison_policy import compare_group
from ..policy.order_group_policy import fit_all, order_parts, order_shares, share_snapshot
from ..vo.manual_order_vo import ManualOrderCandidate, ManualOrderCandidates
from . import group_plan_service, group_view_service, ledger_service

# 按关键字查询时最多返回张数；超出时提示输入更完整的单号
LIMIT = 20
# 关键字最短长度：过短的关键字会命中大量子采购单，容易误选
MIN_KEYWORD = 3


def _invoice_item(connection, invoice_id, item_id):
    found = read_invoices(connection, [invoice_id])
    item = next((row for row in found[0]["items"] if row["id"] == item_id), None) if found else None
    if item is None:
        raise ApiError(404, "发票行不存在或不属于该发票")
    return found[0], item


def _order(connection, order_ids):
    """({子采购单 ID: {子采购行 ID: 上下文}}, 开票依据, 任务行)；任务行按整单全部明细读取，含已开完的行。"""
    grouped, bases = group_plan_service.order_contexts(connection, order_ids, None)
    line_ids = [line_id for lines in grouped.values() for line_id in lines]
    tasks = {row["purchase_line_id"]: row for row in open_lines(connection, line_ids)} if line_ids else {}
    return grouped, bases, tasks


def _searchable(line, task):
    return " ".join(
        str(value or "")
        for value in (
            line.get("order_no"),
            line.get("parent_order_no"),
            line.get("supplier_name"),
            line.get("declaration_name"),
            line.get("item_name"),
            (task or {}).get("record_no"),
        )
    ).casefold()


def candidates(connection, query):
    """备注命中与置信度高的子采购单排前；支持子采购单号、母单号、供应商、品名、报关单号搜索。

    不带关键字时 rows 只含置信度最高且可选、置信度大于 0 的一张（没有则为空），total 为全部候选张数。
    """
    keyword = query.keyword.strip().casefold()
    if keyword and len(keyword) < MIN_KEYWORD:
        raise ApiError(400, f"请至少输入 {MIN_KEYWORD} 个字符查询子采购单")
    invoice, item = _invoice_item(connection, int(query.invoiceId), int(query.invoiceItemId))
    # 已开完的子采购单整单没有剩余应开，不作候选；部分开票的单仍有未结束任务行。
    tasks = {row["purchase_line_id"]: row for row in open_lines(connection)}
    contexts = purchase_lines(connection, list(tasks))
    order_ids = sorted(
        {
            line["purchase_order_id"]
            for line_id, line in contexts.items()
            if not keyword or keyword in _searchable(line, tasks[line_id])
        }
    )
    if not order_ids:
        return ManualOrderCandidates(rows=[], total=0)
    grouped, bases, order_tasks = _order(connection, order_ids)
    tax = (read_invoice_paper(connection, invoice["id"]) or {"items": {}})["items"].get(item["id"], {})
    rows = [
        _candidate(invoice, item, tax.get("tax_amount"), order_id, lines, bases, order_tasks)
        for order_id, lines in grouped.items()
    ]
    rows.sort(key=lambda row: (-Decimal(row.confidence), not row.orderMatched, row.orderNo))
    if not keyword:
        # 默认只展示一张：整单不可选或与发票行毫无相符项时不作默认，由用户按单号查询
        best = next((row for row in rows if not row.block and Decimal(row.confidence) > 0), None)
        return ManualOrderCandidates(rows=[best] if best else [], total=len(rows))
    return ManualOrderCandidates(rows=rows[:LIMIT], total=len(rows))


def _mapping(invoice, item, lines, tasks, bases, items=None):
    """整单明细对应到发票行并按发票压缩：返回 (分配行, 阻断原因)；分配行带 share_quantity / share_amount。

    items 为 {发票行 ID: 发票行}，默认取发票全部有效行；保存时传入扣除其他已确认分配后的可用量。
    """
    active = [row for row in invoice["items"] if row["is_active"]]
    items = items or {row["id"]: row for row in active}
    shares, block = order_shares(invoice, lines, tasks, bases)
    if block:
        return [], block
    if len(active) == 1:
        parts = [
            {
                "invoice_item_id": item["id"],
                "purchase_line_id": key,
                "purchase_basis_id": bases[key]["id"],
                "quantity": quantity,
                "purchase_quantity": quantity,
                "amount": amount,
            }
            for key, (quantity, amount) in shares.items()
        ]
    else:
        parts, block = order_parts(invoice, active, lines, tasks, bases, None)
        if block:
            return [], block
    if item["id"] not in {part["invoice_item_id"] for part in parts}:
        return [], "该子采购单的明细按品名对应不到所选发票行，请选择对应的发票行"
    return fit_all(parts, items), ""


def _item_checks(invoice, item, tax, lines, rows):
    """所选发票行对其对应明细整单应开的比对。"""
    own = [
        (lines[row["purchase_line_id"]], row["share_quantity"], row["share_amount"])
        for row in rows
        if row["invoice_item_id"] == item["id"]
    ]
    return compare_group(invoice, item, tax, own)


def _candidate(invoice, item, tax, order_id, lines, bases, tasks):
    rows, block = _mapping(invoice, item, lines, tasks, bases)
    first = next(iter(lines.values()))
    shown = sorted(lines)
    checks, confidence = _item_checks(invoice, item, tax, lines, rows) if rows else ([], Decimal(0))
    units = {lines[key].get("unit_name") or lines[key].get("unit") or "" for key in shown}
    currencies = {lines[key]["currency"] or "" for key in shown}
    return ManualOrderCandidate(
        purchaseOrderId=str(order_id),
        orderNo=first["order_no"] or "",
        parentOrderNo=first["parent_order_no"] or "",
        supplier=first["supplier_name"] or "",
        company=first["company_name"] or "",
        recordNumbers=sorted(
            {tasks[key]["record_no"] for key in lines if key in tasks and tasks[key]["record_no"]}
        ),
        currency=next(iter(currencies)) if len(currencies) == 1 else "多币种",
        unit=next(iter(units)) if len(units) == 1 else "多单位",
        remainingQuantity=text(sum((row["share_quantity"] for row in rows), Decimal(0)))
        if rows and len(units) == 1
        else None,
        remainingAmount=text(sum((row["share_amount"] for row in rows), Decimal(0)))
        if rows and len(currencies) == 1
        else None,
        orderMatched=bool(order_reference(invoice["remark"], first)),
        confidence=text(confidence),
        tier=tier(confidence),
        checks=mapper.check_views(checks),
        block=block,
        lines=[mapper.purchase_side(key, lines[key], tasks.get(key)) for key in shown],
    )


def _request_id(body, line_id):
    # 每条明细一条分配记录，请求编号由整次提交的 requestId 派生，重复提交只生效一次。
    return str(uuid.uuid5(body.requestId, str(line_id)))


def _fingerprint(body, actor):
    return hashlib.sha256((actor + body.model_dump_json()).encode()).hexdigest()


def _available(connection, invoice):
    """{发票行 ID: 发票行}，数量与金额扣除该行其他已确认分配；一票多单时按剩余容量记账。"""
    result = {}
    for row in invoice["items"]:
        if not row["is_active"]:
            continue
        used_quantity, used_amount = allocation_dao.confirmed_by_item(connection, row["id"])
        result[row["id"]] = {
            **row,
            "quantity": None if row["quantity"] is None else row["quantity"] - used_quantity,
            "amount_including_tax": None
            if row["amount_including_tax"] is None
            else row["amount_including_tax"] - used_amount,
        }
    return result


def create(service, connection, body, actor):
    """在调用方事务内保存整组分配并通过，返回发票 ID。"""
    invoice_id, item_id, order_id = int(body.invoiceId), int(body.invoiceItemId), int(body.purchaseOrderId)
    fingerprint = _fingerprint(body, actor)
    order_line_ids = sorted(row["id"] for row in purchase_order_lines(connection, [order_id]))
    if not order_line_ids:
        raise ApiError(404, "子采购单不存在或没有有效明细")
    replayed = [allocation_dao.by_request(connection, _request_id(body, key)) for key in order_line_ids]
    if any(replayed):
        if all(
            row is None or ((row["checks"] or {}).get("group") or {}).get("requestFingerprint") == fingerprint
            for row in replayed
        ):
            return invoice_id  # 同一操作重复提交，返回原结果
        raise ApiError(409, "请求编号已用于其他分配，不能复用")
    old = allocation_dao.get(connection, int(body.replaceAllocationId)) if body.replaceAllocationId else None
    if body.replaceAllocationId and (
        not old or old["status"] != "confirmed" or old["invoice_id"] != invoice_id
    ):
        raise ApiError(409, "只有本发票已确认的关联可以原子替换")
    # 先按顺序加锁（开票依据 → 任务行 → 发票 → 分配账本），再读取并写入。
    ledger_service.prepare(
        connection, sorted({*order_line_ids, *([old["purchase_line_id"]] if old else [])}), [invoice_id]
    )
    invoice, item = _invoice_item(connection, invoice_id, item_id)
    if not item["is_active"]:
        raise ApiError(409, "发票逻辑明细已停用，不能关联")
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if old:
        allocation_dao.update_status(
            connection,
            old["id"],
            {
                "status": "cancelled",
                "cancelled_by": actor,
                "cancelled_at": now,
                "cancel_reason": body.replaceReason,
            },
            now,
        )
        # 新分配的可用额度须排除刚撤销的原占用；仍在同一事务，后续失败会一起回滚。
        service._publish(connection, old["purchase_line_id"], actor, "替换时重新计算原占用")
    grouped, bases, tasks = _order(connection, [order_id])
    lines = grouped.get(order_id) or {}
    rows, block = _mapping(invoice, item, lines, tasks, bases, _available(connection, invoice))
    if block:
        raise ApiError(409, block)
    item_ids = {row["invoice_item_id"] for row in rows}
    if any(
        row["status"] == "proposed" and row["invoice_item_id"] in item_ids
        for row in allocation_dao.by_invoices(connection, [invoice_id])
    ):
        raise ApiError(409, "对应的发票行已有待审核建议，请先驳回再手动关联")
    paper = read_invoice_paper(connection, invoice_id) or {"items": {}}
    by_item = {row["id"]: row for row in invoice["items"]}
    checks = {
        key: _item_checks(
            invoice, by_item[key], (paper["items"].get(key) or {}).get("tax_amount"), lines, rows
        )[0]
        for key in item_ids
    }
    group = {
        "id": str(uuid.uuid4()),
        "orderIds": [str(order_id)],
        "manual": True,
        "requestFingerprint": fingerprint,
    }
    ids = [
        allocation_dao.insert_allocation(
            connection,
            {
                "invoice_id": invoice_id,
                "invoice_item_id": row["invoice_item_id"],
                "purchase_line_id": row["purchase_line_id"],
                "purchase_basis_id": row["purchase_basis_id"],
                "invoice_version_id": invoice["current_version_id"],
                "quantity": row["quantity"],
                "amount": row["amount"],
                # 人工关联置信度为空，页面标为“人工关联”；比对项与整单应开随记录保存
                "confidence": None,
                "checks": {
                    "items": checks[row["invoice_item_id"]],
                    "purchaseDigest": lines[row["purchase_line_id"]]["digest"],
                    "group": group,
                    "orderShare": share_snapshot(row),
                },
                "status": "proposed",
                "proposed_by": actor,
                "proposed_at": now,
                "request_id": _request_id(body, row["purchase_line_id"]),
            },
            now,
        )
        for row in rows
    ]
    inserted = [allocation_dao.get(connection, value) for value in ids]
    group_view_service.approve_rows(
        service,
        connection,
        inserted,
        GroupConfirmBody(invoiceId=str(invoice_id), invoiceVersionId=body.invoiceVersionId, note=body.note),
        actor,
    )
    if old:
        history = allocation_dao.get(connection, ids[0])["verification_history"] + [
            {
                "action": "replacement",
                "replacesAllocationId": old["id"],
                "reason": body.replaceReason,
                "actor": actor,
                "at": now.isoformat(),
            }
        ]
        allocation_dao.update_status(connection, ids[0], {"verification_history": history}, now)
    return invoice_id

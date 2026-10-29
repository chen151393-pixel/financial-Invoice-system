"""手动整单关联：候选以整张子采购单为最小单位，选中后逐条明细分配（可改小以支持部分开票），整组保存并通过。

- 候选：有效任务行按关键字筛选后按子采购单归并，再读取整单全部有效来源行及其任务行。整单任一明细不在
  有效应开范围、开票依据变化或已按差异结束时整单不可选，原因显示在候选上；已开完的明细不再列出。
- 比对：按全部可分配明细的剩余应开全额与发票行做整单比对（group_comparison_policy），保存时按实际填写重算。
- 保存：同一事务内写入整组分配（checks.group.manual 标记），随即按整单审核规则逐条通过；须说明而未填写、
  超出发票行容量等任一失败时全部回滚。可选原子替换同票一条已确认分配。
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
from ..policy.order_group_policy import order_shares
from ..vo.manual_order_vo import ManualOrderCandidate, ManualOrderCandidates
from . import group_plan_service, group_view_service, ledger_service

# 候选最多返回张数；超出时提示用关键字缩小范围
LIMIT = 50


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
    """备注命中与置信度高的子采购单排前；支持子采购单号、母单号、供应商、品名、报关单号搜索。"""
    invoice, item = _invoice_item(connection, int(query.invoiceId), int(query.invoiceItemId))
    keyword = query.keyword.strip().casefold()
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
    return ManualOrderCandidates(rows=rows[:LIMIT], total=len(rows))


def _candidate(invoice, item, tax, order_id, lines, bases, tasks):
    shares, block = order_shares(invoice, lines, tasks, bases)
    first = next(iter(lines.values()))
    shown = list(shares) if shares else sorted(lines)
    if shares:
        checks, confidence = compare_group(
            invoice, item, tax, [(lines[key], *value) for key, value in shares.items()]
        )
    else:
        checks, confidence = [], Decimal(0)
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
        remainingQuantity=text(sum((q for q, _ in shares.values()), Decimal(0)))
        if shares and len(units) == 1
        else None,
        remainingAmount=text(sum((a for _, a in shares.values()), Decimal(0)))
        if shares and len(currencies) == 1
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


def create(service, connection, body, actor):
    """在调用方事务内保存整组分配并通过，返回发票 ID。"""
    invoice_id, item_id, order_id = int(body.invoiceId), int(body.invoiceItemId), int(body.purchaseOrderId)
    fingerprint = _fingerprint(body, actor)
    submitted = {int(line.purchaseLineId): line for line in body.lines}
    positive = sorted(key for key, line in submitted.items() if line.quantity > 0)
    replayed = [allocation_dao.by_request(connection, _request_id(body, key)) for key in positive]
    if any(replayed):
        if all(
            row and ((row["checks"] or {}).get("group") or {}).get("requestFingerprint") == fingerprint
            for row in replayed
        ):
            return invoice_id  # 同一操作重复提交，返回原结果
        raise ApiError(409, "请求编号已用于其他分配，不能复用")
    order_line_ids = sorted(row["id"] for row in purchase_order_lines(connection, [order_id]))
    if not order_line_ids:
        raise ApiError(404, "子采购单不存在或没有有效明细")
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
    if any(
        row["status"] == "proposed" and row["invoice_item_id"] == item_id
        for row in allocation_dao.by_invoices(connection, [invoice_id])
    ):
        raise ApiError(409, "该发票行已有待审核建议，请先驳回再手动关联")
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
        # 新分配的剩余额度须排除刚撤销的原占用；仍在同一事务，后续失败会一起回滚。
        service._publish(connection, old["purchase_line_id"], actor, "替换时重新计算原占用")
    grouped, bases, tasks = _order(connection, [order_id])
    lines = grouped.get(order_id) or {}
    shares, block = order_shares(invoice, lines, tasks, bases)
    if block:
        raise ApiError(409, block)
    if set(submitted) != set(shares):
        raise ApiError(409, "提交的明细与子采购单当前可分配明细不一致，请刷新后重新选择")
    exceeds = any(
        submitted[key].quantity > shares[key][0] or submitted[key].amount > shares[key][1] for key in positive
    )
    tax = (read_invoice_paper(connection, invoice_id) or {"items": {}})["items"].get(item_id, {})
    checks, _ = compare_group(
        invoice,
        item,
        tax.get("tax_amount"),
        [(lines[key], submitted[key].quantity, submitted[key].amount) for key in positive],
    )
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
                "invoice_item_id": item_id,
                "purchase_line_id": key,
                "purchase_basis_id": bases[key]["id"],
                "invoice_version_id": invoice["current_version_id"],
                "quantity": submitted[key].quantity,
                "amount": submitted[key].amount,
                # 人工关联与逐行人工分配一致：置信度为空，页面标为“人工关联”；比对项随记录保存
                "confidence": None,
                "checks": {"items": checks, "purchaseDigest": lines[key]["digest"], "group": group},
                "status": "proposed",
                "proposed_by": actor,
                "proposed_at": now,
                "request_id": _request_id(body, key),
            },
            now,
        )
        for key in positive
    ]
    rows = [allocation_dao.get(connection, value) for value in ids]
    group_view_service.approve_rows(
        service,
        connection,
        rows,
        GroupConfirmBody(invoiceId=str(invoice_id), invoiceVersionId=body.invoiceVersionId, note=body.note),
        actor,
        ["超出剩余应开"] if exceeds else [],
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

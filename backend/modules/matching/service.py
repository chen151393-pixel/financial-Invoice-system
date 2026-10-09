"""候选评估与人工分配；仅保存本地关联，不调用或写回NS。"""

import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal, localcontext

from sqlalchemy.exc import SQLAlchemyError

from backend.core.errors import ApiError
from backend.modules.invoice.public import matching_invoice

from . import dao
from .policy import (
    capacity,
    compare,
    currency,
    declaration_quantity,
    item_matches,
    normalize,
    number,
    prorated_amount,
    remark_matches,
)
from .summary import matching_summary


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, default=str, ensure_ascii=False).encode()
    ).hexdigest()


def purchase_digest(order, line):
    # 同步时间更新不代表采购业务内容变化，不使已确认关系无故失效。
    return digest([dict(order), {key: value for key, value in line.items() if key != "synced_at"}])


def effective_order(order):
    result = dict(order)
    result["currency_code"] = result.get("currency_code") or result.get("parent_currency_code")
    return result


def source_digest(invoice, item, order, line):
    return digest(
        [
            {
                k: invoice.get(k)
                for k in ("id", "seller", "buyer", "currency", "sourceStatus", "sourceComplete", "gross")
            },
            item,
            purchase_digest(order, line),
        ]
    )


class MatchingService:
    def __init__(self, invoices, purchases, engine=None):
        self.invoices, self.purchases, self.engine = invoices, purchases, engine

    def summaries(self, invoice_ids, owner):
        ids = list(dict.fromkeys(int(value) for value in invoice_ids))
        if any(value > 18446744073709551615 for value in ids):
            raise ApiError(422, "发票编号超出范围")
        invoices = self.invoices.invoice_details(ids, owner)
        if self.engine is None:
            raise ApiError(503, "匹配存储未配置")
        heads, lines = self.purchases.read(owner)
        tenant = hashlib.sha256(owner.encode()).hexdigest()
        try:
            with self.engine.connect() as connection, connection.begin():
                allocations = dao.read(connection, tenant)
                links = dao.read_links(connection, tenant)
        except SQLAlchemyError:
            raise ApiError(503, "匹配状态读取失败，请检查匹配表及数据库连接") from None
        # 当前页共用一次采购和关联查询，摘要复用详情页的校验规则。
        return {
            "rows": [
                self.evaluate(invoice, heads, lines, [dict(row) for row in allocations], links=links)[
                    "summary"
                ]
                for invoice in invoices
            ]
        }

    def preview(
        self, invoice_id, owner, *, customs_no=None, purchase_query=None, invoice_line_id=None, page=1
    ):
        invoice = self.invoices.invoice_detail(invoice_id, owner)
        heads, lines = self.purchases.read(owner)
        allocations, links, storage_reason = [], [], "匹配存储未配置"
        if self.engine is not None:
            try:
                with self.engine.connect() as connection:
                    allocations = dao.read(connection, hashlib.sha256(owner.encode()).hexdigest())
                    links = dao.read_links(connection, hashlib.sha256(owner.encode()).hexdigest())
                storage_reason = ""
            except SQLAlchemyError:
                storage_reason = "匹配表不可用，请执行业务库迁移或检查连接后重试"
        return self.evaluate(
            invoice,
            heads,
            lines,
            allocations,
            storage_reason,
            customs_no=customs_no,
            links=links,
            purchase_query=purchase_query,
            invoice_line_id=invoice_line_id,
            page=page,
        )

    def evaluate(
        self,
        invoice,
        heads,
        lines,
        allocations,
        storage_reason="",
        *,
        customs_no=None,
        links=(),
        purchase_query=None,
        invoice_line_id=None,
        page=1,
        selected_pairs=None,
    ):
        heads = {h["id"]: h for h in heads}
        items = {i["id"]: i for i in invoice["lines"]}
        if invoice_line_id is not None and invoice_line_id not in items:
            raise ApiError(422, "所选发票明细不存在或无权查看")
        query = normalize(purchase_query).casefold()
        if purchase_query is not None and not query:
            raise ApiError(422, "请输入子采购单号、供应商或品名")
        selected_keys = (
            {(pair.invoiceLineId, pair.purchaseLineId) for pair in selected_pairs}
            if selected_pairs is not None
            else None
        )
        by_line = {str(line["id"]): line for line in lines}
        same = {
            key
            for key, h in heads.items()
            if normalize(invoice["seller"]) and normalize(h["supplier_name"]) == normalize(invoice["seller"])
        }
        parent_note = {
            key
            for key, h in heads.items()
            if any(
                remark_matches(invoice.get("remark"), h.get(field))
                for field in ("order_no", "verified_parent_order_no")
            )
        }
        customs_note = {
            key
            for key, h in heads.items()
            if any(
                remark_matches(customs_no or invoice.get("remark"), h.get(field))
                for field in ("customs_record_no", "customs_declaration_no")
            )
        }
        located = parent_note & customs_note if parent_note and customs_note else parent_note or customs_note
        conflicting_clues = bool(parent_note and customs_no and not customs_note) or bool(
            parent_note and customs_note and not located
        )
        if conflicting_clues:
            located = parent_note | customs_note
        for row in allocations:
            item, line = items.get(row["invoice_line_id"]), by_line.get(row["purchase_line_id"])
            order = heads.get(line["purchase_order_id"]) if line else None
            row["stale"] = not order or row["purchase_hash"] != purchase_digest(effective_order(order), line)
            if row["invoice_id"] == invoice.get("id"):
                row["stale"] = (
                    row["stale"]
                    or not item
                    or row["source_hash"] != source_digest(invoice, item, effective_order(order), line)
                )
        linked_invoice_ids = {row["invoice_id"] for row in links}
        linked_purchase_ids = {row["purchase_line_id"] for row in links}
        link_history = []
        for row in links:
            if row["invoice_id"] != invoice.get("id"):
                continue
            item, line = items.get(row["invoice_line_id"]), by_line.get(row["purchase_line_id"])
            order = heads.get(line["purchase_order_id"]) if line else None
            stale = (
                not item
                or not order
                or row["source_hash"] != source_digest(invoice, item, effective_order(order), line)
            )
            link_history.append(
                {
                    "invoiceLineId": row["invoice_line_id"],
                    "purchaseLineId": row["purchase_line_id"],
                    "orderNo": order["order_no"] if order else None,
                    "needsReview": stale,
                    "manualConfirmation": row.get("source_snapshot", {}).get("manualConfirmation", False),
                    "manualReason": row.get("source_snapshot", {}).get("manualReason", ""),
                    "warnings": row.get("source_snapshot", {}).get("warnings", []),
                }
            )
        candidates = []
        with localcontext() as ctx:
            ctx.prec = 64
            for item in invoice["lines"]:
                if invoice_line_id is not None and item["id"] != invoice_line_id:
                    continue
                named_lines = {
                    line["id"]
                    for line in lines
                    if line["purchase_order_id"] in located and item_matches(item, line)
                }
                for line in lines:
                    order = heads.get(line["purchase_order_id"])
                    if order is None:
                        continue
                    manual_selected = (
                        selected_keys is not None and (item["id"], str(line["id"])) in selected_keys
                    )
                    search_hit = bool(query) and any(
                        query in normalize(value).casefold()
                        for value in (
                            order.get("order_no"),
                            order.get("verified_parent_order_no"),
                            order.get("supplier_name"),
                            line.get("item_name"),
                            line.get("declaration_name"),
                        )
                    )
                    if selected_keys is not None:
                        if not manual_selected:
                            continue
                    elif query:
                        if not search_hit:
                            continue
                    elif not (
                        order["id"] in located
                        or (
                            not located
                            and not customs_no
                            and order["id"] in same
                            and item_matches(item, line)
                        )
                    ):
                        continue
                    if not query and selected_keys is None and named_lines and line["id"] not in named_lines:
                        continue
                    order = effective_order(order)
                    checks = compare(invoice, item, order, line)
                    source_hash = source_digest(invoice, item, order, line)
                    availability = capacity(invoice, item, order, line, allocations, source_hash)
                    if invoice.get("id") in linked_invoice_ids or str(line["id"]) in linked_purchase_ids:
                        availability.update(allowed=False, reason="已有整票关联，不能再按数量分配")
                    if conflicting_clues or (
                        parent_note and customs_note and order["id"] not in parent_note & customs_note
                    ):
                        availability.update(
                            allowed=False, reason="发票备注中的采购单与报关单线索指向不同子单，需人工核实"
                        )
                    if storage_reason:
                        reason = availability["reason"]
                        availability.update(
                            allowed=False,
                            reason=storage_reason
                            if availability["allowed"]
                            else f"{reason}；{storage_reason}",
                        )
                    quantity = Decimal(item["quantity"]) if item.get("quantity") else None
                    gross = Decimal(item["gross"]) if item.get("gross") else None
                    candidates.append(
                        {
                            "invoiceLineId": item["id"],
                            "invoiceItem": item["item"],
                            "purchaseLineId": str(line["id"]),
                            "orderNo": order["order_no"],
                            "parentOrderNo": order.get("verified_parent_order_no"),
                            "customsNo": order.get("customs_record_no"),
                            "declarationNo": order.get("customs_declaration_no"),
                            "supplier": order["supplier_name"],
                            "item": line["item_name"],
                            "declarationName": line["declaration_name"],
                            "unit": line.get("declaration_unit"),
                            "quantity": str(line["declaration_quantity"])
                            if line.get("declaration_quantity") is not None
                            else None,
                            "price": format(line["amount"] / declaration_quantity(line), ".8f")
                            if line.get("amount") is not None and declaration_quantity(line) is not None
                            else None,
                            "gross": str(line["amount"]) if line["amount"] is not None else None,
                            "currency": order["currency_code"],
                            "checks": checks,
                            "warnings": [
                                f"{check['label']}不一致：发票「{check['invoiceValue'] or '缺失'}」 / 子采购「{check['purchaseValue'] or '缺失'}」"
                                for check in checks
                                if not check["matched"]
                            ],
                            "allFieldsMatched": all(c["matched"] for c in checks),
                            "basis": "人工搜索选择"
                            if query
                            else "人工选择子采购明细"
                            if manual_selected and order["id"] not in located
                            else "备注采购订单命中"
                            if order["id"] in parent_note
                            else "备注报关单命中"
                            if order["id"] in customs_note
                            else "供应商＋报关品名",
                            "purchaseHash": purchase_digest(order, line),
                            "sourceHash": source_hash,
                            "calculatedInvoicePrice": format(gross / quantity, ".8f")
                            if quantity and gross is not None
                            else None,
                            **availability,
                        }
                    )
        candidates.sort(
            key=lambda r: (
                r["basis"] == "备注采购订单命中",
                r["allowed"],
                sum(c["matched"] for c in r["checks"]),
            ),
            reverse=True,
        )
        confident_counts = Counter(row["invoiceLineId"] for row in candidates if row["allFieldsMatched"])
        for candidate in candidates:
            count = confident_counts[candidate["invoiceLineId"]]
            candidate["matchStatus"] = (
                "报关线索冲突，待核实"
                if conflicting_clues
                else "多个高可信候选，需人工确认"
                if count > 1 and candidate["allFieldsMatched"]
                else "高可信候选，待保存前复核"
                if count == 1 and candidate["allFieldsMatched"]
                else "匹配不一致，需人工核实"
            )
        history = [
            {
                "invoiceLineId": r["invoice_line_id"],
                "purchaseLineId": r["purchase_line_id"],
                "quantity": str(r["quantity"]),
                "gross": str(r["gross"]),
                "needsReview": bool(r.get("stale")),
                "orderNo": r.get("source_snapshot", {}).get("candidate", {}).get("orderNo"),
            }
            for r in allocations
            if r["invoice_id"] == invoice.get("id")
        ]
        link_reason = (
            storage_reason
            or ("该发票已有整票关联" if link_history else "")
            or ("该发票已有数量分配" if history else "")
            or (
                "发票状态或明细待核实"
                if invoice.get("sourceStatus") != "normal" or not invoice.get("sourceComplete")
                else ""
            )
            or ("暂无可选子采购明细" if not candidates else "")
        )
        manual_link_reason = (
            storage_reason
            or ("该发票已有整票关联" if link_history else "")
            or ("该发票已有数量分配" if history else "")
            or (
                "发票明细不完整或状态不支持关联"
                if not invoice.get("sourceComplete")
                or invoice.get("sourceStatus") not in {"normal", "unknown"}
                else ""
            )
        )
        start = (page - 1) * 100 if query else 0
        return {
            "invoice": invoice,
            "purchaseCount": len(heads),
            "purchaseLineCount": len(lines),
            "sameSupplierCount": len(same),
            "remarkOrderCount": len(parent_note),
            "candidateCount": len(candidates),
            "fieldMatchCount": sum(c["allFieldsMatched"] for c in candidates),
            "highConfidenceCount": 0 if conflicting_clues else sum(c["allFieldsMatched"] for c in candidates),
            "candidates": candidates[start : start + 100],
            "page": page if query else 1,
            "hasNext": start + 100 < len(candidates),
            "truncated": len(candidates) > 100,
            "snapshot": digest(
                [
                    invoice,
                    [dict(h) for h in heads.values()],
                    [dict(line) for line in lines],
                    allocations,
                    links,
                    customs_no,
                ]
            ),
            "allocations": history,
            "links": link_history,
            "summary": matching_summary(invoice, candidates, link_history, history, conflicting_clues),
            "linkAllowed": not link_reason,
            "manualLinkAllowed": not manual_link_reason,
            "manualLinkReason": manual_link_reason or "可选择子采购明细，核对差异后人工确认",
            "linkReason": link_reason or "选择候选明细后，由后端逐行复核整票关联",
            "allowed": any(c["allowed"] for c in candidates),
            "reason": storage_reason
            or (
                "该报关单号未定位到已同步的关联子采购单，请核对号码或同步来源。"
                if customs_no and not customs_note and not parent_note
                else "候选须核实销售方主体、币种及来源；可整票关联或按行分配，不写回NS。"
            ),
            "priceReason": "发票含税单价为行价税合计÷数量；采购金额与子采购报关数量配对核对。报关单外币金额不参与发票金额比较。",
        }

    def confirm(self, invoice_id, body, owner):
        if self.engine is None or self.engine.dialect.name != "mysql":
            raise ApiError(503, "确认分配需要已迁移的MySQL业务库")
        tenant = hashlib.sha256(owner.encode()).hexdigest()
        request_hash = digest(
            [invoice_id, body.invoiceLineId, body.purchaseLineId, body.quantity, body.customsNo]
        )
        try:
            with self.engine.begin() as connection:
                invoice = matching_invoice(connection, invoice_id, owner)
                heads, lines = self.purchases.read(owner, connection)
                rows = dao.read(connection, tenant, lock=True)
                links = dao.read_links(connection, tenant, lock=True)
                old = next((r for r in rows if r["request_id"] == str(body.requestId)), None)
                if old:
                    if old["request_hash"] != request_hash:
                        raise ApiError(409, "请求标识已用于其他分配，请重新预览")
                    return {
                        "message": "该分配已经保存，未重复占用",
                        "quantity": str(old["quantity"]),
                        "gross": str(old["gross"]),
                    }
                result = self.evaluate(invoice, heads, lines, rows, customs_no=body.customsNo, links=links)
                if result["snapshot"] != body.snapshot:
                    raise ApiError(409, "来源数据或已分配额度发生变化，请刷新候选后重新确认")
                candidate = next(
                    (
                        c
                        for c in result["candidates"]
                        if c["invoiceLineId"] == body.invoiceLineId
                        and c["purchaseLineId"] == body.purchaseLineId
                    ),
                    None,
                )
                if candidate is None or not candidate["allowed"]:
                    raise ApiError(422, candidate["reason"] if candidate else "所选候选不存在或无权确认")
                with localcontext() as ctx:
                    ctx.prec = 64
                    quantity = Decimal(body.quantity)
                    if quantity <= 0 or quantity > Decimal(candidate["suggestedQuantity"]):
                        raise ApiError(422, "分配数量须大于零且不超过两侧剩余数量")
                    purchase_line = next(line for line in lines if str(line["id"]) == body.purchaseLineId)
                    used_quantity = sum(
                        (
                            Decimal(str(row["quantity"]))
                            for row in rows
                            if str(row.get("purchase_line_id")) == body.purchaseLineId
                        ),
                        Decimal(0),
                    )
                    used_amount = sum(
                        (
                            Decimal(str(row["gross"]))
                            for row in rows
                            if str(row.get("purchase_line_id")) == body.purchaseLineId
                        ),
                        Decimal(0),
                    )
                    gross = prorated_amount(
                        Decimal(str(purchase_line["amount"])),
                        declaration_quantity(purchase_line),
                        used_quantity,
                        quantity,
                        used_amount,
                    )
                    invoice_used = sum(
                        (
                            Decimal(str(row["gross"]))
                            for row in rows
                            if row["invoice_line_id"] == body.invoiceLineId
                        ),
                        Decimal(0),
                    )
                    invoice_line = next(item for item in invoice["lines"] if item["id"] == body.invoiceLineId)
                    if gross <= 0 or invoice_used + gross > Decimal(invoice_line["gross"]):
                        raise ApiError(422, "发票行剩余含税金额不足")
                    if gross != gross.quantize(Decimal("0.00000001")) or gross >= Decimal("1e18"):
                        raise ApiError(422, "分配金额超出存储精度，请调整数量后重新核实")
                dao.insert(
                    connection,
                    {
                        "tenant_id": tenant,
                        "request_id": str(body.requestId),
                        "request_hash": request_hash,
                        "invoice_id": str(invoice_id),
                        "invoice_line_id": body.invoiceLineId,
                        "purchase_line_id": body.purchaseLineId,
                        "quantity": quantity,
                        "gross": gross,
                        "source_hash": candidate["sourceHash"],
                        "actor": owner,
                        "purchase_hash": candidate["purchaseHash"],
                        "source_snapshot": {"invoice": invoice, "candidate": candidate},
                        "created_at": datetime.now(timezone.utc).replace(tzinfo=None),
                    },
                )
            return {
                "message": "分配已保存到本地，未写回NS",
                "quantity": str(quantity),
                "gross": format(gross, ".8f"),
            }
        except SQLAlchemyError:
            raise ApiError(
                503, "分配保存失败或结果不明，请刷新已确认记录核实；重试必须沿用原请求标识"
            ) from None

    def validate_links(
        self, invoice, heads, lines, allocations, links, view, pairs, *, manual=False, warnings=None
    ):
        """整票逐行汇总核对，确认关系时不生成任何数量金额分配。"""
        warnings = warnings if warnings is not None else []

        def discrepancy(message):
            if not manual:
                raise ApiError(422, message)
            if message not in warnings:
                warnings.append(message)

        if not invoice.get("sourceComplete") or invoice.get("sourceStatus") not in {"normal", "unknown"}:
            raise ApiError(422, "发票状态或明细待核实")
        if invoice.get("sourceStatus") == "unknown":
            discrepancy("发票来源状态未知，请人工核实票面有效性")
        if any(row["invoice_id"] == invoice["id"] for row in links):
            raise ApiError(409, "该发票已有整票关联，请刷新查看")
        if any(row["invoice_id"] == invoice["id"] for row in allocations):
            raise ApiError(422, "该发票已有数量分配，不能重复建立整票关联")
        selected_keys = [(pair.invoiceLineId, pair.purchaseLineId) for pair in pairs]
        if len(set(selected_keys)) != len(selected_keys) or len({key[1] for key in selected_keys}) != len(
            pairs
        ):
            raise ApiError(422, "同一子采购明细不能重复选择")
        candidates = {(row["invoiceLineId"], row["purchaseLineId"]): row for row in view["candidates"]}
        invoice_lines = {row["id"]: row for row in invoice["lines"]}
        purchase_lines = {str(row["id"]): row for row in lines}
        orders = {str(row["id"]): effective_order(row) for row in heads}
        selected = []
        totals = {key: [Decimal(0), Decimal(0)] for key in invoice_lines}
        for invoice_line_id, purchase_line_id in selected_keys:
            candidate = candidates.get((invoice_line_id, purchase_line_id))
            item, line = invoice_lines.get(invoice_line_id), purchase_lines.get(purchase_line_id)
            order = orders.get(str(line["purchase_order_id"])) if line else None
            if not candidate or not item or not order:
                raise ApiError(422, "所选明细不在当前候选中，请重新预览")
            if candidate["matchStatus"] == "报关线索冲突，待核实":
                discrepancy("采购单与报关单线索冲突，需人工核实来源")
            if any(row["purchase_line_id"] == purchase_line_id for row in links) or any(
                row["purchase_line_id"] == purchase_line_id for row in allocations
            ):
                raise ApiError(422, "子采购明细已有整票关联或数量分配")
            if order.get("detail_sync_status") != "complete":
                raise ApiError(422, "子采购明细未完整同步")
            if not normalize(invoice.get("seller")) or not normalize(order.get("supplier_name")):
                raise ApiError(422, "销售方或子采购供应商名称缺失，请核实来源")
            if not normalize(invoice.get("seller")) or normalize(invoice["seller"]) != normalize(
                order.get("supplier_name")
            ):
                discrepancy(
                    f"销售方与子采购供应商主体待核实：发票「{invoice.get('seller') or '缺失'}」 / "
                    f"{order['order_no']}「{order.get('supplier_name') or '缺失'}」"
                )
            if not normalize(invoice.get("buyer")) or normalize(invoice["buyer"]) != normalize(
                order.get("company_name")
            ):
                raise ApiError(422, "购买方与采购公司未核实一致")
            if not currency(invoice.get("currency")) or currency(invoice["currency"]) != currency(
                order.get("currency_code")
            ):
                raise ApiError(422, "发票与采购币种未核实一致")
            if order.get("parent_currency_code") and currency(order["currency_code"]) != currency(
                order["parent_currency_code"]
            ):
                raise ApiError(422, "子采购与母采购币种冲突")
            if not item_matches(item, line):
                discrepancy(
                    f"发票行 {invoice_line_id} 与子采购 {order['order_no']} 报关品名不一致："
                    f"{item.get('item') or '缺失'} / {line.get('declaration_name') or '缺失'}"
                )
            if not normalize(item.get("unit")) or normalize(item["unit"]) != normalize(
                line.get("declaration_unit")
            ):
                discrepancy(
                    f"发票单位与子采购报关单位不一致或缺失："
                    f"{item.get('unit') or '缺失'} / {line.get('declaration_unit') or '缺失'}"
                )
            quantity = declaration_quantity(line)
            gross = number(line.get("amount"), positive=True)
            if quantity is None or gross is None:
                raise ApiError(422, "子采购报关数量或人民币含税金额缺失")
            totals[invoice_line_id][0] += quantity
            totals[invoice_line_id][1] += gross
            selected.append((candidate, line, order))
        for line_id, item in invoice_lines.items():
            quantity, gross = (
                number(item.get("quantity"), positive=True),
                number(item.get("gross"), positive=True),
            )
            if quantity is None or gross is None:
                raise ApiError(422, "发票明细数量或含税金额缺失")
            if line_id not in {key[0] for key in selected_keys}:
                raise ApiError(422, f"发票行 {line_id} 尚未选择子采购明细")
            if totals[line_id] != [quantity, gross]:
                discrepancy(
                    f"发票行 {line_id} 所选子采购明细的报关数量或人民币含税金额汇总不一致："
                    f"发票数量 {quantity} / 子采购 {totals[line_id][0]}；"
                    f"发票金额 {gross} / 子采购 {totals[line_id][1]}"
                )
        invoice_gross = number(invoice.get("gross"), positive=True)
        if invoice_gross is None or invoice_gross != sum(
            (number(item["gross"]) for item in invoice_lines.values()), Decimal(0)
        ):
            raise ApiError(422, "发票抬头与明细价税合计不一致")
        return selected

    def review_links(self, invoice_id, body, owner):
        """只读复核所选关系，差异由后端返回；提交时仍在锁内重算。"""
        if self.engine is None:
            raise ApiError(503, "匹配存储未配置")
        invoice = self.invoices.invoice_detail(invoice_id, owner)
        heads, lines = self.purchases.read(owner)
        tenant = hashlib.sha256(owner.encode()).hexdigest()
        try:
            with self.engine.connect() as connection:
                allocations = dao.read(connection, tenant)
                links = dao.read_links(connection, tenant)
        except SQLAlchemyError:
            raise ApiError(503, "匹配表不可用，请执行业务库迁移或检查连接后重试") from None
        view = self.evaluate(
            invoice,
            heads,
            lines,
            allocations,
            customs_no=body.customsNo,
            links=links,
            selected_pairs=body.pairs,
        )
        if view["snapshot"] != body.snapshot:
            raise ApiError(409, "来源数据或关联记录发生变化，请刷新候选后重新确认")
        warnings = []
        try:
            with localcontext() as context:
                context.prec = 64
                self.validate_links(
                    invoice,
                    heads,
                    lines,
                    allocations,
                    links,
                    view,
                    body.pairs,
                    manual=True,
                    warnings=warnings,
                )
        except ApiError as error:
            return {
                "allowed": False,
                "reason": str(error),
                "warnings": warnings,
                "requiresManualConfirmation": bool(warnings),
            }
        return {
            "allowed": True,
            "reason": "存在匹配差异，请核实并填写人工确认说明"
            if warnings
            else "所选关系核对一致，可确认关联",
            "warnings": warnings,
            "requiresManualConfirmation": bool(warnings),
        }

    def link(self, invoice_id, body, owner):
        if self.engine is None or self.engine.dialect.name != "mysql":
            raise ApiError(503, "整票关联需要已迁移的MySQL业务库")
        tenant = hashlib.sha256(owner.encode()).hexdigest()
        keys = sorted((pair.invoiceLineId, pair.purchaseLineId) for pair in body.pairs)
        request_hash = digest([invoice_id, keys, body.customsNo])
        if body.manualConfirmation or body.manualReason:
            request_hash = digest([request_hash, body.manualConfirmation, body.manualReason.strip()])
        try:
            with self.engine.begin() as connection:
                invoice = matching_invoice(connection, invoice_id, owner)
                heads, lines = self.purchases.read(owner, connection)
                allocations = dao.read(connection, tenant, lock=True)
                links = dao.read_links(connection, tenant, lock=True)
                prior = [row for row in links if row["request_id"] == str(body.requestId)]
                if prior:
                    if prior[0]["request_hash"] != request_hash:
                        raise ApiError(409, "请求标识已用于其他关联，请重新预览")
                    return {"message": "该整票关联已经保存，未重复写入", "linkedLines": len(prior)}
                view = self.evaluate(
                    invoice,
                    heads,
                    lines,
                    allocations,
                    customs_no=body.customsNo,
                    links=links,
                    selected_pairs=body.pairs,
                )
                if view["snapshot"] != body.snapshot:
                    raise ApiError(409, "来源数据或关联记录发生变化，请刷新候选后重新确认")
                warnings = []
                with localcontext() as context:
                    context.prec = 64
                    selected = self.validate_links(
                        invoice,
                        heads,
                        lines,
                        allocations,
                        links,
                        view,
                        body.pairs,
                        manual=body.manualConfirmation,
                        warnings=warnings,
                    )
                if body.manualConfirmation and not body.manualReason.strip():
                    raise ApiError(422, "请填写人工确认说明，记录差异核实依据")
                now = datetime.now(timezone.utc).replace(tzinfo=None)
                dao.insert_links(
                    connection,
                    {
                        "tenant_id": tenant,
                        "request_id": str(body.requestId),
                        "request_hash": request_hash,
                        "invoice_id": str(invoice_id),
                        "source_snapshot": {
                            "invoice": invoice,
                            "selectedCandidates": [candidate for candidate, _line, _order in selected],
                            "manualConfirmation": body.manualConfirmation,
                            "manualReason": body.manualReason.strip(),
                            "warnings": warnings,
                        },
                        "actor": owner,
                        "created_at": now,
                    },
                    [
                        {
                            "tenant_id": tenant,
                            "invoice_line_id": candidate["invoiceLineId"],
                            "purchase_line_id": candidate["purchaseLineId"],
                            "purchase_order_id": str(line["purchase_order_id"]),
                            "source_hash": candidate["sourceHash"],
                            "purchase_hash": candidate["purchaseHash"],
                        }
                        for candidate, line, _order in selected
                    ],
                )
            return {"message": "整票与子采购单关系已保存到本地，未写回NS", "linkedLines": len(selected)}
        except SQLAlchemyError:
            raise ApiError(503, "整票关联保存失败或结果不明，请刷新记录核实后沿用原请求标识重试") from None

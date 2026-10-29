"""通过各模块只读门面构造整单候选；预览与提交复用同一份分配规则。"""

import hashlib
import json
from decimal import Decimal

from backend.core.errors import ApiError
from backend.modules.invoice.public import read_invoices
from backend.modules.review.public import current_bases
from backend.modules.source.public import purchase_lines, purchase_order_lines, unit_label, unit_names
from backend.modules.task.public import open_lines

from ..dao import allocation_dao, ledger_dao
from ..policy.allocation_policy import remaining
from ..policy.comparison_policy import name_result, order_reference, text
from ..policy.order_matching_policy import plan
from ..vo.order_matching_vo import OrderCandidate, OrderCandidates


def digest(value):
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode()
    ).hexdigest()


def candidates(connection, query, *, order_id=None):
    found = read_invoices(connection, [int(query.invoiceId)])
    if not found:
        raise ApiError(404, "发票不存在")
    invoice = found[0]
    tasks = {row["purchase_line_id"]: row for row in open_lines(connection)}
    task_contexts = purchase_lines(connection, list(tasks))
    order_ids = set()
    keyword = getattr(query, "keyword", "").strip().casefold()
    for line in task_contexts.values():
        if order_id is not None and line["purchase_order_id"] != order_id:
            continue
        recalled = order_reference(invoice["remark"], line) or name_result(
            invoice["seller_name_normalized"], line["supplier_name_normalized"]
        ) in ("match", "partial")
        searchable = " ".join(
            str(line.get(key) or "")
            for key in ("order_no", "parent_order_no", "supplier_name", "company_name", "ns_account")
        ).casefold()
        if recalled and (not keyword or keyword in searchable):
            order_ids.add(line["purchase_order_id"])
    # 必须覆盖来源整单的全部有效行，不能把有任务的部分行冒充整单。
    source_rows = purchase_order_lines(connection, sorted(order_ids))
    contexts = purchase_lines(connection, [row["id"] for row in source_rows])
    bases = current_bases(connection, list(contexts))
    units = unit_names(connection)
    confirmed = any(
        row["status"] == "confirmed" for row in allocation_dao.by_invoices(connection, [invoice["id"]])
    )
    grouped = {}
    for line_id, line in contexts.items():
        basis = bases.get(line_id)
        line.update(
            currency=basis["currency"] if basis else None,
            basis_reason=basis["reason"] if basis else "缺少有效开票依据",
        )
        grouped.setdefault(line["purchase_order_id"], {})[line_id] = line
    rows = []
    for purchase_id, lines in grouped.items():
        allocation_plan, block = plan(invoice, lines, tasks, bases, query)
        if confirmed:
            block = "发票已有已确认分配，请在逐行分配中核实或取消，不能再次整单分配"
        if not block and any(
            ledger_dao.unresolved(connection, invoice["id"], line_id, 0) for line_id in lines
        ):
            block = "相关发票或子采购仍有待复核占用，请先处理原分配"
        rows.append(
            _candidate(invoice, purchase_id, lines, tasks, bases, units, query, allocation_plan, block)
        )
    rows.sort(
        key=lambda row: (not row.orderMatched, not row.confirm.allowed, row.orderNo, row.purchaseOrderId)
    )
    return rows


def _candidate(invoice, order_id, lines, tasks, bases, units, query, allocation_plan, block):
    first = next(iter(lines.values()))
    remaining_rows = [remaining(tasks[line_id]) if line_id in tasks else (None, None) for line_id in lines]
    unit_values = {
        bases[line_id]["unit"] if line_id in bases else lines[line_id]["unit"] for line_id in lines
    }
    currencies = {line["currency"] for line in lines.values()}
    quantity = (
        None
        if len(unit_values) != 1 or any(q is None for q, _ in remaining_rows)
        else sum((q for q, _ in remaining_rows), Decimal(0))
    )
    amount = (
        None
        if len(currencies) != 1 or any(a is None for _, a in remaining_rows)
        else sum((a for _, a in remaining_rows), Decimal(0))
    )
    items = {item["id"]: item for item in invoice["items"]}
    warnings, previews = [], []
    for part in allocation_plan:
        line, basis, item = (
            lines[part["purchase_line_id"]],
            bases[part["purchase_line_id"]],
            items[part["invoice_item_id"]],
        )
        if item["unit"] != basis["unit"]:
            warnings.append(
                f"发票单位 {item['unit']} 与采购单位 {unit_label(basis['unit'], units)} 不同，确认时必须填写换算证据"
            )
        previews.append(
            {
                "invoiceItemId": str(item["id"]),
                "purchaseLineId": str(part["purchase_line_id"]),
                "purchaseBasisId": str(basis["id"]),
                "item": line["item_name"] or line["declaration_name"] or "",
                "invoiceUnit": item["unit"],
                "purchaseUnit": unit_label(basis["unit"], units),
                "invoiceQuantity": text(part["quantity"]),
                "purchaseQuantity": text(part["purchase_quantity"]),
                "amount": text(part["amount"]),
            }
        )
    reference = order_reference(invoice["remark"], first)
    if reference:
        warnings.insert(0, f"备注命中{reference[0]} {reference[1]}，候选为整张子采购单")
    else:
        warnings.insert(0, "备注未命中该订单，请核实整单对应关系")
    fingerprint = digest(
        {
            "invoice": invoice,
            "lines": lines,
            "tasks": {key: tasks.get(key) for key in lines},
            "bases": {key: bases.get(key) for key in lines},
            "numerator": query.conversionNumerator,
            "denominator": query.conversionDenominator,
        }
    )
    return OrderCandidate(
        purchaseOrderId=str(order_id),
        orderNo=first["order_no"] or "",
        parentOrderNo=first["parent_order_no"] or "",
        account=first["ns_account"],
        supplier=first["supplier_name"] or "",
        company=first["company_name"] or "",
        currency=next(iter(currencies)) or "" if len(currencies) == 1 else "多币种",
        lineCount=len(lines),
        remainingAmount=text(amount),
        remainingQuantity=text(quantity),
        unit=unit_label(next(iter(unit_values)), units) if len(unit_values) == 1 else "多单位",
        orderMatched=bool(reference),
        fingerprint=fingerprint,
        warnings=list(dict.fromkeys(warnings)),
        confirm={"allowed": not block, "reason": block or "确认后将整张发票原子分配到下列采购明细"},
        allocations=previews,
    )


def query_candidates(connection, query):
    rows = candidates(connection, query)
    offset = (query.page - 1) * query.pageSize
    return OrderCandidates(
        rows=rows[offset : offset + query.pageSize],
        total=len(rows),
        page=query.page,
        pages=max(1, (len(rows) + query.pageSize - 1) // query.pageSize),
    )

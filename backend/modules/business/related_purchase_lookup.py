"""按子采购单号只读追溯 NS 报关来源，供票面线索核对。"""

from datetime import datetime, timezone
from decimal import Decimal

from backend.core.errors import ApiError

from .pl_config import parse_config
from .pl_mapper import reference, text


class RelatedPurchaseLookup:
    def __init__(self, ns):
        self.ns = ns

    def query(self, sub_purchase_no: str, invoice_gross: str):
        config = parse_config(self.ns.settings)
        purchase = config.purchase
        number_field = purchase.fields.get("purchase")
        if not number_field:
            raise ApiError(503, "NS 子采购单号映射尚未配置")
        ids = self.ns.filtered_ids(purchase.type, number_field, sub_purchase_no)
        queried_at = datetime.now(timezone.utc).isoformat()
        if not ids:
            return {"found": False, "queriedAt": queried_at}
        if len(ids) != 1:
            raise ApiError(409, "NS 返回多个同号子采购单，请核实来源身份")

        source = self.ns.request("GET", purchase.type, ids[0], exact_numbers=True)["data"]
        if not isinstance(source, dict) or text(source.get(number_field)) != sub_purchase_no:
            raise ApiError(502, "NS 子采购单号与精确查询结果不一致")
        amount_field = purchase.storage_fields.get("total_amount")
        raw_amount = source.get(amount_field) if amount_field else None
        try:
            purchase_amount = Decimal(str(raw_amount)) if raw_amount is not None else None
        except (ValueError, TypeError):
            raise ApiError(502, "NS 子采购金额格式无效") from None

        line_ids = self.ns.filtered_ids(
            config.purchase_line.type, config.purchase_line.parent, ids[0], reference=True
        )
        lines = []
        for line_id in line_ids:
            row = self.ns.request("GET", config.purchase_line.type, line_id, exact_numbers=True)["data"]
            if not isinstance(row, dict) or reference(row.get(config.purchase_line.parent)) != ids[0]:
                raise ApiError(502, "NS 子采购明细归属与查询结果不一致")
            fields = config.purchase_line.fields
            lines.append(
                {
                    "name": text(row.get(fields.get("name"))),
                    "quantity": text(row.get(fields.get("quantity"))),
                    "amount": text(row.get(fields.get("amount"))),
                }
            )

        customs = None
        customs_id = reference(source.get(purchase.customs))
        if customs_id:
            record = self.ns.request("GET", config.customs.type, customs_id, exact_numbers=True)["data"]
            if not isinstance(record, dict):
                raise ApiError(502, "NS 报关单响应不完整")
            customs = {
                "recordNo": text(record.get(config.customs.storage_fields.get("record_no", "name"))),
                "declarationNo": text(record.get(config.customs.fields.get("declaration"))),
                "date": text(record.get(config.customs.fields.get("date"))),
            }
        return {
            "found": True,
            "queriedAt": queried_at,
            "subPurchaseNo": sub_purchase_no,
            "parentPurchase": text(source.get(purchase.fields.get("parent"))),
            "purchaseDate": text(source.get(purchase.storage_fields.get("order_date"))),
            "supplier": text(source.get(purchase.fields.get("vendor"))),
            "pl": text(source.get(purchase.pl)),
            "purchaseAmount": format(purchase_amount, "f") if purchase_amount is not None else None,
            "invoiceGross": invoice_gross,
            "amountMatches": purchase_amount == Decimal(invoice_gross)
            if purchase_amount is not None
            else None,
            "customs": customs,
            "lines": lines,
        }

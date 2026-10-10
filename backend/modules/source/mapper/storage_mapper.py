"""把完整读取的 NS 记录映射为新表的行；不查询数据库、不按展示文本反推金额。

服务器配置（NETSUITE_PL_LOOKUP 的 storage_fields）沿用原有键名，键名到新表列的对应见 FIELDS；
部署环境无需修改配置键。
"""

import re
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation, localcontext

from sqlalchemy import Date, DateTime, Numeric, String

from backend.core.errors import ApiError

from ..entity import customs_declarations, customs_lines, purchase_order_lines, purchase_orders
from ..policy.names import normalize_name
from .ns_fields import normalize, reference, text

# 非列目标：供应商、申报公司引用
SUPPLIER_ID, SUPPLIER_NAME = "supplier.ns_internal_id", "supplier.name"
DECLARANT_ID, DECLARANT_NAME = "declarant.ns_internal_id", "declarant.name"

# 配置键（沿用原有名称）→ 新表列
FIELDS = {
    "purchase": {
        "order_no": "order_no",
        "order_date": "order_date",
        "parent_order_no": "parent_order_no",
        "supplier_identifier": SUPPLIER_ID,
        "supplier_name": SUPPLIER_NAME,
        "currency_code": "currency",
        "total_amount": "total_amount",
        "source_modified_at": "source_modified_at",
    },
    "purchase_line": {
        "line_no": "line_no",
        "item_code": "item_code",
        "item_name": "item_name",
        "declaration_name": "declaration_name",
        "specification": "specification",
        "quantity": "quantity",
        "unit_name": "unit",
        "declaration_quantity": "declared_quantity",
        "declaration_unit": "declared_unit",
        "tax_inclusive_price": "unit_price",
        "amount": "amount",
    },
    "customs": {
        "record_no": "record_no",
        "declaration_no": "declaration_no",
        "declaration_date": "declaration_date",
        "declarant_identifier": DECLARANT_ID,
        "declarant_name": DECLARANT_NAME,
        "source_modified_at": "source_modified_at",
    },
    "customs_line": {
        "line_no": "line_no",
        "sales_order_no": "sales_order_no",
        "origin_place": "origin_place",
        "item_code": "item_code",
        "declaration_name": "declaration_name",
        "specification": "specification",
        "quantity": "quantity",
        "unit_name": "unit",
        "declared_quantity": "declared_quantity",
        "declared_unit": "declared_unit",
        "unit_price": "unit_price",
        "amount": "amount",
        "currency_code": "currency",
    },
}
REQUIRED = {
    "purchase": {"order_no"},
    "purchase_line": {"declaration_name", "quantity", "unit_name", "amount"},
    "customs": {"declaration_no", "declaration_date"},
    "customs_line": {"declaration_name", "specification", "origin_place", "quantity", "unit_name"},
}
TABLES = {
    "purchase": purchase_orders,
    "purchase_line": purchase_order_lines,
    "customs": customs_declarations,
    "customs_line": customs_lines,
}
REFERENCE_LENGTH = {SUPPLIER_ID: 190, DECLARANT_ID: 190, SUPPLIER_NAME: 255, DECLARANT_NAME: 255}


def validate_storage_config(config):
    if not config.company_record_type:
        raise ApiError(503, "保存映射缺少company_record_type，请确认两侧公司引用同一记录类型")
    for name, allowed in FIELDS.items():
        spec = getattr(config, name)
        fields = spec.storage_fields
        if spec.omitted_as_null and (name != "customs" or set(spec.omitted_as_null) - set(fields)):
            raise ApiError(503, "omitted_as_null仅允许已配置映射的报关单号、申报日期")
        if set(fields) - set(allowed):
            raise ApiError(503, f"{name}.storage_fields包含不允许的数据库字段")
        missing = REQUIRED[name] - set(fields)
        if missing:
            raise ApiError(503, f"{name}.storage_fields缺少映射：{', '.join(sorted(missing))}")


def column_value(value, column):
    """按目标列类型、长度、精度转换；不符合时拒绝整页保存。"""
    if value is None or value == "":
        return None
    kind = column.type
    try:
        if isinstance(kind, Numeric):
            if isinstance(value, (bool, float, dict, list)):
                raise ValueError()
            number = Decimal(str(value))
            if not number.is_finite() or abs(number) >= Decimal(10) ** (kind.precision - kind.scale):
                raise ValueError()
            with localcontext() as ctx:
                ctx.prec = 64
                if number != number.quantize(Decimal(1).scaleb(-kind.scale)):
                    raise ValueError()
            return number
        if isinstance(kind, DateTime):
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                raise ValueError()
            return parsed.astimezone(timezone.utc).replace(tzinfo=None)
        if isinstance(kind, Date):
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(value)):
                raise ValueError()
            return date.fromisoformat(str(value))
        if isinstance(kind, String):
            converted = text(value)
            if not converted or len(converted) > kind.length:
                raise ValueError()
            return converted
    except (ValueError, InvalidOperation, OverflowError):
        raise ApiError(422, f"字段{column.name}格式、长度或精度不符合数据库要求，未保存") from None
    raise ApiError(503, f"字段{column.name}不支持当前保存映射")


def reference_value(value, target):
    converted = reference(value) if target.endswith("ns_internal_id") else text(value)
    if converted and len(converted) > REFERENCE_LENGTH[target]:
        raise ApiError(422, f"字段{target}长度不符合数据库要求，未保存")
    return converted or None


def project(record, kind, spec):
    """返回 (列值, 引用值)；默认拒绝缺字段，仅对已核实的报关空字段允许 NULL。"""
    columns, references = {}, {}
    table = TABLES[kind]
    for key, source in spec.storage_fields.items():
        target = FIELDS[kind][key]
        if source not in record:
            if key in spec.omitted_as_null and table.c[target].nullable:
                columns[target] = None
                continue
            raise ApiError(422, f"NS响应缺少已配置字段{source}，请核实映射后重试")
        if target in REFERENCE_LENGTH:
            references[target] = reference_value(record[source], target)
        else:
            columns[target] = column_value(record[source], table.c[target])
    return columns, references


def company_ref(record, field, record_type):
    value = record.get(field)
    record_id = reference(value)
    if not record_id:
        return None
    name = text(value) or record_id
    return {"ns_internal_id": f"{record_type}:{record_id}", "name": name[:255]}


def party(references, id_key, name_key, prefix=""):
    identity = references.get(id_key)
    if not identity:
        return None
    return {"ns_internal_id": f"{prefix}{identity}", "name": references.get(name_key) or identity}


def raw_payload(spec, line_spec, record_id, record, raw_lines):
    return normalize(
        {
            "recordType": spec.type,
            "recordId": record_id,
            "record": record,
            "lineType": line_spec.type,
            "lines": [{"id": line_id, "record": line} for line_id, line in raw_lines],
        }
    )


def checked_text(value, column):
    return column_value(value, column) if value else None


def map_customs(bundle, config, now):
    spec, line_spec = config.customs, config.customs_line
    documents = []
    for record_id, record, raw_lines in bundle["customs"]:
        head, references = project(record, "customs", spec)
        head.update(detail_status="complete", synced_at=now, is_active=True)
        lines = []
        for line_id, raw in raw_lines:
            line, _ = project(raw, "customs_line", line_spec)
            line.update(
                source_line_key=checked_text(f"{line_spec.type}:{line_id}", customs_lines.c.source_line_key),
                pl_no=checked_text(
                    bundle["pl_names"].get(reference(raw.get(line_spec.pl))), customs_lines.c.pl_no
                ),
                is_active=True,
            )
            lines.append(
                {"row": line, "company": company_ref(raw, line_spec.company, config.company_record_type)}
            )
        documents.append(
            {
                "ns_internal_id": record_id,
                "head": head,
                # 申报主体的 NS 记录类型未配置，用独立前缀避免与采购公司身份混淆。
                "declarant": party(references, DECLARANT_ID, DECLARANT_NAME, prefix="declarant:"),
                "lines": lines,
                "raw": raw_payload(spec, line_spec, record_id, record, raw_lines),
            }
        )
    return documents


def map_purchases(bundle, config, now):
    spec, line_spec = config.purchase, config.purchase_line
    documents = []
    for record_id, record, raw_lines in bundle["purchases"]:
        head, references = project(record, "purchase", spec)
        head.update(
            pl_no=checked_text(
                bundle["pl_names"].get(reference(record.get(spec.pl))), purchase_orders.c.pl_no
            ),
            detail_status="complete",
            synced_at=now,
            is_active=True,
        )
        lines = []
        for line_id, raw in raw_lines:
            line, _ = project(raw, "purchase_line", line_spec)
            name = line.get("declaration_name") or line.get("item_name")
            line.update(
                source_line_key=checked_text(
                    f"{line_spec.type}:{line_id}", purchase_order_lines.c.source_line_key
                ),
                item_name_normalized=normalize_name(name)[:500] or None,
                amount_status="source_missing" if line.get("amount") is None else "matched",
                is_active=True,
            )
            lines.append(line)
        documents.append(
            {
                "ns_internal_id": record_id,
                "head": head,
                "supplier": party(references, SUPPLIER_ID, SUPPLIER_NAME),
                "company": company_ref(record, spec.company, config.company_record_type),
                "customs_ns_id": reference(record.get(spec.customs)) or None,
                "lines": lines,
                "raw": raw_payload(spec, line_spec, record_id, record, raw_lines),
            }
        )
    return documents


def map_bundle(bundle, config, now):
    return {"customs": map_customs(bundle, config, now), "purchase": map_purchases(bundle, config, now)}

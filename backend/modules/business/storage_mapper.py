"""将完整NS原始记录映射为数据库值；不查询数据库、不按展示文本反推金额。"""

import re
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation, localcontext

from sqlalchemy import Date, DateTime, Numeric, String

from backend.core.errors import ApiError

from .entity import REQUIRED_FIELDS, STORAGE_FIELDS
from .pl_mapper import reference, text


def validate_storage_config(config):
    if not config.company_record_type:
        raise ApiError(503, "保存映射缺少company_record_type，请确认两侧公司引用同一记录类型")
    for name, allowed in STORAGE_FIELDS.items():
        spec = getattr(config, name)
        fields = spec.storage_fields
        if spec.omitted_as_null and (name != "customs" or set(spec.omitted_as_null) - set(fields)):
            raise ApiError(503, "omitted_as_null仅允许已配置映射的报关单号、申报日期")
        if set(fields) - allowed:
            raise ApiError(503, f"{name}.storage_fields包含不允许的数据库字段")
        missing = REQUIRED_FIELDS[name] - set(fields)
        if missing:
            raise ApiError(503, f"{name}.storage_fields缺少映射：{', '.join(sorted(missing))}")


def normalize(value):
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ApiError(422, "来源包含非有限数值")
        return str(value)
    if isinstance(value, float):
        raise ApiError(422, "来源小数必须按Decimal读取，未保存可能丢失精度的数据")
    if isinstance(value, dict):
        return {k: normalize(v) for k, v in value.items()}
    if isinstance(value, list):
        return [normalize(v) for v in value]
    return value


def database_value(value, column):
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
            converted = (
                reference(value)
                if column.name.endswith("_identifier") and isinstance(value, dict)
                else text(value)
            )
            if not converted or len(converted) > kind.length:
                raise ValueError()
            return converted
    except (ValueError, InvalidOperation, OverflowError):
        raise ApiError(422, f"字段{column.name}格式、长度或精度不符合数据库要求，未保存") from None
    raise ApiError(503, f"字段{column.name}不支持当前保存映射")


def project_storage(record, spec, table):
    # 默认拒绝缺字段；仅对已核实的报关空字段显式允许NULL，不拿内部编号补值。
    result = {}
    for target, source in spec.storage_fields.items():
        if source not in record:
            if target in spec.omitted_as_null and table.c[target].nullable:
                result[target] = None
                continue
            raise ApiError(422, f"NS响应缺少已配置字段{source}，请核实映射后重试")
        result[target] = database_value(record[source], table.c[target])
    return result


def company(record, field, record_type):
    value = record.get(field)
    record_id = reference(value)
    return {
        "company_identifier": f"{record_type}:{record_id}" if record_id else None,
        "company_name": text(value) or None,
    }


def map_bundle(bundle, config, tables, tenant, account, pl_number):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    documents = {"customs": [], "purchase": []}
    for kind, source_key, table_name, line_table_name in (
        ("customs", "customs", "customs_declarations", "customs_declaration_lines"),
        ("purchase", "purchases", "purchase_orders", "purchase_order_lines"),
    ):
        spec, line_spec = getattr(config, kind), getattr(config, kind + "_line")
        table, line_table = tables[table_name], tables[line_table_name]
        for record_id, record, raw_lines in bundle[source_key]:
            head = {name: None for name in STORAGE_FIELDS[kind]}
            head.update(project_storage(record, spec, table))
            head.update(
                tenant_id=tenant,
                ns_account=account,
                ns_internal_id=record_id,
                is_active=True,
                detail_sync_status="complete",
                synced_at=now,
                last_complete_sync_at=now,
                source_data=normalize(
                    {
                        "recordType": spec.type,
                        "recordId": record_id,
                        "record": record,
                        "lineType": line_spec.type,
                        "lines": [{"id": i, "record": r} for i, r in raw_lines],
                    }
                ),
            )
            linked_customs = None
            if kind == "purchase":
                head.update(pl_no=pl_number, **company(record, spec.company, config.company_record_type))
                linked_customs = reference(record.get(spec.customs)) or None
            lines = []
            for line_id, raw in raw_lines:
                line = {name: None for name in STORAGE_FIELDS[kind + "_line"]}
                line.update(project_storage(raw, line_spec, line_table))
                line.update(
                    tenant_id=tenant,
                    source_line_key=f"{line_spec.type}:{line_id}",
                    is_active=True,
                    synced_at=now,
                )
                if kind == "customs":
                    line.update(
                        pl_no=bundle["pl_names"].get(reference(raw.get(line_spec.pl))),
                        **company(raw, line_spec.company, config.company_record_type),
                    )
                # 自动填入的公司、PL、行身份同样校验数据库长度。
                for key, value in list(line.items()):
                    if isinstance(line_table.c[key].type, String) and value is not None:
                        line[key] = database_value(value, line_table.c[key])
                lines.append(line)
            for key, value in list(head.items()):
                if isinstance(table.c[key].type, String) and value is not None:
                    head[key] = database_value(value, table.c[key])
            documents[kind].append({"head": head, "lines": lines, "customs_id": linked_customs})
    return documents

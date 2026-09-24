"""母子采购快照准入规则：来源、行证据和金额核对，复用既有字段转换。"""

import re
from datetime import datetime, timezone
from decimal import Decimal

from backend.core.errors import ApiError

from .pl_mapper import reference, text
from .storage_mapper import company, database_value, map_bundle, normalize


def require(condition, message):
    if not condition:
        raise ApiError(422, message)


def source_id(value):
    require(not isinstance(value, bool), "来源行标识格式错误")
    result = str(value)
    require(bool(re.fullmatch(r"[0-9]{1,40}", result)), "来源行标识缺失或格式错误")
    return result


def complete_items(record, key):
    sublist = record.get(key)
    require(isinstance(sublist, dict), f"母采购缺少完整{key}子列表")
    items = sublist.get("items")
    require(
        isinstance(items, list)
        and sublist.get("totalResults") == len(items)
        and not sublist.get("hasMore")
        and not any(link.get("rel") == "next" for link in sublist.get("links", [])),
        f"母采购{key}子列表未读取完整",
    )
    return items


def mapped_values(table, values):
    return {key: database_value(value, table.c[key]) for key, value in values.items()}


def unit_name(raw, units):
    if raw is None or raw == "":
        return None
    key = reference(raw) if isinstance(raw, dict) else str(raw)
    require(key in units, f"来源单位{key}未核实，未保存")
    return units[key]


def verified_parent_relations(bundle):
    """只有同次 SQL 与 REST 均确认空引用，才允许标记无母单。"""
    rows = bundle.get("purchase_parent_evidence", [])
    evidence = {}
    for row in rows:
        record_id = source_id(row.get("id"))
        require(record_id not in evidence, "子采购母单核实证据重复")
        evidence[record_id] = row
    if rows:
        require(set(evidence) == {row[0] for row in bundle["purchases"]}, "子采购母单核实证据范围不一致")
    purchases = []
    for record_id, record, lines in bundle["purchases"]:
        parent_id = reference(record.get("custrecord_swc_subpo_mainpo"))
        proof = evidence.get(record_id)
        if proof is not None:
            expected = "linked" if parent_id else "no_parent"
            require(
                proof.get("parent_relation_status") == expected
                and str(proof.get("custrecord_swc_subpo_mainpo") or "") == parent_id,
                "子采购母单 REST 与 SQL 引用不一致",
            )
        if not parent_id:
            require(proof is not None, "空母采购引用尚未独立核实，未保存")
            require(
                all(not text(line.get("custrecord_swc_subpo_item_mainpo_lineid")) for _, line in lines),
                "无母采购单却存在母行引用，未保存",
            )
            # REST 会省略空字段；仅在已核实为空时补给严格映射，原始正文另行保留。
            record = {**record, "custrecord_swc_subpo_mainpo": None}
        purchases.append((record_id, record, lines))
    return {**bundle, "purchases": purchases}, evidence


def verified_empty_fields(bundle, config):
    """仅保存独立核实的源空值；缺失金额仍须标记未核实，不能当成零。"""
    allowed = {
        "customs": {"declarant_identifier", "declarant_name"},
        "customs_line": {"specification"},
        "purchase_line": {"tax_inclusive_price", "amount"},
    }
    records = {}
    customs = []
    for record_id, record, lines in bundle["customs"]:
        head = dict(record)
        copied_lines = [(line_id, dict(line)) for line_id, line in lines]
        records["customs", record_id] = head
        records.update({("customs_line", line_id): line for line_id, line in copied_lines})
        customs.append((record_id, head, copied_lines))
    purchases = []
    for record_id, record, lines in bundle["purchases"]:
        copied_lines = [(line_id, dict(line)) for line_id, line in lines]
        records.update({("purchase_line", line_id): line for line_id, line in copied_lines})
        purchases.append((record_id, record, copied_lines))
    seen = set()
    for proof in bundle.get("empty_field_evidence", []):
        kind, record_id, field = proof.get("kind"), source_id(proof.get("id")), proof.get("field")
        require(kind in allowed and (kind, record_id) in records, "空值核实证据范围错误")
        permitted_fields = {getattr(config, kind).storage_fields.get(target) for target in allowed[kind]}
        require(field in permitted_fields and field is not None, "该字段不允许省略后按空值保存")
        key = kind, record_id, field
        require(key not in seen and proof.get("is_empty") == "T", "空值证据重复或未确认")
        seen.add(key)
        record = records[kind, record_id]
        require(record.get(field) in (None, ""), "REST 与 SQL 空值证据不一致")
        record[field] = None
    return {**bundle, "customs": customs, "purchases": purchases}


def prepare_related_documents(bundle, config, tables, tenant, account):
    require(bundle.get("source_account") == account, "来源快照 NS 账户不一致")
    require(bundle.get("complete") is True, "不能保存未完成的来源快照")
    require(config.company_record_type == "classification", "本次母采购映射要求分类公司字段")
    for kind, parent in (("customs", config.customs_line.parent), ("purchases", config.purchase_line.parent)):
        seen = set()
        for record_id, record, lines in bundle[kind]:
            require(record_id not in seen and str(record.get("id")) == record_id, "单据身份重复或不一致")
            seen.add(record_id)
            line_ids = set()
            for line_id, line in lines:
                require(
                    line_id not in line_ids
                    and str(line.get("id")) == line_id
                    and reference(line.get(parent)) == record_id,
                    "来源明细身份或所属单据不一致",
                )
                line_ids.add(line_id)

    mapped_bundle, relation_evidence = verified_parent_relations(bundle)
    mapped_bundle = verified_empty_fields(mapped_bundle, config)
    documents = map_bundle(mapped_bundle, config, tables, tenant, account, None)
    for document, (record_id, record, lines) in zip(documents["customs"], bundle["customs"], strict=True):
        source = document["head"]["source_data"]
        source["record"] = normalize(record)
        source["lines"] = normalize([{"id": rid, "record": row} for rid, row in lines])
        ids = {("customs", record_id), *(("customs_line", rid) for rid, _ in lines)}
        source["emptyFieldEvidence"] = [
            proof for proof in bundle.get("empty_field_evidence", []) if (proof["kind"], proof["id"]) in ids
        ]
    documents["parent"] = []
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    units = bundle["unit_names"]
    evidence = bundle["parent_line_evidence"]
    parent_sources, line_sources = {}, {}
    for entry in bundle["parents"]:
        parent_id, record = source_id(entry["id"]), entry["record"]
        require(
            str(record.get("id")) == parent_id and parent_id not in parent_sources, "母采购身份不一致或重复"
        )
        parent_sources[parent_id] = record
        raw_lines = complete_items(record, "item")
        require(not complete_items(record, "expense"), "费用类母采购尚未支持本次商品行导入")
        proof = [
            row
            for row in evidence
            if str(row.get("transaction")) == parent_id
            and row.get("mainline") == "F"
            and row.get("taxline") == "F"
        ]
        proof_by_line = {source_id(row["id"]): row for row in proof}
        require(len(proof_by_line) == len(proof) == len(raw_lines), "母采购 REST 与 SQL 商品行数不一致")
        head_table, line_table = tables["parent_purchase_orders"], tables["parent_purchase_order_lines"]
        head = mapped_values(
            head_table,
            {
                "order_no": record.get("tranId"),
                "order_date": record.get("tranDate"),
                "supplier_identifier": reference(record.get("entity")),
                "supplier_name": text(record.get("entity")),
                **company(record, "class", "classification"),
                "currency_code": text(record.get("currency")),
                "total_amount": record.get("total"),
                "source_status": text(record.get("status")),
                "source_modified_at": record.get("lastModifiedDate"),
            },
        )
        require(head["order_no"] and head["total_amount"] is not None, "母采购单号或总金额缺失")
        head.update(
            tenant_id=tenant,
            ns_account=account,
            ns_record_type="purchaseOrder",
            ns_internal_id=parent_id,
            source_data=normalize(
                {
                    "recordType": "purchaseOrder",
                    "lineType": "transactionline",
                    "record": record,
                    "lineEvidence": proof,
                }
            ),
            synced_at=now,
            last_complete_sync_at=now,
            detail_sync_status="complete",
            is_active=True,
        )
        lines, seen_refs, seen_keys = [], set(), set()
        for raw in raw_lines:
            line_ref = source_id(raw.get("line"))
            require(line_ref in proof_by_line and line_ref not in seen_refs, "母采购原生行 ID 缺失或重复")
            seen_refs.add(line_ref)
            row = proof_by_line[line_ref]
            key = "transactionline:" + source_id(row.get("uniquekey"))
            require(key not in seen_keys, "母采购稳定行键重复")
            seen_keys.add(key)
            require(reference(raw.get("item")) == str(row.get("item")), "母采购商品引用与 SQL 行不一致")
            values = mapped_values(
                line_table,
                {
                    "source_line_key": key,
                    "line_no": line_ref,
                    "item_code": raw.get("custcol22259"),
                    "item_name": raw.get("custcol28") or text(raw.get("item")),
                    "declaration_name": raw.get("custcol_custom_name"),
                    "specification": raw.get("custcol5"),
                    "quantity": raw.get("quantity"),
                    "unit_name": unit_name(raw.get("units"), units),
                    "amount": raw.get("grossAmt"),
                    "tax_inclusive_price": None,
                },
            )
            require(
                values["quantity"] is not None and values["amount"] is not None, "母采购行数量或含税金额缺失"
            )
            require(
                values["quantity"] == Decimal(str(row.get("quantity")))
                and str(raw.get("units")) == str(row.get("units")),
                "母采购数量或单位证据不一致",
            )
            require(
                Decimal(str(raw.get("amount"))) == Decimal(str(row.get("foreignamount"))),
                "母采购未税金额证据不一致",
            )
            require(
                Decimal(str(raw.get("amount"))) + Decimal(str(raw.get("tax1Amt"))) == values["amount"],
                "母采购行含税金额不一致",
            )
            values.update(
                tenant_id=tenant,
                source_data=normalize({"record": raw, "transactionLine": row}),
                synced_at=now,
                is_active=True,
            )
            lines.append(values)
            line_sources[parent_id, line_ref] = (key, raw)
        require(
            sum((line["amount"] for line in lines), Decimal(0)) == head["total_amount"],
            "母采购商品行金额与总金额不一致，未保存",
        )
        documents["parent"].append({"head": head, "lines": lines})

    for document, (record_id, record, raw_lines) in zip(
        documents["purchase"], bundle["purchases"], strict=True
    ):
        parent_value = record.get("custrecord_swc_subpo_mainpo")
        parent_id = reference(parent_value)
        if parent_id:
            require(parent_id in parent_sources, "本次关联导入要求提供子单引用的完整母采购")
            parent = parent_sources[parent_id]
            require(
                reference(record.get("custrecord_swc_subpo_vendor")) == reference(parent.get("entity")),
                "母子采购供应商不一致",
            )
        require(
            document["customs_id"] in {row[0] for row in bundle["customs"]}, "子采购关联报关不在完整快照中"
        )
        document["parent_source_id"] = parent_id or None
        document["head"]["parent_relation_status"] = "linked" if parent_id else "no_parent"
        document["head"]["source_data"]["record"] = normalize(record)
        document["head"]["source_data"]["lines"] = normalize(
            [{"id": rid, "record": row} for rid, row in raw_lines]
        )
        raw_ids = {rid for rid, _ in raw_lines}
        document["head"]["source_data"]["emptyFieldEvidence"] = [
            proof
            for proof in bundle.get("empty_field_evidence", [])
            if proof["kind"] == "purchase_line" and proof["id"] in raw_ids
        ]
        if record_id in relation_evidence:
            document["head"]["source_data"]["parentRelationEvidence"] = normalize(
                relation_evidence[record_id]
            )
        document["parent_line_keys"] = {}
        for line, (_, raw) in zip(document["lines"], raw_lines, strict=True):
            line_ref, key = None, None
            if parent_id:
                line_ref = source_id(raw.get("custrecord_swc_subpo_item_mainpo_lineid"))
                require((parent_id, line_ref) in line_sources, "子采购母行标识不能唯一对应母采购原生行")
                key, parent_line = line_sources[parent_id, line_ref]
                require(
                    reference(raw.get("custrecord_swc_subpo_item_item"))
                    == reference(parent_line.get("item")),
                    "母子采购行商品不一致",
                )
            line["ns_parent_line_ref"] = line_ref
            document["parent_line_keys"][line["source_line_key"]] = key
            # 采购单位未返回时保持空，不能用报关单位（例如千克）冒充瓶、包或袋。
            line["unit_name"] = unit_name(raw.get("custrecord_swc_subpo_item_unit"), units)
            line["declaration_unit"] = unit_name(raw.get("custrecord_swc_subpo_item_bgunit"), units)
        missing_amounts = [line["source_line_key"] for line in document["lines"] if line["amount"] is None]
        if missing_amounts:
            verified_amount_ids = {
                proof["id"]
                for proof in bundle.get("empty_field_evidence", [])
                if proof["kind"] == "purchase_line"
                and proof["field"] == config.purchase_line.storage_fields["amount"]
            }
            require(
                all(
                    rid in verified_amount_ids
                    for line, (rid, _) in zip(document["lines"], raw_lines, strict=True)
                    if line["amount"] is None
                ),
                "子采购来源空金额未独立核实",
            )
            # 完整来源快照可以包含源空值，但不能把未知金额计为零或声称金额核对通过。
            document["head"]["source_data"]["amountValidation"] = {
                "status": "source_missing",
                "missingAmountLineKeys": missing_amounts,
            }
            document["warnings"] = [
                f"子采购单{document['head']['order_no']}来源明细金额缺失，已保留NULL，金额待核实"
            ]
        else:
            require(
                sum((line["amount"] for line in document["lines"]), Decimal(0))
                == document["head"]["total_amount"],
                "子采购明细金额与单头不一致",
            )
            document["head"]["source_data"]["amountValidation"] = {"status": "matched"}
    require(
        set(parent_sources)
        == {doc["parent_source_id"] for doc in documents["purchase"] if doc["parent_source_id"]},
        "母采购快照包含范围外单据",
    )
    for document in documents["customs"]:
        for line in document["lines"]:
            line["unit_name"] = unit_name(line["unit_name"], units)
            line["declared_unit"] = unit_name(line["declared_unit"], units)
    # 单位解析后的名称同样遵循数据库长度校验。
    for kind, table_name in (("purchase", "purchase_order_lines"), ("customs", "customs_declaration_lines")):
        for document in documents[kind]:
            for line in document["lines"]:
                for field in ("unit_name", "declaration_unit" if kind == "purchase" else "declared_unit"):
                    line[field] = database_value(line[field], tables[table_name].c[field])
    return documents

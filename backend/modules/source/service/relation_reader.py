"""同步时读取 NS 原生关系及来源证据；不按品名猜配，不计算可审核金额。"""

import re
from datetime import datetime, timezone

from backend.core.errors import ApiError

from ..mapper.ns_fields import normalize, reference
from .relation_matcher import collect_comparisons, require_relation_interfaces

RAW_FIELDS = (
    "plId",
    "packingId",
    "companyId",
    "fulfillmentId",
    "fulfillmentLine",
    "itemId",
    "name",
    "sourceQuantity",
    "declarationQuantity",
    "declarationUnitId",
    "declarationModel",
    "parentPurchaseId",
)
PACK_CUSTOMS = "custrecord_swc_declare_record"
PACK_PL = "custrecord_swc_sublist_packingmain"
PACK_SALES = "custrecord_swc_sublist_createdfrom"
PACK_SALES_LINE = "custrecord_swc_so_lineid"


def source_id(value):
    value = reference(value) if isinstance(value, dict) else str(value or "")
    if value and not re.fullmatch(r"[1-9][0-9]{0,19}", value):
        raise ApiError(502, "NS 关联来源包含无效内部ID")
    return value


def read_originals(ns, customs):
    if not getattr(ns.settings, "finance_source_script", "") or not getattr(
        ns.settings, "finance_source_deploy", ""
    ):
        return {}, "原始报关行只读接口尚未配置，原始行与Packing对应关系未完整读取。"
    result = {}
    ids = list(customs)
    seen_rows = set()
    for start in range(0, len(ids), 20):
        batch = ids[start : start + 20]
        data = ns.finance_source_query(batch)
        if (
            not isinstance(data, dict)
            or data.get("complete") is not True
            or type(data.get("contractVersion")) is not int
            or data["contractVersion"] != 1
            or not isinstance(data.get("account"), str)
            or data.get("account", "").lower().replace("_", "-") != ns.settings.account
            or not isinstance(data.get("declarations"), list)
        ):
            raise ApiError(502, "原始报关行接口未完整返回同账套来源，未保存本页")
        batch_ids = set()
        for declaration in data["declarations"]:
            if not isinstance(declaration, dict):
                raise ApiError(502, "原始报关单格式无效")
            identity = declaration.get("id")
            if identity not in batch or identity in batch_ids:
                raise ApiError(502, "原始报关单范围不一致或重复")
            batch_ids.add(identity)
            if declaration.get("recordNumber") != customs[identity].get("name"):
                raise ApiError(502, "原始报关单号与本次读取不一致")
            rows = declaration.get("rows")
            if not isinstance(rows, list) or len(rows) > 2000:
                raise ApiError(502, "原始报关行不完整或超限")
            for row in rows:
                if (
                    not isinstance(row, dict)
                    or row.get("declarationId") != identity
                    or not isinstance(row.get("id"), str)
                    or not source_id(row["id"])
                    or row["id"] in seen_rows
                    or any(not isinstance(row.get(field), str) for field in RAW_FIELDS)
                ):
                    raise ApiError(502, "原始报关行身份、字段或归属无效")
                for field in (
                    "plId",
                    "packingId",
                    "companyId",
                    "fulfillmentId",
                    "itemId",
                    "parentPurchaseId",
                ):
                    source_id(row[field])
                seen_rows.add(row["id"])
            if len(seen_rows) > 5000:
                raise ApiError(422, "本次原始报关行超过5000行，请缩小范围")
            result[identity] = rows
        if batch_ids != set(batch):
            raise ApiError(502, "原始报关单返回范围缺失")
    return result, ""


class RelationReader:
    def __init__(self, ns):
        self.ns = ns

    def collect(self, bundle, *, match=False):
        customs = {source_id(identity): head for identity, head, _ in bundle["customs"]}
        if not customs:
            return {}
        if match:
            require_relation_interfaces(self.ns.settings)
        read_at = datetime.now(timezone.utc).isoformat()
        evidence = {
            identity: {
                "version": 1,
                "account": self.ns.settings.account,
                "declarationId": identity,
                "readAt": read_at,
                "status": "partial",
                "issues": [],
                "rawLines": [],
                "packingLines": [],
                "rawPackingLinks": [],
                "purchaseLinks": [],
                "parentLines": [],
                "childOrders": [],
            }
            for identity in customs
        }
        mapping = self.ns.settings.pl_lookup
        if (
            mapping["customs"]["type"] != "customrecord_swc_declare_record"
            or mapping["purchase"]["type"] != "customrecord_swc_subpo"
        ):
            for value in evidence.values():
                value["issues"].append("当前单据映射尚未配置原始行及Packing关联依据读取。")
            return evidence
        raw, issue = read_originals(self.ns, customs)
        packing = self.ns.relation_rows("packing_by_customs", list(customs))
        by_id = {}
        for row in packing:
            identity = source_id(row.get("id"))
            if not identity or identity in by_id or source_id(row.get(PACK_CUSTOMS)) not in customs:
                raise ApiError(502, "Packing身份、报关归属或返回范围不一致")
            by_id[identity] = row
        extra_ids = sorted(
            {row["packingId"] for rows in raw.values() for row in rows if row["packingId"]} - by_id.keys()
        )
        for start in range(0, len(extra_ids), 300):
            batch = extra_ids[start : start + 300]
            for row in self.ns.relation_rows("packing_by_id", batch):
                identity = source_id(row.get("id"))
                if identity not in batch or identity in by_id:
                    raise ApiError(502, "Packing返回范围不一致或身份重复")
                by_id[identity] = row
        if len(by_id) > 5000:
            raise ApiError(422, "Packing明细超过5000行，请缩小范围")
        sales = sorted({source_id(row.get(PACK_SALES)) for row in by_id.values()} - {""})
        links = self.ns.relation_rows("purchase_links", sales) if sales else []
        if any(source_id(row.get("previousdoc")) not in sales for row in links):
            raise ApiError(502, "销售采购行关系超出读取范围")
        children = {identity: [] for identity in customs}
        parent_ids = {source_id(row.get("nextdoc")) for row in links} - {""}
        for identity, head, rows in bundle["purchases"]:
            declaration_id = reference(head.get(mapping["purchase"]["customs"]))
            if declaration_id not in children:
                continue
            parent_id = source_id(head.get("custrecord_swc_subpo_mainpo"))
            if parent_id:
                parent_ids.add(parent_id)
            children[declaration_id].append(
                {
                    "id": identity,
                    "parentPurchaseId": parent_id,
                    "lines": [
                        {
                            "id": line_id,
                            "parentLineRef": str(line.get("custrecord_swc_subpo_item_mainpo_lineid") or ""),
                            "itemId": source_id(line.get("custrecord_swc_subpo_item_item")),
                            "record": line,
                        }
                        for line_id, line in rows
                    ],
                }
            )
        parent_ids.update(
            row["parentPurchaseId"] for rows in raw.values() for row in rows if row["parentPurchaseId"]
        )
        parent_rows = self.ns.relation_rows("parent_lines", sorted(parent_ids)) if parent_ids else []
        if any(source_id(row.get("transaction")) not in parent_ids for row in parent_rows):
            raise ApiError(502, "母采购行来源超出读取范围")
        for identity, value in evidence.items():
            value["rawLines"] = raw.get(identity, [])
            value["childOrders"] = children[identity]
            pack_ids = {
                source_id(row.get("id")) for row in packing if source_id(row.get(PACK_CUSTOMS)) == identity
            }
            pack_ids.update(row["packingId"] for row in value["rawLines"] if row["packingId"] in by_id)
            value["packingLines"] = [by_id[key] for key in sorted(pack_ids)]
            sales_lines = {
                (source_id(row.get(PACK_SALES)), str(row.get(PACK_SALES_LINE, "")))
                for row in value["packingLines"]
            }
            value["purchaseLinks"] = [
                row
                for row in links
                if (source_id(row.get("previousdoc")), str(row.get("previousline", ""))) in sales_lines
            ]
            parents = {child["parentPurchaseId"] for child in children[identity]}
            parents.update(row["parentPurchaseId"] for row in value["rawLines"])
            parents.update(source_id(row.get("nextdoc")) for row in value["purchaseLinks"])
            value["parentLines"] = [
                row for row in parent_rows if source_id(row.get("transaction")) in parents
            ]
            available_parents = {source_id(row.get("transaction")) for row in value["parentLines"]}
            if parents - {""} - available_parents:
                value["issues"].append("部分关联母采购行未返回，来源行身份尚未核实。")
            if issue:
                value["issues"].append(issue)
            elif not value["rawLines"]:
                value["issues"].append("NS返回的报关原始子行为空，不能建立逐行对应关系。")
            for row in value["rawLines"]:
                target = by_id.get(row["packingId"])
                if not target:
                    value["issues"].append("部分原始报关行缺少可读取的Packing引用。")
                    continue
                if row["plId"] and source_id(target.get(PACK_PL)) != row["plId"]:
                    raise ApiError(502, "原始行与Packing的PL引用不一致，未保存本页")
                value["rawPackingLinks"].append({"rawLineId": row["id"], "packingId": row["packingId"]})
            value["issues"] = list(dict.fromkeys(value["issues"]))
            # collected 仅代表来源已读取，不表示汇总行归属/分摊已核实，也不开放审批。
            value["status"] = "partial" if value["issues"] else "collected"
        if match:
            collect_comparisons(self.ns, bundle, evidence)
        return normalize(evidence)

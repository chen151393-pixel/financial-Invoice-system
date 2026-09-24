"""同步过程中复用NS整单追溯结果，不另写一套配对或分摊算法。"""

from backend.core.errors import ApiError

from .dto import PlScriptQuery
from .pl_mapper import reference
from .pl_script_service import PlScriptService
from .relation_policy import incomplete_reason, source_digest


def require_relation_interfaces(settings):
    mapping = settings.pl_lookup
    if mapping["customs"]["type"] != "customrecord_swc_declare_record":
        return
    if not all(
        getattr(settings, key, "")
        for key in (
            "finance_source_script",
            "finance_source_deploy",
            "pl_restlet_script",
            "pl_restlet_deploy",
        )
    ):
        raise ApiError(503, "完整同步需要配置同账套的原始报关行接口和v3关联查询接口；未保存不完整单据")


def collect_comparisons(ns, bundle, evidence):
    service = PlScriptService(ns)
    for identity, head, detail in bundle["customs"]:
        if not head.get("name"):
            raise ApiError(502, "报关单缺少NS记录编号，无法读取完整关联")
        result = service.query(PlScriptQuery(type="customsRecord", pl=head["name"], showIncomplete=True))
        if result.contractVersion != 3:
            raise ApiError(503, "NS关联接口仍为旧版，须部署v3逐行关联后再同步；本页未保存")
        if (
            len(result.groups) != 1
            or result.groups[0].declarationId != identity
            or result.groups[0].recordNumber != head["name"]
            or result.groups[0].customsCount != len(detail)
        ):
            raise ApiError(502, "NS关联查询与本次报关单身份或明细范围不一致；本页未保存")
        raw = result.groups[0].model_dump()
        children = {
            child.get("name")
            for _, child, rows in bundle["purchases"]
            if reference(child.get(ns.settings.pl_lookup["purchase"]["customs"])) == identity and rows
        }
        returned = {row["cells"][5] for row in raw["rows"] if row["side"] == "purchase"}
        if returned != children:
            raise ApiError(502, "NS关联查询与本次子采购单范围不一致；本页未保存，请重新读取")
        value = evidence[identity]
        # 依据读取缺失时保留已确认的嵌套关系，但不能将整张单据标记为可审核。
        if value["issues"]:
            raw["reviewIssues"] = list(dict.fromkeys([*raw["reviewIssues"], *value["issues"]]))
        payload = {"version": 3, "group": raw}
        reason = incomplete_reason(raw, 3)
        value["comparison"] = {
            "payload": payload,
            "digest": source_digest(payload),
            "ready": not reason,
            "reason": reason,
            "requestId": result.requestId,
            "readCompletedAt": result.readCompletedAt,
        }
        value["status"] = "partial" if reason else "matched"
        if reason:
            value["issues"] = list(dict.fromkeys([*value["issues"], reason]))

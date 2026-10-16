"""仅对已通过独立查询确认无母单的已知子采购类型放行缺失引用。"""

from backend.core.errors import ApiError

PARENT_FIELD = "custrecord_swc_subpo_mainpo"
PURCHASE_TYPE = "customrecord_swc_subpo"


def supports_verification(spec):
    return spec.type == PURCHASE_TYPE and spec.storage_fields.get("parent_order_no") == PARENT_FIELD


def document_error(error, label, identity, head):
    number = str(head.get("name") or identity)
    return ApiError(error.status, f"{label} {number}（内部编号 {identity}）：{error.message}")


def confirmed_empty(row, identity, head):
    if row.get("parent_state") != "empty" or row.get("parent_id") not in (None, ""):
        raise document_error(
            ApiError(422, "母采购单引用未能确认为空，记录接口与查询结果不一致，请核实后重新拉取"),
            "子采购单",
            identity,
            head,
        )
    return {"source": "suiteql", "recordId": identity, "field": PARENT_FIELD, "state": "empty"}

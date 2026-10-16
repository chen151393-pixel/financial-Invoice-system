"""事务外按批核实 REST 未返回的母单引用；只有显式空值才允许基础数据入库。"""

from backend.core.errors import ApiError

from ..policy.parent_reference_policy import (
    PARENT_FIELD,
    confirmed_empty,
    document_error,
    supports_verification,
)

BATCH = 300


def verify_missing_parents(ns, bundle, config, report):
    if not supports_verification(config.purchase):
        return {}
    pending = {identity: head for identity, head, _ in bundle["purchases"] if PARENT_FIELD not in head}
    verified = {}
    identities = list(pending)
    for start in range(0, len(identities), BATCH):
        batch = identities[start : start + BATCH]
        report("核实缺失的母采购单引用", start, len(identities))
        try:
            rows = ns.relation_rows("purchase_parent_links", batch)
        except ApiError as error:
            scope = "、".join(batch[:10])
            raise ApiError(error.status, f"子采购母单核实失败（内部编号 {scope}）：{error.message}") from None
        by_id = {}
        for row in rows:
            identity = str(row.get("id") or "")
            if identity not in batch or identity in by_id:
                raise ApiError(502, "子采购母单核实返回身份重复或超出请求范围，未保存本关联组")
            by_id[identity] = row
        for identity in batch:
            if identity not in by_id:
                raise document_error(
                    ApiError(502, "母采购单引用核实未返回此单据，不能判定为无母单"),
                    "子采购单",
                    identity,
                    pending[identity],
                )
            verified[identity] = confirmed_empty(by_id[identity], identity, pending[identity])
    if identities:
        report("母采购单引用核实完成", len(identities), len(identities))
    for identity, head in pending.items():
        number = head.get("name") or identity
        bundle["warnings"].append(
            f"子采购单 {number}（内部编号 {identity}）经 NS 查询确认未关联母采购单；"
            "基础数据已保存，币种待核实，数量和金额保留 NS 原值。"
        )
    return verified

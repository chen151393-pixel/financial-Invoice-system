"""拉取时的出库准入：从已读取的来源数据包中去掉未出库的报关单；纯转换，不读取 NS 或数据库。

2026-10-23 业务确认：没有真实报关单号或没有关联子采购单的报关单不拉取入库；
只因它被带出的子采购单一起跳过。NS 补齐后重新拉取对应日期范围即可入库。
"""

from ..mapper.ns_fields import reference, text
from ..policy.admission_policy import admission_issues


def skip_unshipped(bundle, config):
    """就地移除未出库报关单及其子采购，返回 bundle["skipped"]：[{id, number, kind, reason}]。"""
    fields = config.customs.storage_fields
    membership = bundle.get("customs_purchase_membership", {})
    skipped, removed = [], set()
    for identity, head, _ in bundle["customs"]:
        members = membership.get(identity, [])
        issues = admission_issues(text(head.get(fields["declaration_no"])), len(members))
        if issues:
            removed.add(identity)
            number = text(head.get(fields.get("record_no", ""))) or identity
            skipped.append(
                {
                    "id": identity,
                    "number": number,
                    "kind": "customs",
                    "reason": "未出库：" + "、".join(issues),
                }
            )
    if not removed:
        bundle["skipped"] = []
        return bundle["skipped"]
    owners = {member: identity for identity, members in membership.items() for member in members}
    numbers = {item["id"]: item["number"] for item in skipped}
    kept_purchases = []
    for identity, head, lines in bundle["purchases"]:
        owner = owners.get(identity) or reference(head.get(config.purchase.customs))
        if owner in removed:
            order_no = text(head.get(config.purchase.storage_fields.get("order_no", ""))) or identity
            skipped.append(
                {
                    "id": identity,
                    "number": order_no,
                    "kind": "purchase",
                    "reason": f"所属报关单 {numbers[owner]} 未出库，本次一起跳过",
                }
            )
        else:
            kept_purchases.append((identity, head, lines))
    bundle["customs"] = [entry for entry in bundle["customs"] if entry[0] not in removed]
    bundle["purchases"] = kept_purchases
    bundle["customs_purchase_membership"] = {k: v for k, v in membership.items() if k not in removed}
    bundle["skipped"] = skipped
    return skipped


def skipped_warning(skipped):
    declarations = [item for item in skipped if item["kind"] == "customs"]
    if not declarations:
        return ""
    shown = "；".join(f"{item['number']}（{item['reason'][4:]}）" for item in declarations[:10])
    more = f" 等 {len(declarations)} 张" if len(declarations) > 10 else ""
    return f"已跳过未出库报关单{more}：{shown}。NS 补齐后重新拉取对应日期即可入库。"

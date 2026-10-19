"""把整批读取的来源数据包按报关关联组拆分；纯转换，不读取 NS 或数据库。"""

from ..policy.parent_reference_policy import missing_parent_warnings, supports_verification


def split_groups(bundle, kind, rows, config):
    """返回 [(本组入口行, 本组数据包)]，顺序与本页入口单据一致。

    一组 = 一张报关单及其全部关联子采购；未关联报关的子采购单独成组。
    分组依据 NS 反查得到的报关—子采购成员关系，与逐组读取时的分组口径一致。
    """
    purchases = {entry[0]: entry for entry in bundle["purchases"]}
    customs = {entry[0]: entry for entry in bundle["customs"]}
    membership = bundle.get("customs_purchase_membership", {})
    owners = {member: identity for identity, members in membership.items() for member in members}
    evidence = bundle.get("relation_evidence", {})
    groups = {}
    for row in rows:
        if kind == "customs-declarations":
            key = ("customs", row["id"])
        else:
            parent = owners.get(row["id"])
            key = ("customs", parent) if parent else ("purchase", row["id"])
        groups.setdefault(key, []).append(row)
    result = []
    for (section, identity), entry_rows in groups.items():
        if section == "customs":
            members = membership.get(identity, [])
            part = {
                "customs": [customs[identity]],
                "customs_purchase_membership": {identity: members},
                "relation_evidence": {identity: evidence[identity]} if identity in evidence else {},
            }
        else:
            members = [identity]
            part = {"customs": [], "customs_purchase_membership": {}, "relation_evidence": {}}
        group_purchases = [purchases[member] for member in members]
        warnings = missing_parent_warnings(group_purchases) if supports_verification(config.purchase) else []
        # 母单表头、PL 名称和母单核实结果按 ID 查找，整批共享不会串组。
        result.append((entry_rows, {**bundle, **part, "purchases": group_purchases, "warnings": warnings}))
    return result

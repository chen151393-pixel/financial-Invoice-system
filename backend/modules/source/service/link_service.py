"""保存后维护报关单—子采购关联、依据状态与内容摘要；全部在保存事务中执行。

- 单头级关联（ns_reference）：来自子采购单上的 NS 报关引用；一张子采购单同一时刻只指向一张报关单。
- 行级关联（local_packing）：沿用原有规则，按已保存的子采购原始行与 Packing 依据定位唯一报关汇总行。
- NS v3 整单关联（comparison）作为依据原样保存；其行身份格式确认后再生成 ns_v3 行级关联。
- 本次未完整同步、但关联的子采购单已更新的报关单：依据标为 partial 并重算摘要，提示重新同步与审核。
"""

from ..dao import customs_declaration_dao, customs_purchase_link_dao, purchase_order_dao, raw_record_dao
from ..policy.local_relation_policy import local_line_relations
from .declaration_service import EVIDENCE_TYPE, digest, snapshot

DEPENDENCY_ISSUE = "关联子采购已更新，请重新完整同步本报关单。"


def detach_moved_orders(connection, saved_orders, customs_ids, now):
    """子采购单改挂报关单、或明细被替换后，失效指向旧报关单或已无效明细的关联。返回受影响的报关单。"""
    affected = set()
    links = customs_purchase_link_dao.active_of_orders(connection, [order["id"] for order in saved_orders])
    by_order = {order["id"]: order for order in saved_orders}
    stale = []
    for link in links:
        order = by_order[link["purchase_order_id"]]
        moved = link["customs_declaration_id"] != customs_ids.get(order["customs_ns_id"])
        line_gone = link["purchase_line_id"] and link["purchase_line_id"] not in order["line_ids"].values()
        if moved or line_gone:
            stale.append(link["id"])
            affected.add(link["customs_declaration_id"])
    customs_purchase_link_dao.mark_stale(connection, stale, now)
    return affected


def refresh_declaration(connection, account, declaration_id, order_ids, evidence, now):
    """完整同步的报关单：按本次读取重建全部关联，旧关联中不再成立的置为 stale。"""
    desired = {(order_id, None, None, "ns_reference") for order_id in order_ids}
    if evidence:
        desired |= line_links(connection, declaration_id, order_ids, evidence)
    existing = customs_purchase_link_dao.active(connection, declaration_id)
    keep = {(order, customs_line, purchase_line) for order, customs_line, purchase_line, _ in desired}
    customs_purchase_link_dao.mark_stale(
        connection,
        [
            link["id"]
            for link in existing
            if (link["purchase_order_id"], link["customs_line_id"], link["purchase_line_id"]) not in keep
        ],
        now,
    )
    for order_id, customs_line_id, purchase_line_id, kind in sorted(
        desired, key=lambda item: tuple(map(str, item))
    ):
        customs_purchase_link_dao.upsert_active(
            connection, declaration_id, order_id, customs_line_id, purchase_line_id, kind, now
        )
    status = "complete" if evidence and evidence.get("status") == "matched" else "partial"
    issues = list((evidence or {}).get("issues", [])) or (
        [] if evidence else ["本次单据快照未包含逐行关联依据，请完整同步。"]
    )
    customs_declaration_dao.update_relation(connection, declaration_id, status, issues, now)
    if evidence:
        raw_record_dao.save(connection, account, EVIDENCE_TYPE, evidence["declarationId"], evidence, now)


def line_links(connection, declaration_id, order_ids, evidence):
    """沿用原有本地行定位规则（local_relation_policy），返回行级关联集合。"""
    head = customs_declaration_dao.head(connection, declaration_id)
    details = customs_declaration_dao.lines(connection, declaration_id)
    orders = purchase_order_dao.orders(connection, sorted(order_ids))
    lines = purchase_order_dao.lines(connection, sorted(order_ids))
    bindings = local_line_relations(
        {**head, "tenant_id": "", "source_data": head["raw_payload"]},
        details,
        [{**order, "tenant_id": "", "source_data": order["raw_payload"]} for order in orders],
        lines,
        {**evidence, "mode": "full_sync"},
    )
    order_of_line = {line["id"]: line["purchase_order_id"] for line in lines}
    return {
        (order_of_line[int(line_id)], int(customs_line_id), int(line_id), "local_packing")
        for line_id, customs_line_id in bindings.items()
    }


def dependents(connection, saved_orders):
    """关联了本次保存的子采购单的报关单（内容可能已变，需重算摘要）。"""
    return customs_purchase_link_dao.declarations_of_orders(
        connection, [order["id"] for order in saved_orders]
    )


def mark_dependents(connection, declaration_ids, now):
    """未完整同步但关联已变化的报关单：依据改为 partial，提示重新同步。"""
    for declaration_id in sorted(declaration_ids):
        head = customs_declaration_dao.head(connection, declaration_id)
        issues = list(dict.fromkeys([*(head["relation_issues"] or []), DEPENDENCY_ISSUE]))
        customs_declaration_dao.update_relation(connection, declaration_id, "partial", issues, now)


def refresh_digests(connection, declaration_ids, now):
    for declaration_id in sorted(declaration_ids):
        content = snapshot(connection, declaration_id)
        customs_declaration_dao.update_digest(connection, declaration_id, digest(content), now)

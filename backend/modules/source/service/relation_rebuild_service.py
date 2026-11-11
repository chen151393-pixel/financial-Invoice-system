"""仅用持久来源重建关联，供启动补算和按单号修复共用；没有 NS 客户端依赖。"""

from datetime import datetime, timezone

from backend.core import write_lock

from ..dao import relation_rebuild_dao
from ..policy.local_relation_policy import LOCAL_RELATION_VERSION
from ..public import SourceChanged
from . import link_service
from .declaration_service import digest, snapshot, sync_lock_name


class RelationRebuildService:
    def __init__(self, engine, events):
        self.engine, self.events = engine, events

    def rebuild(self, *, record_no=None, account=None, stopping=None):
        results, after = [], 0
        while True:
            with self.engine.connect() as connection:
                rows = relation_rebuild_dao.page(connection, after, record_no=record_no, account=account)
            if not rows:
                return results
            for row in rows:
                if stopping and stopping():
                    return results
                results.append(self.rebuild_one(row["id"], row["ns_account"]))
                after = row["id"]

    def rebuild_one(self, declaration_id, account):
        # 与同步、审核相同的账户锁和账本锁；读到的快照直到事件入队提交前不会被替换。
        with (
            write_lock.locked(self.engine, sync_lock_name(self.engine, account)) as connection,
            connection.begin(),
        ):
            content = snapshot(connection, declaration_id)
            if not content or not content["declaration"]["is_active"]:
                return {"id": declaration_id, "status": "skipped", "reason": "报关单不存在或已停用"}
            head, evidence = content["declaration"], content["evidence"]
            result = {"id": declaration_id, "recordNo": head["record_no"], "account": head["ns_account"]}
            if head["ns_account"] != account:
                raise ValueError("关联重建账套不一致")
            if (
                not evidence
                or not head["raw_payload"]
                or any(not o["raw_payload"] for o in content["orders"])
            ):
                return {**result, "status": "skipped", "reason": "本地原始快照或关联依据缺失，未修改关联"}
            if (
                evidence.get("account") != account
                or str(evidence.get("declarationId")) != head["ns_internal_id"]
            ):
                return {
                    **result,
                    "status": "skipped",
                    "reason": "本地关联依据账套或报关身份不一致，未修改关联",
                }
            if link_service.DEPENDENCY_ISSUE in (head["relation_issues"] or []):
                return {
                    **result,
                    "status": "skipped",
                    "reason": "本地来源版本不一致，未使用过期 Packing 重建",
                }
            if evidence.get("localRelationVersion") == LOCAL_RELATION_VERSION:
                return {**result, "status": "current", **self.counts(content)}
            before = digest(content)
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            evidence = {**evidence, "localRelationRebuiltAt": now.isoformat()}
            link_service.refresh_declaration(
                connection, account, declaration_id, [o["id"] for o in content["orders"]], evidence, now
            )
            link_service.refresh_digests(connection, [declaration_id], now)
            updated = snapshot(connection, declaration_id)
            changed = before != digest(updated)
            if changed:
                self.events.publish(
                    connection,
                    SourceChanged(account, tuple(line["id"] for line in content["purchase_lines"])),
                )
            return {**result, "status": "rebuilt", "changed": changed, **self.counts(updated)}

    @staticmethod
    def counts(content):
        linked = {link["purchase_line_id"] for link in content["links"] if link["purchase_line_id"]}
        return {
            "linkedLines": len(linked),
            "unlinkedLines": sum(line["id"] not in linked for line in content["purchase_lines"]),
        }

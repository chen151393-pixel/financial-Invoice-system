"""工作台筛选范围与业务状态分区（纯函数）。

- 账套、供应商、报关单创建日期（中国日期）同时作用于分区计数与核对、开票待办；
- 比对待办没有单一报关单，只按账套与供应商筛选，不按报关单创建日期；
- 分区按报关单计数：待审核的为"待审批"，其余取当前任务中最慢的阶段；没有当前任务为"无需开票"，不进分区。
"""

from collections import defaultdict

from backend.modules.task.public import STAGE_LABELS, STAGES, declaration_stage


class Scope:
    def __init__(self, query, window):
        self.account = query.account
        self.supplier_id = int(query.supplierId) if query.supplierId else None
        # window：(UTC 下限, UTC 上限) 或 None
        self.window = window

    def declaration(self, row):
        if self.account and row["ns_account"] != self.account:
            return False
        if self.supplier_id and self.supplier_id not in row["supplier_ids"]:
            return False
        if self.window:
            created = row.get("ns_created_at")
            if created is None or not self.window[0] <= created < self.window[1]:
                return False
        return True

    def task(self, task, declaration):
        if self.account and task["ns_account"] != self.account:
            return False
        if self.supplier_id and task["supplier_id"] != self.supplier_id:
            return False
        if self.window:
            created = (declaration or {}).get("ns_created_at")
            if created is None or not self.window[0] <= created < self.window[1]:
                return False
        return True


def stage_counts(declarations, pending_ids, tasks, scope, admitted):
    """返回 ([{key, label, count}] 五个分区, 无需开票张数)。admitted(row) 判断报关单是否已出库。"""
    statuses = defaultdict(list)
    for task in tasks:
        statuses[task["customs_declaration_id"]].append(task["status"])
    counts = dict.fromkeys(STAGES, 0)
    none = 0
    for row in declarations:
        if not admitted(row) or not scope.declaration(row):
            continue
        if row["id"] in pending_ids:
            counts["pending_review"] += 1
            continue
        stage = declaration_stage(statuses.get(row["id"], []))
        if stage == "none":
            none += 1
        else:
            counts[stage] += 1
    return [{"key": key, "label": STAGE_LABELS[key], "count": counts[key]} for key in STAGES], none


def supplier_options(declarations, account):
    found = {}
    for row in declarations:
        if not account or row["ns_account"] == account:
            found.update(row["supplier_ids"])
    return sorted(
        ({"id": str(key), "name": name} for key, name in found.items()),
        key=lambda o: (o["name"], int(o["id"])),
    )

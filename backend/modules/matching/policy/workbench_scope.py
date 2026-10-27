"""工作台筛选范围（纯函数）。

- 账套、供应商、报关单创建日期（中国日期）同时作用于漏斗计数与核对、开票待办；
- 比对待办没有单一报关单，只按账套与供应商筛选，不按报关单创建日期。
"""


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


def supplier_options(declarations, account):
    found = {}
    for row in declarations:
        if not account or row["ns_account"] == account:
            found.update(row["supplier_ids"])
    return sorted(
        ({"id": str(key), "name": name} for key, name in found.items()),
        key=lambda o: (o["name"], int(o["id"])),
    )

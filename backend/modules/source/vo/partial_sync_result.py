"""单批逐单结果：计数仅累计确认提交的完整关联单元，不推断失败或未知为成功。"""


class PartialResult:
    def __init__(self, page):
        self.page = page
        self.saved_groups = 0
        self.interrupted = False
        self.items = {
            row["id"]: {
                "id": row["id"],
                "number": row["number"],
                "status": "not_processed",
                "reason": "本次尚未处理",
            }
            for row in page["rows"]
        }
        for failure in page.get("readFailures", []):
            self.items[failure["id"]] = {**failure, "status": "failed"}
        self.storage = {
            "savedAt": None,
            "purchase": dict.fromkeys(("created", "updated", "linesCreated", "linesUpdated"), 0),
            "customs": dict.fromkeys(("created", "updated", "linesCreated", "linesUpdated"), 0),
            "relations": dict.fromkeys(
                (
                    "declarations",
                    "collected",
                    "matched",
                    "partial",
                    "rawLines",
                    "packingLines",
                    "purchaseLinks",
                ),
                0,
            ),
            "warnings": [],
        }

    def mark(self, group, status, reason):
        for row in group:
            self.items[row["id"]].update(status=status, reason=reason)

    def add(self, saved):
        self.saved_groups += 1
        self.storage["savedAt"] = saved["savedAt"]
        for section in ("purchase", "customs", "relations"):
            for key, value in saved[section].items():
                self.storage[section][key] += value
        self.storage["warnings"] = list(dict.fromkeys(self.storage["warnings"] + saved["warnings"]))

    def response(self):
        counts = {
            key: sum(item["status"] == key for item in self.items.values())
            for key in ("saved", "failed", "unknown", "not_processed")
        }
        status = "interrupted" if self.interrupted else "partial" if counts["failed"] else "completed"
        message = f"本批入口单据：已保存 {counts['saved']} 张，失败 {counts['failed']} 张"
        if self.interrupted:
            message += f"，待核实 {counts['unknown']} 张，未处理 {counts['not_processed']} 张；已停止后续拉取"
        message += "。已确认保存的数据保留，同一报关关联组一起提交或失败"
        page = {key: value for key, value in self.page.items() if key != "readFailures"}
        return {
            **page,
            "storage": self.storage,
            "message": message,
            "batch": {
                "status": status,
                "canContinue": not self.interrupted,
                "counts": counts,
                "items": list(self.items.values()),
            },
        }

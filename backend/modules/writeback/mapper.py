"""数据库行转换为接口对象；不执行SQL或决定操作权限。"""

import json


def to_preview(row):
    return {
        "id": row["id"],
        "target": row["target"],
        "operation": row["operation"],
        "payload": json.loads(row["payload"]),
        "before": json.loads(row["snapshot"]) if row["snapshot"] else None,
        "expires": row["expires"],
        "state": row["state"],
        "result": json.loads(row["result"]) if row["result"] else None,
    }

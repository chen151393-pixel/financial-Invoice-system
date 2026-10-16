"""数据库字段与群配置响应的纯转换。"""

from datetime import UTC, datetime


def group(row):
    return {
        "groupName": row["group_name"],
        "chatId": row["chat_id"],
        "employee": row["employee"],
        "userid": row["userid"],
    }


def binding(row):
    return {
        **group(row),
        "account": row["account"],
        "supplierId": row["supplier_id"],
        "supplierName": row["supplier_name"],
        "revision": row["revision"],
        "enabled": row["enabled"],
        "updatedAt": datetime.fromtimestamp(row["updated_at"], UTC).isoformat(),
    }


def fields(data):
    return {
        "group_name": data.groupName,
        "chat_id": data.chatId,
        "employee": data.employee,
        "userid": data.userid,
    }

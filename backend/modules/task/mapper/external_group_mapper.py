"""外部群目录与接口字段映射，不执行查询。"""

from datetime import UTC, datetime


def fields(row):
    return dict(
        groupName=row["group_name"],
        chatId=row["chat_id"],
        employee=row["owner_name"],
        userid=row["owner_userid"],
        memberCount=row["member_count"],
        department=row["department"],
        createdAt=row["group_created_at"].replace(tzinfo=UTC).isoformat() if row["group_created_at"] else "",
    )


def values(group):
    created = (
        datetime.fromisoformat(group["createdAt"]).astimezone(UTC).replace(tzinfo=None)
        if group.get("createdAt")
        else None
    )
    return dict(
        group_name=group["groupName"],
        chat_id=group["chatId"],
        owner_name=group["employee"],
        owner_userid=group["userid"],
        member_count=group["memberCount"],
        department=group["department"],
        group_created_at=created,
    )


def binding_fields(group):
    return dict(
        group_name=group["groupName"],
        chat_id=group["chatId"],
        owner_name=group["employee"],
        owner_userid=group["userid"],
    )

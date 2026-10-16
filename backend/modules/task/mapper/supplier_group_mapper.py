"""供应商群绑定的展示转换，不读取数据库。"""

from ..vo.supplier_group_vo import GroupBinding
from .task_mapper import iso


def binding(row, supplier):
    return GroupBinding(
        groupName=row["group_name"],
        chatId=row["chat_id"],
        employee=row["owner_name"],
        userid=row["owner_userid"],
        account=supplier.get("ns_account", ""),
        supplierId=str(row["supplier_id"]),
        supplierName=supplier.get("name") or "供应商待确认",
        revision=row["version"],
        enabled=row["enabled"],
        updatedAt=iso(row["updated_at"]),
    )

"""供应商群绑定的展示转换，不读取数据库。"""

from ..vo.supplier_group_vo import GroupBinding, SupplierNotify
from .task_mapper import iso


def directory_status(catalog):
    return {
        "directoryUpdatedAt": catalog.get("directoryUpdatedAt"),
        "directoryStale": catalog.get("directoryStale", False),
        "directoryRefreshing": catalog.get("directoryRefreshing", False),
        "directoryRefreshError": catalog.get("directoryRefreshError", ""),
    }


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


def notify(row):
    """没有设置记录视为开启通知，版本为 0。"""
    if row is None:
        return SupplierNotify(enabled=True, revision=0)
    return SupplierNotify(
        enabled=row["notify_enabled"],
        revision=row["version"],
        updatedBy=row["updated_by"],
        updatedAt=iso(row["updated_at"]),
    )

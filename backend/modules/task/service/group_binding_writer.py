"""同一事务内保存供应商绑定，供实时维护和导入确认共用。"""

from backend.core.errors import ApiError

from ..dao import supplier_group_dao


def write_binding(
    connection, supplier_id, revision, fields, actor, now, *, replace_existing=True, enabled=True
):
    current = supplier_group_dao.by_supplier(connection, supplier_id, lock=True)
    if revision != (current["version"] if current else 0):
        raise ApiError(409, "供应商绑定已被修改，请重新查询后确认")
    if current and current["chat_id"] != fields["chat_id"] and not replace_existing:
        raise ApiError(409, "供应商已有其他默认群，请明确确认替换原绑定")
    values = {**fields, "enabled": enabled, "updated_by": actor}
    if current is None:
        supplier_group_dao.insert_group(connection, {"supplier_id": supplier_id, **values}, now)
    elif not supplier_group_dao.update_group(connection, current["id"], revision, values, now):
        raise ApiError(409, "供应商绑定已被修改，请重新查询后确认")
    return supplier_group_dao.by_supplier(connection, supplier_id)

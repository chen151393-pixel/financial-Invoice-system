"""读取既有单位字典，仅 source 模块访问该兼容表。"""

from sqlalchemy import inspect, select

from ..entity.unit_dictionary import unit_dictionary as units


def unit_names(connection):
    # 新安装环境可以没有这张人工维护的字典，缺表时保留来源值；连接和SQL错误仍向上抛出。
    if not inspect(connection).has_table(units.name):
        return {}
    rows = connection.execute(
        select(units.c.unit_id, units.c.unit_name).where(units.c.enabled == 1)
    ).mappings()
    return {
        str(row["unit_id"]): str(row["unit_name"]).strip()
        for row in rows
        if row["unit_name"] and str(row["unit_name"]).strip()
    }

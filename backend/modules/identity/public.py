"""identity 对外只读门面：其他模块把操作者标识显示为人员姓名（2026-11-10）。"""

from .dao import user_dao
from .policy.login_policy import feishu_user_id

SYSTEM_ACTORS = {"system": "系统"}


def actor_names(connection, actors):
    """{操作者标识: 显示名称}。

    飞书账号（user:fs:<user_id>）取本地飞书人员副本的姓名；人员停用后副本保留，历史记录仍可显示姓名。
    system 显示“系统”；找不到人员或其他标识（如应急管理员、服务身份）原样返回，不臆造姓名。
    """
    actors = {actor for actor in actors if actor}
    ids = {actor: feishu_user_id(actor) for actor in actors}
    names = user_dao.names_by_user_ids(connection, [user_id for user_id in ids.values() if user_id])
    return {actor: SYSTEM_ACTORS.get(actor) or names.get(ids[actor]) or actor for actor in actors}

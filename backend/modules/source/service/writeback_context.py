"""来源身份只读门面，不把分类 ID 当作 NS 子公司 ID。"""

from ..dao.writeback_context_dao import by_lines


def writeback_context(connection, line_ids):
    return by_lines(connection, line_ids)

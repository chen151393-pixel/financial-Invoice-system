"""来源身份只读门面，不把分类 ID 当作 NS 子公司 ID。"""

from ..dao.writeback_context_dao import by_lines, sub_order_counts


def writeback_context(connection, line_ids):
    return by_lines(connection, line_ids)


def parent_sub_order_counts(connection, parent_ids):
    """母单下本地有效子采购单张数；回写据此判断“母单仅一张子采购单”。"""
    return sub_order_counts(connection, parent_ids)

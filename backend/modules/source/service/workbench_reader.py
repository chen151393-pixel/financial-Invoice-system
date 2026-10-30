"""供工作台读取轻量报关来源，复用调用方的只读快照。"""

from ..dao import workbench_purchase_dao, workbench_source_dao


def workbench_declarations(connection):
    return workbench_source_dao.read(connection)


def workbench_purchases(connection):
    """全部有效报关关联的子采购含税单头金额及报关创建时间；调用方按月去重。"""
    return workbench_purchase_dao.read(connection)

"""供工作台读取轻量报关来源，复用调用方的只读快照。"""

from ..dao import workbench_source_dao


def workbench_declarations(connection):
    return workbench_source_dao.read(connection)

"""旧导入与Alembic的元数据注册入口；SQL实现位于各模块DAO。"""

from .core.database import make_engine as make_engine
from .core.schema import metadata as metadata
from .modules.audit.entity import audit as audit
from .modules.audit.entity import finance_audit as finance_audit
from .modules.audit.entity import previews as previews
from .modules.audit.entity import target_locks as target_locks
from .modules.reconciliation.entity import reviews as reviews
from .modules.reconciliation.entity import snapshots as snapshots

# 保留历史应用库迁移的结构校验；群配置运行时只读写独立业务库。
from .modules.reconciliation.group_entity import bindings as bindings
from .modules.reconciliation.task_entity import tasks as tasks

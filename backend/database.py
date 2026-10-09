"""旧导入与Alembic的元数据注册入口；SQL实现位于各模块DAO。"""

from .core.database import make_engine as make_engine
from .core.schema import metadata as metadata
from .modules.audit.entity import audit as audit
from .modules.audit.entity import finance_audit as finance_audit
from .modules.reconciliation.entity import reviews as reviews
from .modules.reconciliation.entity import snapshots as snapshots
from .modules.reconciliation.task_entity import tasks as tasks
from .modules.writeback.entity import previews as previews
from .modules.writeback.entity import target_locks as target_locks

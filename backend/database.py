"""旧导入与Alembic的元数据注册入口；SQL实现位于各模块DAO。"""

from .core.database import make_engine as make_engine
from .core.schema import metadata as metadata
from .modules.audit.entity import audit as audit
from .modules.writeback.entity import previews as previews
from .modules.writeback.entity import target_locks as target_locks

"""旧Workflow导入兼容入口；保留既有集成及回归测试。"""

from .modules.writeback.policy import encode as encode
from .modules.writeback.policy import fingerprint as fingerprint
from .modules.writeback.policy import millis as millis
from .modules.writeback.service import WritebackService as Workflow

__all__ = ["Workflow", "encode", "fingerprint", "millis"]

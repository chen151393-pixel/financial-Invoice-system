"""旧配置导入的兼容入口；新代码使用 backend.core.config。"""

from .core.config import ROOT as ROOT
from .core.config import Settings as Settings
from .core.config import load_settings as load_settings

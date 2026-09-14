"""审计模块对其他模块公开的事务内记录接口。"""

from .dao import append as record

__all__ = ["record"]

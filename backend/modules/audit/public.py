"""审计模块对其他模块公开的事务内记录接口。"""

from .dao import append_finance as record_finance_review

__all__ = ["record_finance_review"]

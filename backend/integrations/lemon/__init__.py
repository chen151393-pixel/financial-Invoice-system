"""柠檬云 open2 记账开放平台适配器包。

仅做外部系统客户端：鉴权（auth）、配置（config）、发票读取与字段映射（source/mapper）。
不写数据库、不决定业务状态；落库与编排由 invoice / sync 模块负责。
"""

from .auth import FileTokenStore, LemonOpen2Auth, Token, TokenStore
from .config import LemonOpen2Settings, load_lemon_open2_settings
from .mapper import INVOICE_CATEGORY_INPUT, map_invoice, map_lines
from .source import InvoiceRecord, LemonInvoiceSource, Open2LemonSource

__all__ = [
    "LemonOpen2Settings",
    "load_lemon_open2_settings",
    "LemonOpen2Auth",
    "Token",
    "TokenStore",
    "FileTokenStore",
    "LemonInvoiceSource",
    "Open2LemonSource",
    "InvoiceRecord",
    "map_invoice",
    "map_lines",
    "INVOICE_CATEGORY_INPUT",
]

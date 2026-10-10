"""PL 联查字段由服务器配置，不允许浏览器指定任意记录或筛选表达式。"""

from typing import Annotated, Literal

from pydantic import Field, ValidationError

from backend.core.dto import StrictModel
from backend.core.errors import ApiError

Identifier = Annotated[str, Field(pattern=r"^[A-Za-z][A-Za-z0-9_]{0,99}$")]
Column = Literal[
    "declaration",
    "date",
    "sales",
    "parent",
    "purchase",
    "origin",
    "vendor",
    "name",
    "spec",
    "quantity",
    "unit",
    "price",
    "amount",
    "currency",
]


class RecordSpec(StrictModel):
    type: Identifier
    fields: dict[Column, Identifier] = Field(default_factory=dict)
    storage_fields: dict[str, Identifier] = Field(default_factory=dict)
    omitted_as_null: list[Literal["declaration_no", "declaration_date"]] = Field(default_factory=list)


class PlSpec(RecordSpec):
    number: Identifier


class PurchaseSpec(RecordSpec):
    pl: Identifier
    customs: Identifier
    company: Identifier


class LineSpec(RecordSpec):
    parent: Identifier


class CustomsLineSpec(LineSpec):
    pl: Identifier
    company: Identifier


class LookupConfig(StrictModel):
    company_record_type: Identifier | None = None
    pl: PlSpec
    purchase: PurchaseSpec
    purchase_line: LineSpec
    customs: RecordSpec
    customs_line: CustomsLineSpec


def parse_config(settings):
    if not settings.pl_lookup:
        raise ApiError(503, "PL 单联查尚未配置：请管理员配置 PL、采购明细、报关单及明细字段映射")
    try:
        config = LookupConfig.model_validate(settings.pl_lookup)
    except ValidationError:
        raise ApiError(503, "PL 单联查字段映射不完整或格式错误，请管理员核对配置文档") from None
    for spec in (config.pl, config.purchase, config.purchase_line, config.customs, config.customs_line):
        if spec.type not in settings.record_types:
            raise ApiError(503, f"PL 单联查记录类型未加入读取白名单：{spec.type}")
    return config

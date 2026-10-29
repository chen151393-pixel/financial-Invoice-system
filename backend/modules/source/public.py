"""source 对外只读门面与来源变化事件。"""

from dataclasses import dataclass

from .dao.purchase_order_dao import lines as purchase_order_lines
from .dao.unit_dictionary_dao import unit_names
from .policy.admission_policy import admission_issues, admission_reason
from .policy.declared_price_policy import (
    declared_cny,
    declared_unit_price,
    declared_unit_price_cny,
    pick_sales_order,
)
from .policy.unit_policy import unit_label
from .service.contract_service import SubpoContractSource
from .service.declaration_service import DeclarationService, digest, snapshot
from .service.declared_price_reader import declared_prices
from .service.directory_service import SourceDirectory, china_day_range
from .service.pl_comparison_service import PlScriptService
from .service.purchase_context import line_declarations, purchase_lines, supplier_line_ids
from .service.workbench_reader import workbench_declarations
from .service.writeback_context import writeback_context

__all__ = [
    "purchase_order_lines",
    "writeback_context",
    # 报关单准入（已出库）：有真实报关单号且有关联子采购单
    "admission_issues",
    "admission_reason",
    "workbench_declarations",
    "unit_names",
    "unit_label",
    # 采购报关联查（实时 NS）与子采购合同
    "PlScriptService",
    "SubpoContractSource",
    # 报关单读取（review）：DeclarationService 提供分页/索引/完整内容/审核锁；
    # snapshot、digest 供调用方在 DeclarationService.locked() 的同一连接中读取并核对摘要
    "DeclarationService",
    "digest",
    "snapshot",
    # 来源目录（task）：供应商、采购公司、子采购单号与行品名的只读查询
    "SourceDirectory",
    # 子采购行比对上下文（matching）：purchase_lines(connection, line_ids) → {ID: 上下文含 digest}
    "purchase_lines",
    "supplier_line_ids",
    # 子采购行所属子采购单号与报关单 ID（matching 归档发票文件）
    "line_declarations",
    # 申报价换算为人民币（按对应销售单汇率）：review 申报幅度、matching 价格校验；
    # declared_unit_price 给出原币申报单价及是否试算（NS 未填时按报关金额 ÷ 报关数量）
    "declared_cny",
    "declared_unit_price",
    "declared_unit_price_cny",
    "pick_sales_order",
    "declared_prices",
    # 中国日期区间换算为 UTC 区间（报关单创建日期筛选）
    "china_day_range",
    "SourceChanged",
]


@dataclass(frozen=True)
class SourceChanged:
    ns_account: str
    purchase_line_ids: tuple[int, ...]
    reason: str = "采购来源关键内容变化，需重新审核"

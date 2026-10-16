"""source 对外只读门面与来源变化事件。"""

from dataclasses import dataclass

from .dao.unit_dictionary_dao import unit_names
from .policy.unit_policy import unit_label
from .service.contract_service import SubpoContractSource
from .service.declaration_service import DeclarationService, digest, snapshot
from .service.directory_service import SourceDirectory
from .service.pl_comparison_service import PlScriptService
from .service.purchase_context import purchase_lines

__all__ = [
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
    "SourceChanged",
]


@dataclass(frozen=True)
class SourceChanged:
    ns_account: str
    purchase_line_ids: tuple[int, ...]
    reason: str = "采购来源关键内容变化，需重新审核"

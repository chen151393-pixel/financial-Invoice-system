"""source 模块对外门面：其他模块唯一可以导入的文件。

架构第 4a 步：NS 来源读取逻辑已从 business 移入本模块。旧 business / reconciliation 在第 4e 步
删除前，经下方"过渡期导出"使用这些能力；第 4e 步删除旧模块时一并删除过渡期导出。
"""

from .dto.pl_comparison import PlScriptQuery
from .mapper.ns_fields import normalize, reference, text
from .policy.local_relation_policy import local_line_relations
from .policy.ns_config import parse_config
from .policy.relation_policy import comparison_view, incomplete_reason, source_digest
from .service.contract_service import SubpoContractSource
from .service.declaration_service import DeclarationService, digest, snapshot
from .service.directory_service import SourceDirectory
from .service.ns_reader import PlReader
from .service.pl_comparison_service import PlScriptService
from .service.relation_matcher import require_relation_interfaces
from .service.relation_reader import RelationReader

__all__ = [
    # 采购报关联查（实时 NS）与子采购合同
    "PlScriptQuery",
    "PlScriptService",
    "SubpoContractSource",
    # 报关单读取（review）：DeclarationService 提供分页/索引/完整内容/审核锁；
    # snapshot、digest 供调用方在 DeclarationService.locked() 的同一连接中读取并核对摘要
    "DeclarationService",
    "digest",
    "snapshot",
    # 来源目录（task）：供应商、采购公司、子采购单号与行品名的只读查询
    "SourceDirectory",
    # 过渡期导出：仅供旧 business / reconciliation 使用，第 4e 步删除
    "PlReader",
    "RelationReader",
    "comparison_view",
    "incomplete_reason",
    "local_line_relations",
    "normalize",
    "parse_config",
    "reference",
    "require_relation_interfaces",
    "source_digest",
    "text",
]

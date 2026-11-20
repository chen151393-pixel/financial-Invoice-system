"""settlement 模块拥有的表；导入本包即登记到 schema_metadata。"""

from .bank_receipt import settlement_bank_receipts
from .batch import settlement_batches
from .batch_item import settlement_batch_items
from .bill import settlement_bills
from .contract import settlement_contracts
from .document_group import settlement_document_group_items, settlement_document_groups
from .hk_slip import settlement_hk_slips
from .party import settlement_parties

__all__ = [
    "settlement_hk_slips",
    "settlement_bank_receipts",
    "settlement_batches",
    "settlement_batch_items",
    "settlement_bills",
    "settlement_contracts",
    "settlement_parties",
    "settlement_document_groups",
    "settlement_document_group_items",
]

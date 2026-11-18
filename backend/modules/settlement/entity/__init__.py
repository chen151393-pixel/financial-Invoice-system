"""settlement 模块拥有的表；导入本包即登记到 schema_metadata。"""

from .bank_receipt import settlement_bank_receipts
from .batch import settlement_batches
from .batch_item import settlement_batch_items
from .bill import settlement_bills
from .contract import settlement_contracts
from .party import settlement_parties

__all__ = [
    "settlement_bank_receipts",
    "settlement_batches",
    "settlement_batch_items",
    "settlement_bills",
    "settlement_contracts",
    "settlement_parties",
]

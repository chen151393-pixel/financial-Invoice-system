"""review 模块拥有的表；导入本包即登记到 schema_metadata。"""

from .line import lines
from .record import records

__all__ = ["lines", "records"]

from .calculation_job import calculation_jobs as calculation_jobs
from .customs_approval import customs_approvals as customs_approvals
from .customs_receipt import customs_receipt_lines as customs_receipt_lines
from .customs_receipt import customs_receipts as customs_receipts
from .declaration_snapshot import declaration_snapshots as declaration_snapshots
from .purchase_basis import bases as bases
from .snapshot_supplier import snapshot_suppliers as snapshot_suppliers

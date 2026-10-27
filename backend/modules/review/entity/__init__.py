"""review 模块拥有的表；导入本包即登记到 schema_metadata。"""

from .line import lines
from .record import records

__all__ = ["lines", "records"]

from .calculation_job import calculation_jobs as calculation_jobs
from .declaration_snapshot import declaration_snapshots as declaration_snapshots
from .purchase_basis import bases as bases
from .snapshot_supplier import snapshot_suppliers as snapshot_suppliers

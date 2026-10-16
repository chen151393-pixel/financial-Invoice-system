"""供应商档案：来源门面分页读取真实供应商，叠加本模块群绑定。"""

from sqlalchemy.exc import SQLAlchemyError

from backend.core.errors import ApiError

from ..dao import supplier_group_dao
from ..mapper.supplier_group_mapper import binding
from ..vo.supplier_group_vo import SupplierProfileList
from .supplier_group_service import SupplierGroupService


class SupplierProfileService:
    def __init__(self, engine, directory):
        self.engine, self.directory = engine, directory

    def browse(self, query, actor):
        try:
            with self.engine.connect() as connection:
                included = (
                    supplier_group_dao.supplier_ids(connection, enabled=query.status == "enabled")
                    if query.status in ("enabled", "disabled")
                    else None
                )
                excluded = supplier_group_dao.supplier_ids(connection) if query.status == "unbound" else []
                matched = (
                    supplier_group_dao.supplier_ids(connection, keyword=query.keyword)
                    if query.keyword
                    else []
                )
            found = self.directory.suppliers(
                query.account,
                query.keyword,
                query.page,
                query.pageSize,
                include_ids=included,
                exclude_ids=excluded,
                matching_ids=matched,
            )
            with self.engine.connect() as connection:
                bindings = supplier_group_dao.by_suppliers(connection, [row["id"] for row in found["items"]])
        except SQLAlchemyError:
            raise ApiError(503, "供应商档案读取失败，请检查业务数据库") from None
        return SupplierProfileList(
            items=[
                {
                    "supplierId": str(row["id"]),
                    "supplierName": row["name"],
                    "account": row["ns_account"],
                    "nsInternalId": row["ns_internal_id"],
                    "binding": binding(bindings[row["id"]], row) if row["id"] in bindings else None,
                }
                for row in found["items"]
            ],
            total=found["total"],
            page=query.page,
            pageSize=query.pageSize,
            pages=max(1, (found["total"] + query.pageSize - 1) // query.pageSize),
            manage=SupplierGroupService.capability(actor),
        )

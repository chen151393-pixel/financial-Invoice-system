"""业务数据公开入口：本地采购快照，以及只读NS核对查询契约。"""

import hashlib
from contextlib import contextmanager

from sqlalchemy.exc import SQLAlchemyError

from backend.core.errors import ApiError

from . import dao
from .contract_service import SubpoContractSource as SubpoContractSource
from .dao import matching_sources
from .dto import PlScriptQuery as PlScriptQuery
from .entity import load_tables
from .pl_script_service import PlScriptService as PlScriptService
from .reconciliation_dao import read_declarations
from .relation_mapper import summarize_relations
from .relation_policy import incomplete_reason as incomplete_relation_reason
from .relation_policy import source_digest as relation_digest
from .review_source_mapper import review_sources
from .supplier_service import SupplierDirectory as SupplierDirectory

__all__ = [
    "SupplierDirectory",
    "SubpoContractSource",
    "CustomsReconciliationSource",
    "PurchaseMatchingSource",
    "PlScriptQuery",
    "PlScriptService",
    "incomplete_relation_reason",
    "relation_digest",
]


class CustomsReconciliationSource:
    """按登录身份分页读取本地报关单及 NS 直接关联的子采购单。"""

    def __init__(self, engine):
        self.engine = engine

    def read(self, owner, **criteria):
        if self.engine is None:
            raise ApiError(503, "业务数据库未配置，请先配置并同步报关与采购单据")
        tenant = hashlib.sha256(owner.encode()).hexdigest()
        try:
            with self.engine.connect() as connection, connection.begin():
                tables = load_tables(connection, include_relations=True)
                approved = []
                for row in criteria.pop("approved", ()):
                    current = self._read_one(
                        connection, tables, tenant, row["account"], row["declaration_id"]
                    )
                    if len(current["heads"]) != 1:
                        continue
                    head_id = current["heads"][0]["id"]
                    if row.get("source") == "database":
                        digest = current["review_sources"][head_id]["digest"]
                    else:
                        comparison = current["relations"].get(head_id, {}).get("comparison")
                        digest = comparison["digest"] if comparison else None
                    if digest == row["digest"]:
                        approved.append(row)
                data = read_declarations(connection, tables, tenant, approved=approved, **criteria)
                return review_sources(summarize_relations(data))
        except SQLAlchemyError:
            raise ApiError(503, "报关与采购数据读取失败，请检查业务数据库及迁移状态") from None

    def _read_one(self, connection, tables, tenant, account, declaration_id):
        data = read_declarations(
            connection,
            tables,
            tenant,
            keyword="",
            account=account,
            declaration_id=declaration_id,
            page=1,
            page_size=2,
            include_rows=True,
        )
        return review_sources(summarize_relations(data))

    def read_one(self, owner, account, declaration_id):
        """返回同身份、同账套的一张当前报关单及其完整本地证据。"""
        if self.engine is None:
            raise ApiError(503, "业务数据库未配置")
        tenant = hashlib.sha256(owner.encode()).hexdigest()
        try:
            with self.engine.connect() as connection, connection.begin():
                tables = load_tables(connection, include_relations=True)
                return self._read_one(connection, tables, tenant, account, declaration_id)
        except SQLAlchemyError:
            raise ApiError(503, "报关与采购数据读取失败，请检查业务数据库及迁移状态") from None

    @contextmanager
    def locked_review(self, owner, account, declaration_id):
        """审核期间复用同步账户锁，防止本地来源在确认事务中被同步替换。"""
        if self.engine is None:
            raise ApiError(503, "业务数据库未配置")
        tenant = hashlib.sha256(owner.encode()).hexdigest()
        lock = hashlib.sha256(f"pl-save:{self.engine.url.database}:{tenant}:{account}".encode()).hexdigest()
        with self.engine.connect() as connection:
            mysql = connection.dialect.name == "mysql"
            with connection.begin():
                acquired = dao.acquire_sync_lock(connection, lock) if mysql else True
            if not acquired:
                raise ApiError(409, "此账套正在同步或审核，请稍后重新查询")
            try:
                with connection.begin():
                    tables = load_tables(connection, include_relations=True)
                    data = self._read_one(connection, tables, tenant, account, declaration_id)
                    if len(data["heads"]) != 1:
                        raise ApiError(409, "报关单已停用或来源范围发生变化，请重新查询")
                    yield data
            finally:
                if mysql:
                    try:
                        if connection.in_transaction():
                            connection.rollback()
                        with connection.begin():
                            dao.release_sync_lock(connection, lock)
                    except SQLAlchemyError:
                        connection.invalidate()


class PurchaseMatchingSource:
    def __init__(self, engine):
        self.engine = engine

    def read(self, owner, connection=None):
        if self.engine is None:
            raise ApiError(503, "业务数据库未配置")
        tenant = hashlib.sha256(owner.encode()).hexdigest()
        if connection is not None:
            return matching_sources(
                connection, load_tables(connection, include_parents=True), tenant, lock=True
            )
        try:
            with self.engine.connect() as connection, connection.begin():
                return matching_sources(connection, load_tables(connection, include_parents=True), tenant)
        except SQLAlchemyError:
            raise ApiError(503, "采购快照读取失败，请检查业务数据库") from None

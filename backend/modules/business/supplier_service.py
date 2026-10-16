"""供应商目录的公开查询服务，仅使用已同步的有效采购来源。"""

import hashlib

from sqlalchemy.exc import SQLAlchemyError

from backend.core.errors import ApiError

from . import supplier_dao
from .entity import load_tables


class SupplierDirectory:
    def __init__(self, engine):
        self.engine = engine

    def read(self, owner, **criteria):
        if self.engine is None:
            raise ApiError(503, "业务数据库未配置，请先同步采购供应商")
        try:
            with self.engine.connect() as connection, connection.begin():
                return supplier_dao.suppliers(
                    connection,
                    load_tables(connection),
                    hashlib.sha256(owner.encode()).hexdigest(),
                    **criteria,
                )
        except SQLAlchemyError:
            raise ApiError(503, "供应商读取失败，请检查业务数据库及采购同步状态") from None

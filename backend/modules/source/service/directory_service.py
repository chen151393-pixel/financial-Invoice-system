"""来源目录（只读门面）：供应商、采购公司、子采购单号与子采购行品名。

供 task 模块展示任务、搜索任务和维护供应商群使用；只返回普通字典，不暴露表结构。
含已停用的来源记录，保证历史任务仍能显示名称。
"""

from sqlalchemy.exc import SQLAlchemyError

from backend.core.errors import ApiError

from ..dao import company_dao, purchase_order_dao, supplier_dao

SEARCH_LIMIT = 500


class SourceDirectory:
    def __init__(self, engine):
        self.engine = engine

    def _read(self, read):
        if self.engine is None:
            raise ApiError(503, "业务数据库未配置")
        try:
            with self.engine.connect() as connection:
                return read(connection)
        except SQLAlchemyError:
            raise ApiError(503, "来源数据读取失败，请检查业务数据库及迁移状态") from None

    def describe(self, *, supplier_ids=(), company_ids=(), order_ids=(), line_ids=()):
        """按 ID 批量取名称：suppliers {id: {name, ns_account, active}}、companies {id: name}、
        orders {id: order_no}、lines {id: {item_name, declaration_name, specification}}。"""

        def read(connection):
            return {
                "suppliers": supplier_dao.names(connection, sorted(set(supplier_ids))),
                "companies": company_dao.names(connection, sorted(set(company_ids))),
                "orders": purchase_order_dao.numbers(connection, sorted(set(order_ids))),
                "lines": purchase_order_dao.line_names(connection, sorted(set(line_ids))),
            }

        return self._read(read)

    def search(self, keyword):
        """名称包含关键字的供应商 ID、单号包含关键字的子采购单 ID（各最多 500 个）。"""

        def read(connection):
            return {
                "supplier_ids": supplier_dao.ids_like(connection, keyword, SEARCH_LIMIT),
                "order_ids": purchase_order_dao.ids_like(connection, keyword, SEARCH_LIMIT),
            }

        return self._read(read)

    def suppliers(self, account, keyword, page, page_size):
        """有效供应商分页：{total, items: [{id, ns_account, name}]}。"""

        def read(connection):
            total, rows = supplier_dao.page(connection, account, keyword, (page - 1) * page_size, page_size)
            return {"total": total, "items": rows}

        return self._read(read)

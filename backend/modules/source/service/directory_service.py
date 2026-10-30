"""来源目录（只读门面）：供应商、采购公司、子采购单号与子采购行品名。

供 task 模块展示任务、搜索任务和维护供应商群使用；只返回普通字典，不暴露表结构。
含已停用的来源记录，保证历史任务仍能显示名称。
"""

from datetime import datetime, time, timedelta

from sqlalchemy.exc import SQLAlchemyError

from backend.core.errors import ApiError

from ..dao import company_dao, customs_declaration_dao, purchase_order_dao, supplier_dao
from ..dao.unit_dictionary_dao import unit_names

CHINA_OFFSET = timedelta(hours=8)

SEARCH_LIMIT = 500


def china_day_range(start, end):
    """中国日期区间 [start, end] 换算为 UTC 无时区时间区间 [lower, upper)。"""
    lower = datetime.combine(start, time.min) - CHINA_OFFSET
    upper = datetime.combine(end + timedelta(days=1), time.min) - CHINA_OFFSET
    return lower, upper


def declaration_ids_created(connection, start, end):
    """在调用方快照内读取 NS 创建日期（中国日期，含首尾）对应的报关单 ID。"""
    lower, upper = china_day_range(start, end)
    return customs_declaration_dao.ids_created_between(connection, lower, upper)


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
                "units": unit_names(connection),
            }

        return self._read(read)

    def declarations(self, declaration_ids):
        """归档用报关单头：{id: {record_no, declaration_no, created_at}}，created_at 为 NS 创建时间（UTC）。"""
        return self._read(
            lambda connection: customs_declaration_dao.archive_heads(connection, sorted(set(declaration_ids)))
        )

    def declaration_ids_created(self, start, end):
        """NS 创建日期（中国日期）在 start—end（含）之间的报关单 ID。"""
        return self._read(lambda connection: declaration_ids_created(connection, start, end))

    def orders_by_number(self, order_no):
        """按子采购单号精确查找有效子采购单：[{id, order_no, customs_declaration_id}]。"""
        return self._read(lambda connection: purchase_order_dao.with_declarations(connection, exact=order_no))

    def orders_in_text(self, value):
        """查找单号出现在文本（如文件名）中的有效子采购单：[{id, order_no, customs_declaration_id}]。"""
        return self._read(lambda connection: purchase_order_dao.with_declarations(connection, within=value))

    def search(self, keyword):
        """名称包含关键字的供应商 ID、单号包含关键字的子采购单 ID（各最多 500 个）。"""

        def read(connection):
            return {
                "supplier_ids": supplier_dao.ids_like(connection, keyword, SEARCH_LIMIT),
                "order_ids": purchase_order_dao.ids_like(connection, keyword, SEARCH_LIMIT),
            }

        return self._read(read)

    def search_task_filters(self, *, supplier_name="", purchase_order_no=""):
        """任务组合查询：分别匹配供应商名称与子采购单号，不截断匹配 ID；None 表示不限。"""
        return self._read(
            lambda connection: {
                "supplier_ids": supplier_dao.ids_like(connection, supplier_name, None)
                if supplier_name
                else None,
                "order_ids": purchase_order_dao.ids_like(connection, purchase_order_no, None)
                if purchase_order_no
                else None,
            }
        )

    def suppliers(
        self,
        account,
        keyword,
        page,
        page_size,
        *,
        include_ids=None,
        exclude_ids=(),
        matching_ids=(),
        name_terms=(),
    ):
        """有效供应商分页；可按 ID 集合包含/排除，matching_ids 与名称关键词取并集。

        返回 {total, items: [{id, ns_account, ns_internal_id, name}]}，不暴露来源表。
        """

        def read(connection):
            total, rows = supplier_dao.page(
                connection,
                account,
                keyword,
                (page - 1) * page_size,
                page_size,
                include_ids=include_ids,
                exclude_ids=exclude_ids,
                matching_ids=matching_ids,
                name_terms=name_terms,
            )
            return {"total": total, "items": rows}

        return self._read(read)

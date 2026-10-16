"""进项发票查询：列表（搜索、状态、日期、分页、按币种汇总）与详情。"""

from sqlalchemy.exc import SQLAlchemyError

from backend.core.errors import ApiError

from ..dao import header_dao, item_dao
from ..mapper import invoice_mapper
from ..vo.invoice_vo import AmountSummary, InvoiceList


class InvoiceService:
    def __init__(self, engine):
        self.engine = engine

    def _connect(self):
        if self.engine is None:
            raise ApiError(503, "业务数据库未配置")
        return self.engine.connect()

    def browse(self, query):
        try:
            with self._connect() as connection:
                total, amounts, rows = header_dao.page(connection, query)
        except SQLAlchemyError:
            raise ApiError(503, "发票查询失败，请检查业务数据库及迁移状态") from None
        return InvoiceList(
            total=total,
            page=query.page,
            pageSize=query.page_size,
            hasPrevious=query.page > 1,
            hasNext=query.page * query.page_size < total,
            rows=[invoice_mapper.row(row, row["line_count"]) for row in rows],
            amounts=[
                AmountSummary(
                    currency=row["currency"],
                    count=row["count"],
                    net=invoice_mapper.text(row["net"]),
                    tax=invoice_mapper.text(row["tax"]),
                    gross=invoice_mapper.text(row["gross"]),
                )
                for row in amounts
            ],
        )

    def detail(self, invoice_id):
        try:
            with self._connect() as connection:
                found = header_dao.by_ids(connection, [invoice_id])
                item_rows = item_dao.by_invoices(connection, [invoice_id])
        except SQLAlchemyError:
            raise ApiError(503, "发票详情读取失败，请检查业务数据库") from None
        if not found:
            raise ApiError(404, "发票不存在")
        return invoice_mapper.detail(found[0], [row for row in item_rows if row["is_active"]])

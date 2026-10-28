"""两种审核队列共用搜索范围，通过门面读取 ID，不截断匹配结果。"""

from backend.core.search_terms import search_terms
from backend.modules.invoice.public import invoice_ids_between
from backend.modules.source.public import supplier_line_ids


def queue_scope(connection, query):
    return {
        "line_ids": set(
            supplier_line_ids(
                connection,
                int(query.supplierId) if query.supplierId else None,
                name_terms=search_terms(query.supplierName),
            )
        )
        if query.supplierId or query.supplierName
        else None,
        "invoice_ids": set(
            invoice_ids_between(
                connection,
                query.invoiceFrom,
                query.invoiceTo,
                number_terms=search_terms(query.invoiceNo),
            )
        )
        if query.invoiceFrom or query.invoiceNo
        else None,
    }

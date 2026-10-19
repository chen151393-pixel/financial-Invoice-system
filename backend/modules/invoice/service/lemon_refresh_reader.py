"""补拉入口只读取得本地发票来源身份；不向调用方暴露原始票据正文。"""

from ..dao import header_dao


def read_lemon_refresh_targets(connection, invoice_ids):
    fields = (
        "id",
        "source",
        "lemon_account",
        "external_id",
        "invoice_date",
        "invoice_no",
        "business_type",
        "current_version_id",
    )
    return [{key: row[key] for key in fields} for row in header_dao.by_ids(connection, invoice_ids)]

"""已入库发票账套选项：仅查询本地数据，不要求当前上游授权可用。"""

from sqlalchemy.exc import SQLAlchemyError

from backend.core.errors import ApiError
from backend.modules.invoice.public import read_invoice_accounts

from ..dao import lemon_binding_dao, lemon_run_dao
from ..policy.lemon_detail_policy import account_namespace


def invoice_accounts(binding, owner):
    settings = binding.settings
    if owner != f"user:{settings.admin_user}":
        raise ApiError(403, "只有本系统管理员可查询发票账套")
    if binding.engine is None:
        raise ApiError(503, "业务数据库未配置")
    scope = binding._scope(owner)
    try:
        with binding.engine.connect() as connection:
            accounts = read_invoice_accounts(connection)
            names = lemon_run_dao.account_names(connection, scope)
            current = lemon_binding_dao.get(connection, scope)
    except SQLAlchemyError:
        raise ApiError(503, "账套选项读取失败，请检查业务数据库及迁移状态") from None
    if current and current["selected_asid"] and current["selected_name"]:
        names.insert(0, {"asid": current["selected_asid"], "account_name": current["selected_name"]})
    labels = {"lemon": "Excel 导入（账套未对齐）"}
    for row in names:
        for professional, edition in ((True, "专业版"), (False, "默认版")):
            key = account_namespace(settings.lemon_host, row["asid"], professional)
            labels.setdefault(key, f"{row['account_name']}（{edition} · {row['asid']}）")
    return {
        "items": [
            {"value": account, "label": labels.get(account, f"历史账套（名称未记录 · {account}）")}
            for account in accounts
        ]
    }

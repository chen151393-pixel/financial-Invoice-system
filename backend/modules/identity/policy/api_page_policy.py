"""已认证接口与页面的对应；使用服务端路由模板，未知入口默认不放行。

先匹配页面复用的查询，再匹配模块。页面授权不取消已有管理员、写入开关等限制。
"""

SHARED = {
    ("GET", "/api/matching/invoice-totals"): ("invoices",),
    ("POST", "/api/matching/invoices/query"): ("invoices",),
    ("POST", "/api/matching/summaries"): ("invoices", "match"),
    ("POST", "/api/matching/proposals/generate"): ("invoices", "match"),
    ("POST", "/api/source/relations/rebuild"): ("sync",),
    ("GET", "/api/sync/lemon/invoices/accounts"): ("invoices", "sync"),
    ("POST", "/api/sync/lemon/invoices/detail-actions"): ("invoices", "sync"),
    ("POST", "/api/sync/lemon/invoices/refresh-details"): ("invoices", "sync"),
    ("GET", "/api/sync/lemon/runs/{request_id}"): ("invoices", "sync"),
    ("GET", "/api/writeback/invoices/{invoice_id}"): ("match", "writeback"),
    ("POST", "/api/writeback/invoices/{invoice_id}/recheck"): ("match", "writeback"),
}
PREFIXES = (
    ("/api/identity", ("access",)),
    ("/api/matching/workbench", ("workbench",)),
    ("/api/tasks/supplier-groups", ("supplier-profiles",)),
    ("/api/task/supplier-groups", ("supplier-profiles",)),
    ("/api/tasks/external-groups", ("supplier-profiles",)),
    ("/api/tasks", ("invoice-followup",)),
    ("/api/task", ("invoice-followup",)),
    ("/api/review/customs-receipts", ("customs-match",)),
    ("/api/review", ("finance",)),
    ("/api/invoices", ("invoices",)),
    ("/api/matching", ("match",)),
    ("/api/writeback", ("writeback",)),
    ("/api/source/pl-comparison", ("pl",)),
    ("/api/source/vendor-bills", ("writeback",)),
    ("/api/sync", ("sync",)),
    ("/api/ns", ("sync",)),
)


def required_pages(method, route):
    if route == "/api/session":
        return None
    if route == "/api/openapi.json":
        return ("access",)
    shared = SHARED.get((method, route))
    if shared is not None:
        return shared
    for prefix, pages in PREFIXES:
        if route == prefix or route.startswith(prefix + "/"):
            return pages
    return ()

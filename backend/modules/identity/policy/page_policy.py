"""页面访问目录；具体业务操作继续执行其所属模块的校验。"""

from .role_policy import ROLES

PAGES = (
    ("workbench", "总体工作台", "工作空间", "查看业务概况与待办"),
    ("finance", "财务核对", "财务", "报关与采购口径核对"),
    ("customs-match", "报关单比对", "财务", "导入海关回执并比对报关明细"),
    ("invoices", "进项发票", "财务", "查询发票与票面明细"),
    ("match", "发票比对", "财务", "查看发票与采购关联"),
    ("invoice-followup", "开票跟进", "采购", "跟进合同、通知和收票"),
    ("supplier-profiles", "供应商档案", "采购", "维护供应商与群资料"),
    ("pl", "采购报关联查", "采购", "查询采购及报关来源"),
    ("writeback", "NS 回写", "采购", "查看回写任务与处理结果"),
    ("sync", "数据同步", "系统", "查看数据来源与同步记录"),
    ("access", "人员与权限", "系统", "管理成员角色与页面权限"),
)
PAGE_CODES = tuple(item[0] for item in PAGES)


def page_items(codes=PAGE_CODES):
    return [
        {
            "code": code,
            "label": label,
            "group": group,
            "description": description,
            "assignable": True,
        }
        for code, label, group, description in PAGES
        if code in codes
    ]


def default_pages(role):
    # 升级保留原页面范围，避免新版本突然阻断已启用成员；保存后按配置收窄。
    if role not in ROLES:
        return []
    return list(PAGE_CODES if role == "admin" else PAGE_CODES[:-1])


def effective_pages(roles, configurations):
    if "admin" in roles:
        return list(PAGE_CODES)
    granted = set()
    for role in roles:
        if role in ROLES:
            row = configurations.get(role)
            granted.update(row["pages"] if row is not None else default_pages(role))
    return [code for code in PAGE_CODES if code in granted]

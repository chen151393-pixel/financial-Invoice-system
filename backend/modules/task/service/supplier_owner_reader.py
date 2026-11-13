"""人员关联的组合目录、当前生效版本与历史读取；搜索与分页均在后端。"""

from datetime import UTC, datetime, timedelta

from backend.core.errors import ApiError
from backend.core.search_terms import search_terms
from backend.modules.identity.public import assignment_members
from backend.modules.source.public import supplier_owner_directory

from ..dao import supplier_owner_dao
from ..vo.supplier_owner_vo import OwnerHistory, OwnerItem, OwnerList, OwnerOptions, OwnerVersion


def china_today(now=None):
    return ((now or datetime.now(UTC)) + timedelta(hours=8)).date()


def version_item(row):
    return OwnerVersion(
        id=str(row["id"]),
        memberId=str(row["member_id"]),
        memberName=row["member_name"],
        effectiveDate=row["effective_date"].isoformat(),
        revision=row["id"],
        reason=row["reason"],
        actor=row["actor"],
        createdAt=row["created_at"].replace(tzinfo=UTC).isoformat(),
    )


def choices(connection):
    directory = supplier_owner_directory(connection)
    return directory, assignment_members(connection)


def options(connection):
    directory, members = choices(connection)
    return OwnerOptions(
        suppliers=[
            {"id": r["id"], "name": r["name"], "account": r["ns_account"]}
            for r in directory["suppliers"]
            if r["is_active"]
        ],
        companies=[
            {"id": r["id"], "name": r["name"], "account": r["ns_account"]}
            for r in directory["companies"]
            if r["is_active"]
        ],
        members=[{"id": int(r["id"]), "name": r["name"]} for r in members if r["active"]],
        today=china_today().isoformat(),
    )


def browse(connection, query):
    directory, _ = choices(connection)
    suppliers = {r["id"]: r for r in directory["suppliers"]}
    companies = {r["id"]: r for r in directory["companies"]}
    associations = {
        (r["supplier_id"], r["company_id"]): r for r in supplier_owner_dao.associations(connection)
    }
    pairs = {(r["supplier_id"], r["company_id"]) for r in directory["pairs"]} | set(associations)
    versions = {}
    for row in supplier_owner_dao.records(connection):
        versions.setdefault((row["supplier_id"], row["company_id"]), []).append(row)
    today, items = china_today(), []
    terms = [term.casefold() for term in search_terms(query.supplierName)]
    for supplier_id, company_id in pairs:
        supplier, company = suppliers.get(supplier_id), companies.get(company_id)
        if supplier is None or company is None:
            continue
        if terms and not any(term in supplier["name"].casefold() for term in terms):
            continue
        if query.companyId is not None and company_id != query.companyId:
            continue
        association = associations.get((supplier_id, company_id))
        history = versions.get((supplier_id, company_id), [])
        applicable = [r for r in history if r["effective_date"] <= today]
        current = applicable[-1] if applicable else None
        # 同一天后追加的版本替代该日旧计划；所有原版本仍保留在历史中。
        scheduled = {r["effective_date"]: r for r in history if r["effective_date"] > today}
        if query.memberId is not None and (current is None or current["member_id"] != query.memberId):
            continue
        if query.status == "assigned" and current is None:
            continue
        if query.status == "unassigned" and (current is not None or scheduled):
            continue
        if query.status == "scheduled" and not scheduled:
            continue
        items.append(
            OwnerItem(
                supplierId=supplier_id,
                supplierName=supplier["name"],
                nsInternalId=supplier["ns_internal_id"],
                account=supplier["ns_account"],
                companyId=company_id,
                companyName=company["name"],
                revision=association["revision"] if association else 0,
                current=version_item(current) if current else None,
                scheduled=[version_item(r) for r in scheduled.values()],
                status="assigned" if current else "scheduled" if scheduled else "unassigned",
            )
        )
    items.sort(key=lambda item: (item.supplierName, item.companyName, item.supplierId, item.companyId))
    total = len(items)
    start = (query.page - 1) * query.pageSize
    return OwnerList(
        items=items[start : start + query.pageSize],
        total=total,
        page=query.page,
        pageSize=query.pageSize,
        pages=max(1, (total + query.pageSize - 1) // query.pageSize),
        today=today.isoformat(),
    )


def history(connection, supplier_id, company_id):
    row = supplier_owner_dao.pair(connection, supplier_id, company_id)
    if row is None:
        return OwnerHistory(items=[])
    return OwnerHistory(
        items=[
            version_item(r) for r in reversed(supplier_owner_dao.records(connection, supplier_id, company_id))
        ]
    )


def validate_target(connection, body):
    directory, members = choices(connection)
    member = next((r for r in members if int(r["id"]) == body.memberId and r["active"]), None)
    if member is None:
        raise ApiError(400, "负责人不存在或已不在当前导入范围，请重新选择飞书成员")
    suppliers = {r["id"]: r for r in directory["suppliers"] if r["is_active"]}
    companies = {r["id"]: r for r in directory["companies"] if r["is_active"]}
    rows = []
    for item in sorted(body.items, key=lambda item: (item.supplierId, item.companyId)):
        supplier, company = suppliers.get(item.supplierId), companies.get(item.companyId)
        if supplier is None or company is None or supplier["ns_account"] != company["ns_account"]:
            raise ApiError(400, "供应商与采购抬头须存在且属于同一 NS 账套")
        row = supplier_owner_dao.pair(connection, item.supplierId, item.companyId)
        if (row["revision"] if row else 0) != item.revision:
            raise ApiError(409, "人员关联已被修改，请刷新列表后重新预览")
        rows.append((item, row))
    return member, rows

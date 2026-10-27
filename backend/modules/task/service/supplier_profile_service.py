"""供应商档案：来源门面分页读取真实供应商，叠加本模块群绑定与"是否开启供应商通知"设置。"""

from datetime import datetime, timedelta, timezone

from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from backend.core.errors import ApiError
from backend.core.write_lock import transaction

from ..dao import event_dao, supplier_group_dao, supplier_setting_dao
from ..mapper.supplier_group_mapper import binding, notify
from ..policy.invoicing_speed_policy import NOTIFIED, RECEIVED, SLOW_DAYS, average, task_durations
from ..vo.supplier_group_vo import InvoicingSpeed, SupplierNotify, SupplierProfileList, SupplierSpeed
from .supplier_group_service import SupplierGroupService

CONFLICT = "供应商通知设置已被他人修改，请刷新后重试"
SPEED_WINDOW_DAYS = 90
SPEED_LIMIT = 8


class SupplierProfileService:
    def __init__(self, engine, directory):
        self.engine, self.directory = engine, directory

    def browse(self, query, actor):
        try:
            with self.engine.connect() as connection:
                included = (
                    supplier_group_dao.supplier_ids(connection, enabled=query.status == "enabled")
                    if query.status in ("enabled", "disabled")
                    else None
                )
                excluded = supplier_group_dao.supplier_ids(connection) if query.status == "unbound" else []
                matched = (
                    supplier_group_dao.supplier_ids(connection, keyword=query.keyword)
                    if query.keyword
                    else []
                )
            found = self.directory.suppliers(
                query.account,
                query.keyword,
                query.page,
                query.pageSize,
                include_ids=included,
                exclude_ids=excluded,
                matching_ids=matched,
            )
            with self.engine.connect() as connection:
                ids = [row["id"] for row in found["items"]]
                bindings = supplier_group_dao.by_suppliers(connection, ids)
                settings = supplier_setting_dao.by_suppliers(connection, ids)
            counts = self._counts(query.account)
        except SQLAlchemyError:
            raise ApiError(503, "供应商档案读取失败，请检查业务数据库") from None
        return SupplierProfileList(
            items=[
                {
                    "supplierId": str(row["id"]),
                    "supplierName": row["name"],
                    "account": row["ns_account"],
                    "nsInternalId": row["ns_internal_id"],
                    "binding": binding(bindings[row["id"]], row) if row["id"] in bindings else None,
                    "notify": notify(settings.get(row["id"])),
                }
                for row in found["items"]
            ],
            total=found["total"],
            page=query.page,
            pageSize=query.pageSize,
            pages=max(1, (found["total"] + query.pageSize - 1) // query.pageSize),
            manage=SupplierGroupService.capability(actor),
            counts=counts,
        )

    def _counts(self, account):
        """概况计数：只数来源中有效的供应商（ID 集合交给来源门面过滤后计数）。"""
        with self.engine.connect() as connection:
            bound = supplier_group_dao.supplier_ids(connection)
            notify_off = supplier_setting_dao.disabled_ids(connection)

        def total(**scope):
            return self.directory.suppliers(account, "", 1, 1, **scope)["total"]

        return {
            "all": total(),
            "bound": total(include_ids=bound),
            "unbound": total(exclude_ids=bound),
            "notifyOff": total(include_ids=notify_off),
        }

    def invoicing_speed(self, now=None):
        """近 90 天发票收齐的任务：通知到收齐的平均天数，按供应商从慢到快取前 8 家。"""
        now = now or datetime.now(timezone.utc)
        since = (now - timedelta(days=SPEED_WINDOW_DAYS)).replace(tzinfo=None)
        try:
            with self.engine.connect() as connection:
                rows = event_dao.first_reached(connection, (NOTIFIED, *RECEIVED))
        except SQLAlchemyError:
            raise ApiError(503, "开票时效读取失败，请检查业务数据库") from None
        durations = task_durations(rows, since)
        names = self.directory.describe(supplier_ids=[i for i in durations if i is not None])["suppliers"]
        ranked = sorted(
            ((supplier_id, average(values), len(values)) for supplier_id, values in durations.items()),
            key=lambda item: item[1],
            reverse=True,
        )
        samples = [value for values in durations.values() for value in values]
        return InvoicingSpeed(
            windowDays=SPEED_WINDOW_DAYS,
            slowDays=int(SLOW_DAYS),
            average=format(average(samples), "f") if samples else None,
            taskCount=len(samples),
            suppliers=[
                SupplierSpeed(
                    supplierId=str(supplier_id or ""),
                    supplier=(names.get(supplier_id) or {}).get("name") or "供应商待确认",
                    days=format(days, "f"),
                    tasks=count,
                    slow=days > SLOW_DAYS,
                )
                for supplier_id, days, count in ranked[:SPEED_LIMIT]
            ],
        )

    def set_notify(self, body, actor):
        """人工开启或关闭供应商通知；带版本保存，只影响之后的财务审核。"""
        if not SupplierGroupService.capability(actor).allowed:
            raise ApiError(403, "服务身份只读，不能维护供应商档案")
        supplier_id = int(body.supplierId)
        if supplier_id not in self.directory.describe(supplier_ids=[supplier_id])["suppliers"]:
            raise ApiError(404, "供应商不存在")
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        try:
            with transaction(self.engine) as connection:
                current = supplier_setting_dao.get(connection, supplier_id, lock=True)
                if current is None:
                    if body.revision != 0:
                        raise ApiError(409, CONFLICT)
                    supplier_setting_dao.insert_setting(connection, supplier_id, body.enabled, actor, now)
                elif not supplier_setting_dao.update_setting(
                    connection, supplier_id, body.enabled, body.revision, actor, now
                ):
                    raise ApiError(409, CONFLICT)
                saved = supplier_setting_dao.get(connection, supplier_id)
        except IntegrityError:
            raise ApiError(409, CONFLICT) from None
        except SQLAlchemyError:
            raise ApiError(503, "供应商通知设置保存失败，请检查业务数据库") from None
        return SupplierNotify(**notify(saved).model_dump())

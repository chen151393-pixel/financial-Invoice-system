"""财务列表只读持久化快照；不读取来源明细、不计算申报幅度。"""

from datetime import UTC, datetime, timedelta, timezone

from sqlalchemy.exc import SQLAlchemyError

from backend.core.errors import ApiError

from ..dao import declaration_snapshot_dao
from ..policy.calculation_policy import FAILED_REASON, PENDING_REASON, calculation_key
from ..vo.review_vo import AutoReview, Declaration, ReviewList, SupplierOption


def month_start_utc(now):
    local = now.astimezone(timezone(timedelta(hours=8))).replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    )
    return local.astimezone(UTC).replace(tzinfo=None)


class ReviewQueryService:
    def __init__(self, engine, tolerance):
        self.engine, self.key = engine, calculation_key(tolerance)

    def browse(self, query):
        try:
            with self.engine.connect() as connection:
                # 同一快照内读取计数、页面和队列，避免后台发布恰好夹在两条查询之间。
                if connection.dialect.name == "mysql":
                    connection = connection.execution_options(isolation_level="REPEATABLE READ")
                with connection.begin():
                    counts, total, page, suppliers, jobs = declaration_snapshot_dao.browse(
                        connection, query, self.key, month_start_utc(datetime.now(UTC))
                    )
        except SQLAlchemyError:
            raise ApiError(503, "财务计算结果读取失败，请检查数据库及迁移状态") from None
        groups = []
        for row in page:
            group = Declaration.model_validate_json(row["payload"])
            group.calculatedAt = row["calculated_at"].replace(tzinfo=UTC).isoformat()
            if not row["fresh"]:
                reason = FAILED_REASON if row["last_error"] else PENDING_REASON
                group.calculationStatus = "failed" if row["last_error"] else "pending"
                group.marginAlert = False
                group.autoReview = AutoReview(eligible=False, reasons=[reason])
                group.review.allowed = False
                group.review.reason = reason
                for line in group.customsLines:
                    line.margin, line.marginStatus, line.marginNote = "", "unavailable", reason
                    line.declaredUnitPriceCny, line.originalUnitPriceCny = "", ""
            groups.append(group)
        notices = [
            f"账套 {job['ns_account']}：{FAILED_REASON if job['last_error'] else PENDING_REASON}。"
            "当前显示上次完成的单据快照和状态统计；异常及可自动审核计数暂不包含该账套。"
            for job in jobs
            if (not query.account or job["ns_account"] == query.account)
            and (job["requested_revision"] != job["completed_revision"] or job["calculation_key"] != self.key)
        ]
        counts.update(
            customs=sum(g.customsCount for g in groups),
            purchase=sum(g.purchaseCount for g in groups),
            shown=len(groups),
        )
        return ReviewList(
            groups=groups,
            counts=counts,
            notices=notices,
            accounts=[job["ns_account"] for job in jobs],
            suppliers=[SupplierOption(id=str(row["supplier_id"]), name=row["name"]) for row in suppliers],
            page=query.page,
            pageSize=query.pageSize,
            total=total,
            pages=max(1, (total + query.pageSize - 1) // query.pageSize),
        )

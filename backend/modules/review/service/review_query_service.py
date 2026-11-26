"""财务列表只读持久化快照；不读取来源明细、不计算申报幅度。"""

from datetime import UTC, datetime, timedelta, timezone

from sqlalchemy.exc import SQLAlchemyError

from backend.core.errors import ApiError
from backend.modules.identity.public import actor_names
from backend.modules.source.public import declaration_ids_created

from ..dao import declaration_snapshot_dao
from ..policy.auto_review_policy import margin_flags
from ..policy.calculation_policy import FAILED_REASON, PENDING_REASON, calculation_key
from ..vo.review_vo import AutoReview, Declaration, ReviewList, SupplierOption
from .approval_progress_reader import read_progress
from .customs_approved_reader import approved_declaration_ids


def month_start_utc(now):
    local = now.astimezone(timezone(timedelta(hours=8))).replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    )
    return local.astimezone(UTC).replace(tzinfo=None)


class ReviewQueryService:
    def __init__(self, engine, tolerance, task_reader=None):
        self.engine, self.key = engine, calculation_key(tolerance)
        self.task_reader = task_reader

    def browse(self, query):
        try:
            with self.engine.connect() as connection:
                # 同一快照内读取计数、页面和队列，避免后台发布恰好夹在两条查询之间。
                if connection.dialect.name == "mysql":
                    connection = connection.execution_options(isolation_level="REPEATABLE READ")
                with connection.begin():
                    declaration_ids = (
                        declaration_ids_created(connection, query.createdFrom, query.createdTo)
                        if query.createdFrom
                        else None
                    )
                    counts, total, page, suppliers, jobs = declaration_snapshot_dao.browse(
                        connection,
                        query,
                        self.key,
                        month_start_utc(datetime.now(UTC)),
                        declaration_ids,
                        customs_approved_ids=approved_declaration_ids(connection),
                    )
                    groups = [Declaration.model_validate_json(row["payload"]) for row in page]
                    reviewer_names = actor_names(connection, (g.review.reviewedBy for g in groups))
                    progress = read_progress(
                        connection,
                        {g.id: (g.declaration, int(g.id)) for g in groups},
                        self.task_reader,
                        finance_views={int(g.id): g.review for g in groups},
                    )
        except SQLAlchemyError:
            raise ApiError(503, "财务计算结果读取失败，请检查数据库及迁移状态") from None
        for group, row in zip(groups, page, strict=True):
            actor = group.review.reviewedBy
            group.review.reviewedByName = reviewer_names.get(actor) if actor else None
            group.approvalProgress = progress[group.id]
            group.calculatedAt = row["calculated_at"].replace(tzinfo=UTC).isoformat()
            if not row["fresh"]:
                reason = FAILED_REASON if row["last_error"] else PENDING_REASON
                group.calculationStatus = "failed" if row["last_error"] else "pending"
                group.autoReview = AutoReview(eligible=False, reasons=[reason])
                group.review.allowed = False
                group.review.reason = reason
                for line in group.customsLines:
                    line.margin, line.marginStatus, line.marginNote = "", "unavailable", reason
                    line.declaredUnitPriceCny, line.originalUnitPriceCny = "", ""
                    line.originalPrice = line.purchaseUnitPriceUsd = line.declaredUnitPriceUsd = ""
                    line.purchasePriceNote = reason
            # 兼容旧快照中混合的 marginAlert；只归类已有逐行结果，不重算金额。
            flags = margin_flags({"status": line.marginStatus} for line in group.customsLines)
            group.marginAlert = flags["marginAlert"]
            group.unitMismatch = flags["unitMismatch"]
            group.quantityMismatch = flags["quantityMismatch"]
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

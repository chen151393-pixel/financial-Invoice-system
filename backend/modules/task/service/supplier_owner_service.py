"""新增、批量更换及显式任务交接：同一账本短事务、不可变历史、预览版本复核。"""

import hashlib
import json
from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from backend.core.errors import ApiError
from backend.core.write_lock import transaction

from ..dao import supplier_owner_dao, task_dao, task_owner_dao
from ..vo.supplier_owner_vo import OwnerImpact, OwnerSaved
from . import supplier_owner_reader as reader


def writable(actor):
    if actor.startswith("service:"):
        raise ApiError(403, "服务身份只读，不能修改供应商人员关联")


def impact(connection, body):
    member, pairs = reader.validate_target(connection, body)
    today = reader.china_today()
    if body.effectiveDate.year < 1900 or body.effectiveDate.year > 9998:
        raise ApiError(400, "请选择有效的生效日期")
    tasks = []
    allowed = body.effectiveDate <= today
    for item, _ in pairs:
        existing = supplier_owner_dao.effective(connection, item.supplierId, item.companyId, today)
        if existing and existing["effective_date"] > body.effectiveDate:
            allowed = False
        for task in task_owner_dao.open_tasks(connection, item.supplierId, item.companyId):
            current = task_owner_dao.at_time(connection, task["id"], datetime.now(UTC).replace(tzinfo=None))
            tasks.append(
                {
                    "id": task["id"],
                    "status": task["status"],
                    "updatedAt": task["updated_at"].isoformat(),
                    "ownerId": current["id"] if current else None,
                }
            )
    reason = (
        "可交接选中关系下的未完成任务，已完成任务不受影响"
        if allowed
        else "未来生效或早于当前归属的变更只用于新业务；任务交接请在实际交接当日操作"
    )
    if body.transferOpenTasks and not allowed:
        raise ApiError(400, reason)
    payload = {
        "body": body.model_dump(mode="json", exclude={"previewToken"}),
        "member": member,
        "tasks": tasks,
        "today": today.isoformat(),
    }
    token = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    return member, OwnerImpact(
        pairCount=len(pairs),
        openTaskCount=len(tasks),
        transferAllowed=allowed,
        transferReason=reason,
        memberName=member["name"],
        effectiveDate=body.effectiveDate.isoformat(),
        previewToken=token,
    )


class SupplierOwnerService:
    def __init__(self, engine):
        self.engine = engine

    def _read(self, operation):
        try:
            with self.engine.connect() as connection, connection.begin():
                return operation(connection)
        except SQLAlchemyError:
            raise ApiError(503, "人员关联读取失败，请检查数据库及迁移状态") from None

    def options(self):
        return self._read(reader.options)

    def browse(self, query):
        return self._read(lambda connection: reader.browse(connection, query))

    def history(self, supplier_id, company_id):
        return self._read(lambda connection: reader.history(connection, supplier_id, company_id))

    def preview(self, body, actor):
        writable(actor)
        return self._read(lambda connection: impact(connection, body)[1])

    def save(self, body, actor):
        writable(actor)
        try:
            # 与任务生成、完结同一账本锁，预览之后任何任务状态或归属变化都会被复核。
            with transaction(self.engine) as connection:
                member, preview = impact(connection, body)
                if preview.previewToken != body.previewToken:
                    raise ApiError(409, "预览后人员或任务已变化，请重新预览再保存")
                now = datetime.now(UTC).replace(tzinfo=None)
                count = 0
                for item in sorted(body.items, key=lambda item: (item.supplierId, item.companyId)):
                    version_id = supplier_owner_dao.append(
                        connection,
                        item.supplierId,
                        item.companyId,
                        {
                            "member_id": body.memberId,
                            "member_name": member["name"],
                            "effective_date": body.effectiveDate,
                            "reason": body.reason.strip(),
                            "actor": actor,
                        },
                        now,
                    )
                    if body.transferOpenTasks:
                        owner = {"id": version_id, "member_id": body.memberId, "member_name": member["name"]}
                        for task in task_owner_dao.open_tasks(connection, item.supplierId, item.companyId):
                            task = task_dao.get(connection, task["id"], lock=True)
                            before = task_owner_dao.at_time(connection, task["id"], now)
                            task_owner_dao.append(
                                connection,
                                task["id"],
                                owner,
                                now,
                                body.reason.strip() or "人员交接",
                                actor,
                                now,
                                transfer=True,
                                previous_member_id=before["member_id"] if before else None,
                            )
                            count += 1
                return OwnerSaved(saved=len(body.items), transferredTasks=count)
        except IntegrityError:
            raise ApiError(409, "人员关联已被其他操作修改，请刷新后重新预览") from None
        except SQLAlchemyError:
            raise ApiError(503, "人员关联保存结果暂时无法确认，请刷新列表核实，勿直接重复提交") from None

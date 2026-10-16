"""供应商默认群配置；群信息从企微读取，不发送消息。"""

import time
from datetime import UTC, datetime

from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from backend.core.errors import ApiError

from . import group_dao, group_mapper, task_policy
from .group_dto import GroupFields
from .group_vo import GroupBinding, GroupList, WecomGroupList
from .task_vo import NotificationGroup, TaskCapability


class SupplierGroupService:
    def __init__(self, engine, suppliers, admin_owner, *, wecom=None):
        self.engine, self.suppliers, self.admin_owner = engine, suppliers, admin_owner
        self.wecom = wecom

    def capability(self, owner):
        allowed = owner == self.admin_owner
        return TaskCapability(
            allowed=allowed, reason="可维护供应商默认通知群" if allowed else "当前身份无群配置维护权限"
        )

    def _authorize(self, owner):
        if not self.capability(owner).allowed:
            raise ApiError(403, "当前身份无群配置维护权限")

    def _database(self):
        if self.engine is None:
            raise ApiError(503, "业务数据库未配置，无法维护供应商群映射")
        return self.engine

    def for_task(self, owner, account, supplier_key):
        try:
            with self._database().connect() as connection:
                row = group_dao.task_binding(connection, owner, account, supplier_key)
        except SQLAlchemyError:
            raise ApiError(503, "群配置读取失败，请检查 MySQL 业务库及供应商群映射表") from None
        return NotificationGroup(**group_mapper.group(row), revision=row["revision"]) if row else None

    def browse(self, owner, query):
        try:
            with self._database().connect() as connection:
                rows, total = group_dao.browse(connection, owner, query)
        except SQLAlchemyError:
            raise ApiError(503, "群配置读取失败，请检查 MySQL 业务库及供应商群映射表") from None
        result = {
            "items": [group_mapper.binding(row) for row in rows],
            "total": total,
            "page": query.page,
            "pageSize": query.pageSize,
            "pages": max(1, (total + query.pageSize - 1) // query.pageSize),
        }
        return GroupList(**result, manage=self.capability(owner))

    def supplier_options(self, owner, query):
        return self.suppliers.read(
            owner, keyword=query.keyword, account=query.account, page=query.page, page_size=query.pageSize
        )

    def _wecom(self):
        if self.wecom is None:
            raise ApiError(503, "企微群查询尚未配置，请联系管理员")
        return self.wecom

    def search_wecom(self, owner, query):
        self._authorize(owner)
        catalog = self._wecom().groups(refresh=query.refresh)
        groups = catalog["items"]
        selected = sorted(
            (group for group in groups if query.keyword.casefold() in group["groupName"].casefold()),
            key=lambda group: (group["groupName"], group["userid"], group["chatId"]),
        )
        total = len(selected)
        items = []
        for group in selected[(query.page - 1) * query.pageSize : query.page * query.pageSize]:
            items.append(
                {
                    **group,
                    "createdAt": datetime.fromtimestamp(group["createdAt"], UTC).isoformat()
                    if group["createdAt"] is not None
                    else None,
                }
            )
        return WecomGroupList(
            unavailableCount=catalog["unavailableCount"],
            items=items,
            total=total,
            page=query.page,
            pageSize=query.pageSize,
            pages=max(1, (total + query.pageSize - 1) // query.pageSize),
        )

    def save(self, owner, body):
        self._authorize(owner)
        # 供应商名称与身份以服务器可见的采购来源为准，不接受前端提交名称或派生分组键。
        suppliers = self.suppliers.read(owner, account=body.account, supplier_id=body.supplierId)["items"]
        if len(suppliers) != 1:
            raise ApiError(404, "供应商不存在、已停用或无权访问，请重新选择")
        # 允许仅停用已有映射时不依赖企微网络；不能趁停用更换群或篡改群主。
        current = None
        if not body.enabled and body.revision > 0:
            try:
                with self._database().connect() as connection:
                    current = group_dao.binding(connection, owner, body.account, body.supplierId)
            except SQLAlchemyError:
                raise ApiError(503, "群配置读取失败，请检查 MySQL 业务库") from None
        if current and current["chat_id"] == body.chatId:
            fields = GroupFields(**group_mapper.group(current))
        else:
            # 外部查询在数据库事务之外；群名和群主只取企微当前返回值。
            live = self._wecom().group(body.chatId)
            try:
                fields = GroupFields(
                    **{key: live[key] for key in ("groupName", "chatId", "employee", "userid")}
                )
            except (KeyError, ValidationError):
                raise ApiError(502, "企微群字段不符合保存要求，请核对群信息") from None
        now = int(time.time())
        values = {
            **group_mapper.fields(fields),
            "owner": owner,
            "account": body.account,
            "supplier_id": body.supplierId,
            "supplier_name": suppliers[0]["supplierName"] or body.supplierId,
            "supplier_key": task_policy.key(body.account, "supplier", body.supplierId),
            "enabled": body.enabled,
            "revision": body.revision + 1,
            "updated_at": now,
        }
        try:
            with self._database().begin() as connection:
                if not group_dao.save(connection, values, body.revision):
                    raise ApiError(409, "配置已被修改或不存在，请重新查询后编辑")
        except IntegrityError:
            raise ApiError(409, "该供应商已有配置或版本已变化，请重新查询后编辑") from None
        except SQLAlchemyError:
            raise ApiError(503, "群配置未能保存，请重新查询核实结果") from None
        return GroupBinding(**group_mapper.binding(values))

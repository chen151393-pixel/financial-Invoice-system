"""供应商默认企微群配置；群名与群主只取企微当前返回值，不发送消息。"""

from datetime import UTC, datetime, timezone

from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from backend.core.errors import ApiError

from ..dao import supplier_group_dao
from ..dto.supplier_group_dto import GroupFields
from ..mapper.supplier_group_mapper import binding
from ..policy.supplier_group_policy import match_group
from ..vo.capability import Capability
from ..vo.supplier_group_vo import GroupList, SupplierList, WecomGroupList


def _pages(total, page_size):
    return max(1, (total + page_size - 1) // page_size)


class SupplierGroupService:
    def __init__(self, engine, directory, wecom=None):
        self.engine, self.directory, self.wecom = engine, directory, wecom

    @staticmethod
    def capability(actor):
        allowed = not actor.startswith("service:")
        return Capability(
            allowed=allowed, reason="可维护供应商默认通知群" if allowed else "服务身份只读，不能维护群配置"
        )

    def _authorize(self, actor):
        if not self.capability(actor).allowed:
            raise ApiError(403, "服务身份只读，不能维护群配置")

    def browse(self, query, actor):
        found = self.directory.search(query.keyword)["supplier_ids"] if query.keyword else []
        try:
            with self.engine.connect() as connection:
                total, rows = supplier_group_dao.page(
                    connection,
                    status=query.status,
                    keyword=query.keyword,
                    supplier_ids=found,
                    offset=(query.page - 1) * query.pageSize,
                    limit=query.pageSize,
                )
        except SQLAlchemyError:
            raise ApiError(503, "群配置读取失败，请检查业务数据库及迁移状态") from None
        suppliers = self.directory.describe(supplier_ids=[row["supplier_id"] for row in rows])["suppliers"]
        return GroupList(
            items=[binding(row, suppliers.get(row["supplier_id"], {})) for row in rows],
            total=total,
            page=query.page,
            pageSize=query.pageSize,
            pages=_pages(total, query.pageSize),
            manage=self.capability(actor),
        )

    def supplier_options(self, query):
        result = self.directory.suppliers(query.account, query.keyword, query.page, query.pageSize)
        try:
            with self.engine.connect() as connection:
                bindings = supplier_group_dao.by_suppliers(connection, [row["id"] for row in result["items"]])
        except SQLAlchemyError:
            raise ApiError(503, "供应商绑定读取失败，请重新查询") from None
        return SupplierList(
            items=[
                {
                    "account": row["ns_account"],
                    "supplierId": str(row["id"]),
                    "supplierName": row["name"],
                    "binding": binding(bindings[row["id"]], row) if row["id"] in bindings else None,
                }
                for row in result["items"]
            ],
            total=result["total"],
            page=query.page,
            pageSize=query.pageSize,
            pages=_pages(result["total"], query.pageSize),
        )

    def _wecom(self):
        if self.wecom is None:
            raise ApiError(503, "企微群查询尚未配置，请联系管理员")
        return self.wecom

    def search_wecom(self, query, actor):
        self._authorize(actor)
        catalog = self._wecom().groups(refresh=query.refresh)
        selected = sorted(
            (
                group
                for group in catalog["items"]
                if query.keyword.casefold() in group["groupName"].casefold()
            ),
            key=lambda group: (group["groupName"], group["userid"], group["chatId"]),
        )
        items = [
            {
                **group,
                "createdAt": datetime.fromtimestamp(group["createdAt"], UTC).isoformat()
                if group["createdAt"] is not None
                else None,
            }
            for group in selected[(query.page - 1) * query.pageSize : query.page * query.pageSize]
        ]
        return WecomGroupList(
            unavailableCount=catalog["unavailableCount"],
            items=items,
            total=len(selected),
            page=query.page,
            pageSize=query.pageSize,
            pages=_pages(len(selected), query.pageSize),
        )

    def match_wecom(self, query, actor):
        self._authorize(actor)
        supplier_id = int(query.supplierId)
        supplier = self.directory.describe(supplier_ids=[supplier_id])["suppliers"].get(supplier_id)
        if not supplier or not supplier["active"]:
            raise ApiError(404, "供应商不存在或已停用，请重新选择")
        catalog = self._wecom().groups(refresh=query.refresh)
        ranked = []
        for group in catalog["items"]:
            match = match_group(supplier["name"], group, query.keyword)
            if match is not None:
                ranked.append((match[0], {**group, "matchReason": match[1]}))
        ranked.sort(key=lambda row: (row[0], row[1]["groupName"], row[1]["userid"], row[1]["chatId"]))
        selected = ranked[(query.page - 1) * query.pageSize : query.page * query.pageSize]
        return WecomGroupList(
            unavailableCount=catalog["unavailableCount"],
            items=[
                {
                    **group,
                    "createdAt": datetime.fromtimestamp(group["createdAt"], UTC).isoformat()
                    if group["createdAt"] is not None
                    else None,
                }
                for _, group in selected
            ],
            total=len(ranked),
            page=query.page,
            pageSize=query.pageSize,
            pages=_pages(len(ranked), query.pageSize),
        )

    def save(self, body, actor):
        self._authorize(actor)
        supplier_id = int(body.supplierId)
        supplier = self.directory.describe(supplier_ids=[supplier_id])["suppliers"].get(supplier_id)
        if not supplier or not supplier["active"]:
            raise ApiError(404, "供应商不存在或已停用，请重新选择")
        try:
            with self.engine.connect() as connection:
                current = supplier_group_dao.by_supplier(connection, supplier_id)
        except SQLAlchemyError:
            raise ApiError(503, "群配置读取失败，请检查业务数据库") from None
        if body.revision != (current["version"] if current else 0):
            raise ApiError(409, "配置已被修改或不存在，请重新查询后编辑")
        # 仅停用已有映射时不依赖企微网络；不能趁停用更换群或篡改群主。
        if current and not body.enabled and current["chat_id"] == body.chatId:
            fields = {
                "group_name": current["group_name"],
                "chat_id": current["chat_id"],
                "owner_name": current["owner_name"],
                "owner_userid": current["owner_userid"],
            }
        else:
            fields = self._live_group(body.chatId)
        values = {**fields, "enabled": body.enabled, "updated_by": actor}
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        try:
            with self.engine.begin() as connection:
                if current is None:
                    supplier_group_dao.insert_group(connection, {"supplier_id": supplier_id, **values}, now)
                elif not supplier_group_dao.update_group(
                    connection, current["id"], body.revision, values, now
                ):
                    raise ApiError(409, "配置已被修改，请重新查询后编辑")
                saved = supplier_group_dao.by_supplier(connection, supplier_id)
        except IntegrityError:
            raise ApiError(409, "该供应商已有配置，请重新查询后编辑") from None
        except SQLAlchemyError:
            raise ApiError(503, "群配置未能保存，请重新查询核实结果") from None
        return binding(saved, supplier)

    def _live_group(self, chat_id):
        # 外部查询在数据库事务之外；群名和群主只取企微当前返回值。
        live = self._wecom().group(chat_id)
        try:
            fields = GroupFields(**{key: live[key] for key in ("groupName", "chatId", "employee", "userid")})
        except (KeyError, ValidationError):
            raise ApiError(502, "企微群字段不符合保存要求，请核对群信息") from None
        return {
            "group_name": fields.groupName,
            "chat_id": fields.chatId,
            "owner_name": fields.employee,
            "owner_userid": fields.userid,
        }

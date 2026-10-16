"""已确认导入的外部群目录与后续人工关联，不调用企微发送。"""

from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from backend.core.errors import ApiError

from ..dao import external_group_dao, supplier_group_dao
from ..mapper.external_group_mapper import binding_fields, fields
from ..mapper.supplier_group_mapper import binding
from ..vo.group_import_vo import CatalogItem, CatalogPage
from .group_binding_writer import write_binding
from .group_import_preview import authorize
from .supplier_group_service import SupplierGroupService


class ExternalGroupService:
    def __init__(self, engine, directory):
        self.engine, self.directory = engine, directory

    def browse(self, query, actor):
        with self.engine.connect() as connection:
            total, rows = external_group_dao.page(connection, query)
            links = supplier_group_dao.by_chats(connection, [row["chat_id"] for row in rows])
        suppliers = self.directory.describe(supplier_ids=[r["supplier_id"] for r in links])["suppliers"]
        return CatalogPage(
            items=[
                CatalogItem(
                    **fields(row),
                    revision=row["version"],
                    filename=row["filename"],
                    updatedAt=row["updated_at"].replace(tzinfo=UTC).isoformat(),
                    suppliers=[
                        dict(
                            supplierId=str(link["supplier_id"]),
                            supplierName=suppliers.get(link["supplier_id"], {}).get("name", "供应商待确认"),
                            account=suppliers.get(link["supplier_id"], {}).get("ns_account", ""),
                            binding=binding(link, suppliers.get(link["supplier_id"], {})),
                        )
                        for link in links
                        if link["chat_id"] == row["chat_id"]
                    ],
                )
                for row in rows
            ],
            total=total,
            page=query.page,
            pageSize=query.pageSize,
            pages=max(1, (total + query.pageSize - 1) // query.pageSize),
            manage=SupplierGroupService.capability(actor),
        )

    def associate(self, body, actor):
        authorize(actor)
        supplier_id = int(body.supplierId)
        supplier = self.directory.describe(supplier_ids=[supplier_id])["suppliers"].get(supplier_id)
        if not supplier or not supplier["active"]:
            raise ApiError(404, "供应商不存在或已停用，请重新选择")
        now = datetime.now(UTC).replace(tzinfo=None)
        try:
            with self.engine.begin() as connection:
                group = external_group_dao.by_chat(connection, body.chatId, lock=True)
                if not group or group["version"] != body.catalogRevision:
                    raise ApiError(409, "外部群目录已更新，请刷新后重新核对群主")
                saved = write_binding(
                    connection,
                    supplier_id,
                    body.revision,
                    binding_fields(fields(group)),
                    actor,
                    now,
                    replace_existing=body.replaceExisting,
                )
        except IntegrityError:
            raise ApiError(409, "供应商绑定已有其他修改，请刷新后重试") from None
        except SQLAlchemyError:
            raise ApiError(503, "绑定未能保存，请刷新核实结果") from None
        return binding(saved, supplier)

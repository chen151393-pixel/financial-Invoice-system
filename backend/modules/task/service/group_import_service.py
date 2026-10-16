"""确认导入：目录与人工选择的供应商绑定同事务提交，重复确认返回原结果。"""

import json
from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from backend.core.errors import ApiError

from ..dao import external_group_dao, group_import_dao
from ..mapper.external_group_mapper import binding_fields, values
from ..vo.group_import_vo import ImportResult
from .group_binding_writer import write_binding
from .group_import_preview import authorize, owned_preview, pending


class GroupImportService:
    def __init__(self, engine, directory):
        self.engine, self.directory = engine, directory

    def confirm(self, body, actor):
        authorize(actor)
        choices = sorted((s.model_dump() for s in body.selections), key=lambda s: s["rowNo"])
        if len({s["rowNo"] for s in choices}) != len(choices):
            raise ApiError(422, "同一行不能重复选择供应商")
        if len({s["supplierId"] for s in choices}) != len(choices):
            raise ApiError(422, "一个供应商只能选择一个默认群，请调整重复关联")
        # 事务前读取门面，事务中只锁本模块目录与绑定，不持锁调用外部系统。
        suppliers = self.directory.describe(supplier_ids=[int(s["supplierId"]) for s in choices])["suppliers"]
        try:
            with self.engine.begin() as connection:
                item = owned_preview(connection, body.importId, actor, lock=True)
                if item["status"] == "confirmed":
                    stored = json.loads(item["confirmation"])
                    if stored["selections"] != choices:
                        raise ApiError(409, "该预览已确认，不能用不同关联重复提交；请在群目录维护")
                    return ImportResult(**stored["result"])
                pending(item)
                rows = json.loads(item["snapshot"])
                valid = {row["rowNo"]: row for row in rows if not row["issue"]}
                self._validate_choices(choices, valid, suppliers)
                if not valid:
                    raise ApiError(422, "没有有效群，请修正表格后重新上传")
                now = datetime.now(UTC).replace(tzinfo=None)
                self._save_catalog(connection, valid.values(), item["filename"], actor, now)
                self._save_bindings(connection, choices, valid, actor, now)
                result = ImportResult(
                    importId=body.importId,
                    imported=len(valid),
                    bound=len(choices),
                    skipped=len(rows) - len(valid),
                    message="有效外部群已导入，所选供应商绑定已保存；未关联群可继续手动维护",
                )
                group_import_dao.confirm(
                    connection,
                    body.importId,
                    json.dumps(dict(selections=choices, result=result.model_dump()), ensure_ascii=False),
                    now,
                )
                return result
        except IntegrityError:
            raise ApiError(409, "群目录或供应商绑定已被其他操作更新，请重新上传预览") from None
        except SQLAlchemyError:
            raise ApiError(503, "导入结果暂时无法确认，请用同一预览和选择重试核实") from None

    @staticmethod
    def _validate_choices(choices, valid, suppliers):
        for choice in choices:
            if choice["rowNo"] not in valid:
                raise ApiError(422, "错误行或不存在的行不能关联供应商")
            supplier = suppliers.get(int(choice["supplierId"]))
            if not supplier or not supplier["active"]:
                raise ApiError(409, "所选供应商不存在或已停用，请重新选择")

    @staticmethod
    def _save_catalog(connection, rows, filename, actor, now):
        for row in sorted(rows, key=lambda r: r["group"]["chatId"]):
            current = external_group_dao.by_chat(connection, row["group"]["chatId"], lock=True)
            if row["catalogRevision"] != (current["version"] if current else 0):
                raise ApiError(409, "外部群目录已更新，请重新上传预览后确认")
            external_group_dao.put(
                connection, current, {**values(row["group"]), "filename": filename, "updated_by": actor}, now
            )

    @staticmethod
    def _save_bindings(connection, choices, rows, actor, now):
        for choice in sorted(choices, key=lambda c: int(c["supplierId"])):
            group = rows[choice["rowNo"]]["group"]
            write_binding(
                connection,
                int(choice["supplierId"]),
                choice["revision"],
                binding_fields(group),
                actor,
                now,
                replace_existing=choice["replaceExisting"],
            )

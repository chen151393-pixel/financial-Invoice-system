"""生成服务器端匹配快照；名称候选只建议，不创建群或绑定。"""

import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from backend.core.errors import ApiError

from ..dao import external_group_dao, group_import_dao, supplier_group_dao
from ..mapper.supplier_group_mapper import binding
from ..policy.supplier_group_policy import match_group
from ..vo.group_import_vo import ImportReceipt, PreviewPage, PreviewRow
from .group_xlsx_reader import read_groups
from .supplier_group_service import SupplierGroupService


def authorize(actor):
    if not SupplierGroupService.capability(actor).allowed:
        raise ApiError(403, "服务身份只读，不能导入或关联外部群")


def owned_preview(connection, import_id, actor, *, lock=False):
    item = group_import_dao.get(connection, import_id, lock=lock)
    if not item or item["owner"] != actor:
        raise ApiError(404, "导入预览不存在或不属于当前账号")
    return item


def pending(item):
    if item["created_at"] < datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=24):
        raise ApiError(409, "预览已超过 24 小时，请重新上传以核对最新绑定")


def receipt(item, rows):
    valid = [row for row in rows if not row["issue"]]
    expired = item.get("created_at", datetime.now(UTC).replace(tzinfo=None)) < datetime.now(UTC).replace(
        tzinfo=None
    ) - timedelta(hours=24)
    reason = "确认后导入有效群并保存已选择的关联；未选择供应商的群保留待维护"
    if not valid:
        reason = "没有有效群，请修正后重新上传"
    elif item["status"] == "confirmed":
        reason = "该预览已确认，请在群目录继续维护"
    elif expired:
        reason = "预览已超过 24 小时，请重新上传"
    return ImportReceipt(
        importId=item["id"],
        filename=item["filename"],
        total=len(rows),
        valid=len(valid),
        invalid=len(rows) - len(valid),
        matched=sum(bool(r["candidates"]) for r in valid),
        unmatched=sum(not r["candidates"] for r in valid),
        status=item["status"],
        confirm=dict(
            allowed=bool(valid) and item["status"] == "pending" and not expired,
            reason=reason,
        ),
    )


class GroupImportPreview:
    def __init__(self, engine, directory):
        self.engine, self.directory = engine, directory

    def _suppliers(self, account):
        result, page = [], 1
        while True:
            found = self.directory.suppliers(account, "", page, 500)
            result.extend(found["items"])
            if len(result) >= found["total"] or not found["items"]:
                return result
            page += 1

    def create(self, body, actor):
        authorize(actor)
        rows, suppliers = read_groups(body), self._suppliers(body.account)
        with self.engine.connect() as connection:
            bindings = supplier_group_dao.by_suppliers(connection, [s["id"] for s in suppliers])
            for row in rows:
                row.update(catalogRevision=0, candidates=[], candidateCount=0)
                if row["issue"]:
                    continue
                existing = external_group_dao.by_chat(connection, row["group"]["chatId"])
                row["catalogRevision"] = existing["version"] if existing else 0
                ranked = self._candidates(row["group"], suppliers, bindings)
                row.update(candidates=ranked[:5], candidateCount=len(ranked))
        item = dict(
            id=str(uuid4()),
            owner=actor,
            filename=body.filename,
            status="pending",
            snapshot=json.dumps(rows, ensure_ascii=False),
        )
        with self.engine.begin() as connection:
            group_import_dao.create(connection, item)
        return receipt(item, rows)

    @staticmethod
    def _candidates(group, suppliers, bindings):
        ranked = []
        for supplier in suppliers:
            match = match_group(supplier["name"], group)
            if match is not None:
                ranked.append(
                    (
                        match[0],
                        dict(
                            supplierId=str(supplier["id"]),
                            supplierName=supplier["name"],
                            account=supplier["ns_account"],
                            reason=match[1],
                            binding=binding(bindings[supplier["id"]], supplier).model_dump()
                            if supplier["id"] in bindings
                            else None,
                        ),
                    )
                )
        ranked.sort(key=lambda r: (r[0], r[1]["supplierName"], r[1]["supplierId"]))
        return [row[1] for row in ranked]

    def browse(self, query, actor):
        with self.engine.connect() as connection:
            item = owned_preview(connection, query.importId, actor)
        rows = json.loads(item["snapshot"])
        info = receipt(item, rows)
        selected = rows
        start = (query.page - 1) * query.pageSize
        return PreviewPage(
            **info.model_dump(),
            suggestions=self._suggestions(rows) if item["status"] == "pending" else [],
            items=[PreviewRow(**r) for r in selected[start : start + query.pageSize]],
            page=query.page,
            pageSize=query.pageSize,
            pages=max(1, (len(selected) + query.pageSize - 1) // query.pageSize),
        )

    @staticmethod
    def _suggestions(rows):
        suggestions = []
        for row in rows:
            if row["issue"] or row["candidateCount"] != 1:
                continue
            candidate = row["candidates"][0]
            existing = candidate["binding"]
            if existing and existing["chatId"] != row["group"]["chatId"]:
                continue
            supplier = {key: value for key, value in candidate.items() if key != "reason"}
            suggestions.append(dict(rowNo=row["rowNo"], supplier=supplier, replaceExisting=False))
        # 同一供应商被多个群推荐时不预选，防止以行序决定默认群。
        counts = {}
        for item in suggestions:
            key = item["supplier"]["supplierId"]
            counts[key] = counts.get(key, 0) + 1
        return [item for item in suggestions if counts[item["supplier"]["supplierId"]] == 1]

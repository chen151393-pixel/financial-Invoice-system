"""供匹配模块读取当前身份已通过的本地财务审核证据。"""

import json

from sqlalchemy.exc import SQLAlchemyError

from backend.core.errors import ApiError

from . import dao, mapper


class ApprovedCustomsSource:
    def __init__(self, engine):
        self.engine = engine

    def read(self, owner, *, account=None, declaration_id=None):
        if self.engine is None:
            raise ApiError(503, "审核数据库未配置")
        try:
            with self.engine.connect() as connection:
                rows = dao.approved_sources(connection, owner)
        except SQLAlchemyError:
            raise ApiError(503, "审核状态读取失败，请检查应用数据库") from None
        approved = []
        for row in rows:
            if account is not None and row["account"] != account:
                continue
            if declaration_id is not None and row["declaration_id"] != declaration_id:
                continue
            try:
                payload = json.loads(row["payload"])
                content = payload["content"]
                if (
                    payload.get("source") != "database"
                    or payload.get("version") != 1
                    or content.get("head", {}).get("ns_account") != row["account"]
                    or content["head"]["ns_internal_id"] != row["declaration_id"]
                    or mapper.digest(content) != row["digest"]
                ):
                    continue
            except (KeyError, TypeError, ValueError):
                continue
            approved.append(
                {
                    "account": row["account"],
                    "declarationId": row["declaration_id"],
                    "revision": row["revision"],
                    "snapshotId": row["snapshot_id"],
                    "digest": row["digest"],
                    "content": content,
                }
            )
        return approved

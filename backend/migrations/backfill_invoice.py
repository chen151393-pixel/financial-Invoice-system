"""0008 回填：既有票头与明细生成不可变基线版本，不修改确认历史。"""

import hashlib
import json

from sqlalchemy import MetaData, Table, select, update


def backfill(connection):
    meta = MetaData()
    headers = Table("invoice_headers", meta, autoload_with=connection)
    items = Table("invoice_items", meta, autoload_with=connection)
    versions = Table("invoice_versions", meta, autoload_with=connection)
    for head in connection.execute(select(headers).order_by(headers.c.id)).mappings():
        rows = [
            dict(r)
            for r in connection.execute(
                select(items).where(items.c.invoice_id == head["id"]).order_by(items.c.id)
            ).mappings()
        ]
        header = {
            k: v
            for k, v in head.items()
            if k not in ("current_version_id", "created_at", "updated_at", "imported_at")
        }

        def safe(value):
            return json.loads(json.dumps(value, ensure_ascii=False, default=str))

        digest = hashlib.sha256(json.dumps(safe([header, rows]), sort_keys=True).encode()).hexdigest()
        version = connection.execute(
            versions.insert().values(
                invoice_id=head["id"],
                revision=1,
                content_sha256=digest,
                raw_record_id=head["raw_record_id"],
                source=head["source"],
                external_id=head["invoice_key"],
                currency_source="source_rule" if head["source"] == "lemon_excel" else "unresolved",
                source_rule_version="lemon_cny_v1" if head["source"] == "lemon_excel" else None,
                header_snapshot=safe(header),
                items_snapshot=safe(rows),
                created_at=head["created_at"],
                updated_at=head["updated_at"],
            )
        ).inserted_primary_key[0]
        connection.execute(
            update(headers)
            .where(headers.c.id == head["id"])
            .values(current_version_id=version, detail_status="complete" if rows else "pending")
        )

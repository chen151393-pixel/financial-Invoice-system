"""0006 的冻结回填：只复制旧审核快照，不把当前来源冒充历史证据。"""

import hashlib
import json
from collections import defaultdict

from sqlalchemy import MetaData, Table, select, update


def backfill(connection):
    meta = MetaData()
    lines = Table("review_lines", meta, autoload_with=connection)
    records = Table("review_records", meta, autoload_with=connection)
    bases = Table("review_purchase_bases", meta, autoload_with=connection)
    heads = {r["id"]: r for r in connection.execute(select(records)).mappings()}
    revisions, previous = defaultdict(int), {}
    for row in connection.execute(select(lines).order_by(lines.c.id)).mappings():
        head = heads[row["review_id"]]
        line_id = row["purchase_line_id"]
        revisions[line_id] += 1
        if line_id in previous:
            connection.execute(
                update(bases).where(bases.c.id == previous[line_id]).values(status="superseded")
            )
        values = {
            k: row[k]
            for k in (
                "purchase_order_id",
                "purchase_line_id",
                "supplier_id",
                "company_id",
                "currency",
                "quantity",
                "unit",
                "amount",
            )
        }
        digest = hashlib.sha256(json.dumps(values, sort_keys=True, default=str).encode()).hexdigest()
        values.update(
            ns_account=head["ns_account"],
            revision=revisions[line_id],
            status="review_required",
            currency_source="unresolved",
            source_sha256=row["line_sha256"],
            basis_sha256=digest,
            source_refs={
                "legacy_review_line_id": row["id"],
                "issue": "历史快照缺少完整来源版本引用，需重新审核",
            },
            origin_review_id=head["id"],
            approved_by=head["approved_by"],
            approved_at=head["approved_at"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
        basis_id = connection.execute(bases.insert().values(**values)).inserted_primary_key[0]
        previous[line_id] = basis_id
        connection.execute(update(lines).where(lines.c.id == row["id"]).values(purchase_basis_id=basis_id))

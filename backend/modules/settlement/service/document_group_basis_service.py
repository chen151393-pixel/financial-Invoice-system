"""来源更正后显式确认更新组依据；事务内复核预览，保留原提单和合同。"""

import hashlib
import json
from datetime import UTC, datetime

from backend.core import write_lock
from backend.core.errors import ApiError

from ..dao import document_group_dao as dao
from ..policy.amount_policy import money
from ..policy.document_group_basis_policy import update_reason
from ..vo.batch_vo import Action
from ..vo.document_group_vo import GroupBasisPreview


class DocumentGroupBasisService:
    def __init__(self, groups):
        self.groups = groups

    def _preview(self, connection, group_id):
        context, rows = self.groups.source.load(connection, group_id, lock=True)
        group = dao.get(connection, group_id)
        reason = update_reason(rows) or ("当前来源一致，无需更新" if not context["document_issue"] else "")
        current = rows[0] if rows else {}
        signature = dict(group=group, members=rows)
        token = hashlib.sha256(
            json.dumps(signature, ensure_ascii=False, sort_keys=True, default=str).encode()
        ).hexdigest()
        preview = GroupBasisPreview(
            groupId=group_id,
            oldConsignee=group["consignee"],
            oldCurrency=group["currency"],
            newConsignee=current.get("consignee", ""),
            newCurrency=current.get("currency", ""),
            declarationCount=len(rows),
            amount=str(money(sum((row["amount"] for row in rows), start=0)))
            if not update_reason(rows)
            else "",
            token=token,
            update=Action(allowed=not reason, reason=reason),
        )
        return preview, group, rows

    def preview(self, group_id):
        self.groups._require_engine()
        with self.groups.engine.connect() as connection:
            return self._preview(connection, group_id)[0]

    def confirm(self, group_id, body, owner):
        self.groups._require_engine()
        if owner.startswith("service:"):
            raise ApiError(403, "服务身份只读，不能更新资料组来源")
        with write_lock.transaction(self.groups.engine, "settlement") as connection:
            preview, group, rows = self._preview(connection, group_id)
            if not preview.update.allowed:
                raise ApiError(409, preview.update.reason)
            if preview.token != body.token:
                raise ApiError(409, "预览后来源或归属已变化，请重新核对")
            now = datetime.now(UTC).replace(tzinfo=None)
            history = [
                *(group["basis_history"] or []),
                dict(
                    before=dict(consignee=group["consignee"], currency=group["currency"]),
                    after=dict(consignee=preview.newConsignee, currency=preview.newCurrency),
                    declarations=[
                        dict(
                            number=row["declaration_no"],
                            receiptId=row["receipt_id"],
                            revision=row["revision"],
                        )
                        for row in rows
                    ],
                    operator=owner,
                    at=now.isoformat(),
                ),
            ]
            dao.update_basis(connection, group_id, preview.newConsignee, preview.newCurrency, history, now)
            return self.groups._view(connection, dao.get(connection, group_id))

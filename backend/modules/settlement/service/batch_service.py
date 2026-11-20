"""结汇批次用例：建批次、确认资料已出、登记汇回 / 确认结汇、作废、列表与详情。

写入只涉及 settlement 自己的表，使用模块写锁；海关回执金额经 review 门面在同一连接内只读获取，
建批次时冻结到明细，之后回执换版不改变已建批次的金额。

2026-11-18 起只有香港中转建批次；直接收汇改记直接收汇明细（总账），不再新建直接收汇批次。
settle()（直接收汇确认结汇）仅为此前已建的直接收汇批次保留，调用方是批次详情的“确认结汇”；
确认库中没有未完结的直接收汇批次后，连同 batch_state_policy 中的 DIRECT 状态转换一并删除。
"""

import math
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from backend.core import write_lock
from backend.core.errors import ApiError

from ..dao import batch_dao, batch_item_dao, hk_slip_dao
from ..mapper.batch_mapper import balances, detail, summary
from ..policy.amount_policy import balance_check
from ..policy.batch_selection_policy import validate_selection
from ..policy.batch_state_policy import STATUS_LABELS, can_transition, status_label
from ..policy.route_policy import HK_TRANSIT, ROUTE_LABELS
from ..vo.batch_vo import BatchList, StatusCount

OPEN_STATUSES = ("collected", "documents_ready")


def _now():
    return datetime.now(UTC).replace(tzinfo=None)


def _require_operator(owner):
    if owner.startswith("service:"):
        raise ApiError(403, "服务身份只读，不能修改结汇批次")


class BatchService:
    def __init__(self, engine, candidates, documents, *, fee_alert=Decimal("50")):
        self.engine = engine
        self.candidates = candidates
        # 资料齐全度读取器：香港中转确认资料已出前校验提单与销售合同
        self.documents = documents
        self.fee_alert = fee_alert

    def _require_engine(self):
        if self.engine is None:
            raise ApiError(503, "业务数据库未配置")

    # ---- 查询 ----

    def browse(self, body):
        self._require_engine()
        filters = {
            "route": None if body.route == "all" else body.route,
            "statuses": {"all": None, "open": OPEN_STATUSES}.get(body.status, (body.status,)),
            "consignee": body.consignee,
            "batch_no": body.batchNo,
            "received_from": body.receivedFrom,
            "received_to": body.receivedTo,
        }
        with self.engine.connect() as connection:
            if body.declarationNo:
                filters["ids"] = batch_item_dao.batch_ids_by_declaration(connection, body.declarationNo)
            total, rows = batch_dao.page(connection, filters, (body.page - 1) * body.pageSize, body.pageSize)
            if rows == [] and total and body.page > 1:
                last = math.ceil(total / body.pageSize)
                total, rows = batch_dao.page(connection, filters, (last - 1) * body.pageSize, body.pageSize)
            items = batch_item_dao.of_batches(connection, [row["id"] for row in rows])
            counts = batch_dao.status_counts(connection, filters)
        return BatchList(
            items=[summary(row, len(items.get(row["id"], [])), self.fee_alert) for row in rows],
            total=total,
            page=body.page,
            pageSize=body.pageSize,
            counts=[
                StatusCount(route=route, status=status, label=status_label(route, status), count=count)
                for (route, status), count in sorted(counts.items())
            ],
        )

    def get(self, batch_id):
        self._require_engine()
        with self.engine.connect() as connection:
            batch = batch_dao.get(connection, batch_id)
            if batch is None:
                raise ApiError(404, "结汇批次不存在")
            return self._detail(connection, batch_id)

    # ---- 写入 ----

    def create(self, body, owner, *, require_balance=False, slip=None):
        """一笔回款建一个批次：报关单须为香港中转、同一境外收货人、同一币种，且未在其他有效批次中。"""
        _require_operator(owner)
        self._require_engine()
        request_id = str(body.requestId)
        now = _now()
        try:
            with write_lock.transaction(self.engine, "settlement") as connection:
                existing = batch_dao.by_request(connection, request_id)
                if existing:
                    return self._detail(connection, existing["id"])
                numbers = list(body.declarationNos)
                batch_item_dao.active_by_numbers(connection, numbers, lock=True)
                rows = self.candidates.load(connection, numbers=numbers)
                route, consignee, currency, total = validate_selection(rows, numbers)
                if (
                    require_balance
                    and not balance_check(total, body.receivedAmount, body.receivedFee, self.fee_alert)[
                        "balanced"
                    ]
                ):
                    raise ApiError(422, "到账金额加手续费须与已选报关合计对平，请核对后再登记")
                batch_id = batch_dao.insert_batch(
                    connection,
                    {
                        "request_id": request_id,
                        "route": route,
                        "status": "collected",
                        "consignee": consignee,
                        "currency": currency,
                        "declared_total": total,
                        "payer": body.payer or None,
                        "receiving_account": body.receivingAccount or None,
                        "received_on": body.receivedOn,
                        "received_amount": body.receivedAmount,
                        "received_fee": body.receivedFee,
                        "received_reference": body.receivedReference or None,
                        "note": body.note or None,
                        "created_by": owner,
                    },
                    now,
                )
                batch_dao.update_batch(
                    connection, batch_id, {"batch_no": f"HK{now:%Y%m%d}-{batch_id:05d}"}, now
                )
                if slip:
                    hk_slip_dao.save(connection, batch_id, slip, owner, now)
                found = {row["declaration_no"]: row for row in rows}
                batch_item_dao.insert_items(
                    connection,
                    batch_id,
                    [
                        {
                            "declaration_no": number,
                            "record_no": found[number]["record_no"] or None,
                            "receipt_id": found[number]["receipt_id"],
                            "receipt_revision": found[number]["revision"],
                            "sales_orders": "、".join(found[number]["sales_orders"]) or None,
                            "consignee": found[number]["consignee"],
                            "export_date": found[number]["export_date"],
                            "currency": found[number]["currency"],
                            "declared_amount": found[number]["amount"],
                        }
                        for number in numbers
                    ],
                    now,
                )
                return self._detail(connection, batch_id)
        except IntegrityError:
            raise ApiError(409, "所选报关单已被其他结汇批次占用，请刷新后重试") from None
        except SQLAlchemyError:
            raise ApiError(503, "结汇批次保存失败，请检查业务数据库及迁移状态") from None

    def documents_ready(self, batch_id, owner):
        """香港中转：到账对平、提单与销售合同齐全后确认资料包已出。"""
        return self._transition(batch_id, owner, "documents_ready", "documentsReady", {})

    def settle(self, batch_id, owner):
        """直接收汇：到账加手续费与报关合计对平后确认已结汇（NS 已核销）。"""
        return self._transition(batch_id, owner, "settled", "settle", {}, route="direct")

    def remit(self, batch_id, body, owner):
        """香港中转：登记香港汇回境内到账；汇回加手续费与报关合计对平才确认已结汇。"""
        values = {
            "remitted_on": body.remittedOn,
            "remitted_amount": body.remittedAmount,
            "remitted_fee": body.remittedFee,
            "remitted_reference": body.remittedReference or None,
        }
        return self._transition(batch_id, owner, "settled", "settle", values, route=HK_TRANSIT)

    def cancel(self, batch_id, body, owner):
        values = {"cancel_reason": body.reason}
        return self._transition(batch_id, owner, "cancelled", "cancel", values)

    def _transition(self, batch_id, owner, target, action, values, *, route=None):
        _require_operator(owner)
        self._require_engine()
        now = _now()
        with write_lock.transaction(self.engine, "settlement") as connection:
            batch = batch_dao.get(connection, batch_id, lock=True)
            if batch is None:
                raise ApiError(404, "结汇批次不存在")
            if route and batch["route"] != route:
                raise ApiError(409, f"该批次为{ROUTE_LABELS[batch['route']]}，不能执行此操作")
            candidate = {**batch, **values}
            if target == "settled" and batch["route"] == HK_TRANSIT and batch["status"] == "documents_ready":
                # 先给出具体差额，再走通用可操作判断
                remitted = [b for b in balances(candidate, self.fee_alert)[0] if b.stage == "remitted"]
                if not remitted or not remitted[0].balanced:
                    note = remitted[0].warnings if remitted else ["未登记汇回金额"]
                    raise ApiError(409, "汇回金额加手续费与报关合计不一致：" + "；".join(note))
            check = getattr(summary(candidate, 0, self.fee_alert).actions, action)
            if not check.allowed:
                raise ApiError(409, check.reason)
            if target == "documents_ready":
                items = batch_item_dao.of_batches(connection, [batch_id])[batch_id]
                reason = self.documents.blocking_reason(connection, batch, items)
                if reason:
                    raise ApiError(409, reason)
            if not can_transition(batch["route"], batch["status"], target):
                raise ApiError(
                    409,
                    f"当前状态为{status_label(batch['route'], batch['status'])}，不能变更为{STATUS_LABELS[target]}",
                )
            stamps = {
                "documents_ready": {"documents_ready_by": owner, "documents_ready_at": now},
                "settled": {"settled_by": owner, "settled_at": now},
                "cancelled": {"cancelled_by": owner, "cancelled_at": now},
            }[target]
            batch_dao.update_batch(connection, batch_id, {**values, **stamps, "status": target}, now)
            if target == "cancelled":
                batch_item_dao.release(connection, batch_id, now)
            return self._detail(connection, batch_id)

    def _detail(self, connection, batch_id):
        batch = batch_dao.get(connection, batch_id)
        items = batch_item_dao.of_batches(connection, [batch_id])[batch_id]
        issue = ""
        if batch["status"] == "collected":
            issue = self.documents.blocking_reason(connection, batch, items)
        view = detail(batch, items, self.fee_alert, issue)
        slip = hk_slip_dao.get(connection, batch_id)
        if slip:
            view.receivedSlipName = slip["file_name"]
            view.receivedSlipUrl = f"/api/settlement/batches/{batch_id}/bank-slip/file"
        return view

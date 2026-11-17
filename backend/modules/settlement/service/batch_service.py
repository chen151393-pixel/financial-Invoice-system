"""结汇批次用例：建批次、确认资料已出、登记汇回 / 确认结汇、作废、列表与详情。

写入只涉及 settlement 自己的表，使用模块写锁；海关回执金额经 review 门面在同一连接内只读获取，
建批次时冻结到明细，之后回执换版不改变已建批次的金额。
"""

import math
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from backend.core import write_lock
from backend.core.errors import ApiError
from backend.core.names import normalize_name

from ..dao import batch_dao, batch_item_dao
from ..mapper.batch_mapper import balances, detail, summary
from ..policy.batch_state_policy import STATUS_LABELS, can_transition, status_label
from ..policy.route_policy import HK_TRANSIT, ROUTE_LABELS
from ..vo.batch_vo import BatchList, StatusCount

OPEN_STATUSES = ("collected", "documents_ready")


def _now():
    return datetime.now(UTC).replace(tzinfo=None)


def _require_operator(owner):
    if owner.startswith("service:"):
        raise ApiError(403, "服务身份只读，不能修改结汇批次")


def _single(values, label):
    distinct = {value for value in values}
    if len(distinct) != 1:
        raise ApiError(422, f"批次内报关单的{label}必须一致，当前有：{'、'.join(sorted(distinct))}")
    return distinct.pop()


def validate_selection(rows, numbers):
    """建批次前的业务校验；返回 (路径, 境外收货人, 币种, 报关合计)。"""
    found = {row["declaration_no"]: row for row in rows}
    missing = [number for number in numbers if number not in found]
    if missing:
        raise ApiError(422, f"以下报关单没有可用的海关回执：{'、'.join(missing)}")
    blocked = [f"{number}（{found[number]['blocked']}）" for number in numbers if found[number]["blocked"]]
    if blocked:
        raise ApiError(409, "以下报关单不能结汇：" + "；".join(blocked))
    chosen = [found[number] for number in numbers]
    route = _single((row["route"] for row in chosen), "回款路径")
    _single((normalize_name(row["consignee"]) for row in chosen), "境外收货人")
    currency = _single((row["currency"] for row in chosen), "币种")
    total = sum((row["amount"] for row in chosen), Decimal(0))
    return route, chosen[0]["consignee"], currency, total


class BatchService:
    def __init__(self, engine, candidates, *, fee_alert=Decimal("50")):
        self.engine = engine
        self.candidates = candidates
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
            items = batch_item_dao.of_batches(connection, [batch_id])[batch_id]
        return detail(batch, items, self.fee_alert)

    # ---- 写入 ----

    def create(self, body, owner):
        """一笔回款建一个批次：报关单须同一路径、同一境外收货人、同一币种，且未在其他有效批次中。"""
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
                    connection, batch_id, {"batch_no": f"SB{now:%Y%m%d}-{batch_id:05d}"}, now
                )
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
        """香港中转：到账对平后确认资料包已出（报关单、提单、销售合同、形式发票已提交银行）。"""
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
        return detail(batch, items, self.fee_alert)

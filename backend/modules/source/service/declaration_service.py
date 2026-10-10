"""报关单完整内容的读取：报关单、明细、有效关联、关联子采购单及明细。

内容摘要与对外读取（review 模块经 public 使用）都基于这里组装的同一份数据。
"""

import hashlib
from contextlib import contextmanager

from sqlalchemy.exc import SQLAlchemyError

from backend.core.errors import ApiError

from ..dao import (
    customs_declaration_dao,
    customs_purchase_link_dao,
    lock_dao,
    purchase_order_dao,
    raw_record_dao,
)
from ..policy.content_digest import content_digest

EVIDENCE_TYPE = "relation_evidence"


def sync_lock_name(engine, account):
    """同步保存与审核确认共用的账户锁名称。"""
    return hashlib.sha256(f"source-sync:{engine.url.database}:{account}".encode()).hexdigest()


def snapshot(connection, declaration_id):
    """返回报关单完整内容；不存在时返回 None。"""
    head = customs_declaration_dao.head(connection, declaration_id)
    if head is None:
        return None
    links = customs_purchase_link_dao.active(connection, declaration_id)
    order_ids = sorted({link["purchase_order_id"] for link in links})
    evidence = raw_record_dao.latest(connection, head["ns_account"], EVIDENCE_TYPE, head["ns_internal_id"])
    return {
        "declaration": head,
        "customs_lines": customs_declaration_dao.lines(connection, declaration_id),
        "links": links,
        "orders": purchase_order_dao.orders(connection, order_ids),
        "purchase_lines": purchase_order_dao.lines(connection, order_ids),
        "evidence": evidence,
    }


def digest(content):
    return content_digest(
        content["declaration"],
        content["customs_lines"],
        content["orders"],
        content["purchase_lines"],
        content["links"],
    )


def comparison(content):
    """NS v3 整单关联（同步时已校验）；没有时返回 None。"""
    evidence = content.get("evidence") or {}
    return (evidence.get("comparison") or {}).get("payload")


class DeclarationService:
    def __init__(self, engine):
        self.engine = engine

    def _require_engine(self):
        if self.engine is None:
            raise ApiError(503, "业务数据库未配置")

    def page(self, account, keyword, page, page_size):
        self._require_engine()
        try:
            with self.engine.connect() as connection:
                total, rows = customs_declaration_dao.page(
                    connection, account, keyword, (page - 1) * page_size, page_size
                )
        except SQLAlchemyError:
            raise ApiError(503, "报关单读取失败，请检查业务数据库及迁移状态") from None
        return total, rows

    def detail(self, declaration_id):
        self._require_engine()
        try:
            with self.engine.connect() as connection:
                content = snapshot(connection, declaration_id)
        except SQLAlchemyError:
            raise ApiError(503, "报关单读取失败，请检查业务数据库及迁移状态") from None
        if content is None:
            raise ApiError(404, "报关单不存在")
        return content

    @contextmanager
    def locked(self, account):
        """持有同步账户锁并开启事务：审核确认期间来源不会被同步替换。

        产出的 connection 供调用方在同一事务中读取来源（snapshot）并写入自己的表。
        """
        self._require_engine()
        name = sync_lock_name(self.engine, account)
        with self.engine.connect() as connection:
            with connection.begin():
                acquired = lock_dao.acquire(connection, name)
            if not acquired:
                raise ApiError(409, "此账套正在同步，请稍后重试")
            try:
                with connection.begin():
                    yield connection
            finally:
                try:
                    if connection.in_transaction():
                        connection.rollback()
                    with connection.begin():
                        lock_dao.release(connection, name)
                except SQLAlchemyError:
                    connection.invalidate()

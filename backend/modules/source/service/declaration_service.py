"""报关单完整内容的读取：报关单、明细、有效关联、关联子采购单及明细。

内容摘要与对外读取（review 模块经 public 使用）都基于这里组装的同一份数据。
"""

import hashlib
from collections import defaultdict
from contextlib import contextmanager

from sqlalchemy.exc import SQLAlchemyError

from backend.core import write_lock
from backend.core.errors import ApiError

from ..dao import (
    customs_declaration_dao,
    customs_purchase_link_dao,
    purchase_order_dao,
    raw_record_dao,
    sales_order_dao,
)
from ..mapper.customs_display_mapper import customs_display_lines
from ..mapper.parent_purchase_unit_mapper import parent_purchase_units
from ..policy.content_digest import content_digest

EVIDENCE_TYPE = "relation_evidence"


def sync_lock_name(engine, account):
    """同步保存与审核确认共用的账户锁名称。"""
    return hashlib.sha256(f"source-sync:{engine.url.database}:{account}".encode()).hexdigest()


def snapshot(connection, declaration_id):
    """返回报关单完整内容；不存在时返回 None。"""
    return snapshots(connection, [declaration_id]).get(declaration_id)


def snapshots(connection, declaration_ids):
    """同一连接批量读取完整来源，不跨请求缓存，也不省略失效头关联的有效行。"""
    heads = customs_declaration_dao.heads(connection, declaration_ids)
    if not heads:
        return {}
    links, customs = defaultdict(list), defaultdict(list)
    for link in customs_purchase_link_dao.active_by_declarations(connection, list(heads)):
        links[link["customs_declaration_id"]].append(link)
    for line in customs_declaration_dao.lines_by_declarations(connection, list(heads)):
        customs[line["customs_declaration_id"]].append(line)
    order_ids = sorted({link["purchase_order_id"] for group in links.values() for link in group})
    orders = purchase_order_dao.orders(connection, order_ids)
    purchase_lines = purchase_order_dao.lines(connection, order_ids)
    sales = sales_order_dao.by_ids(
        connection, [order["sales_order_id"] for order in orders if order["sales_order_id"]]
    )
    evidence = raw_record_dao.latest_by_keys(
        connection, EVIDENCE_TYPE, [(head["ns_account"], head["ns_internal_id"]) for head in heads.values()]
    )
    result = {}
    for identity, head in heads.items():
        linked_ids = {link["purchase_order_id"] for link in links[identity]}
        linked_orders = [order for order in orders if order["id"] in linked_ids]
        result[identity] = _snapshot(
            head,
            customs[identity],
            links[identity],
            linked_orders,
            [line for line in purchase_lines if line["purchase_order_id"] in linked_ids],
            {
                order["sales_order_id"]: sales[order["sales_order_id"]]
                for order in linked_orders
                if order["sales_order_id"] in sales
            },
            evidence.get((head["ns_account"], head["ns_internal_id"])),
        )
    return result


def _snapshot(head, customs, links, orders, purchase_lines, sales, evidence):
    return {
        "declaration": head,
        "customs_lines": customs_display_lines(head, customs),
        "links": links,
        "orders": orders,
        # 销售单头（币种、汇率）只用于申报幅度，不参与内容摘要
        "sales_orders": sales,
        "purchase_lines": parent_purchase_units(orders, purchase_lines, evidence),
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

    def index(self, account, keyword, supplier_id=None):
        self._require_engine()
        try:
            with self.engine.connect() as connection:
                return customs_declaration_dao.index(connection, account, keyword, supplier_id)
        except SQLAlchemyError:
            raise ApiError(503, "报关单读取失败，请检查业务数据库及迁移状态") from None

    def suppliers(self, account):
        """有效报关单关联到的供应商：[{id, name}]，供财务核对按供应商筛选。"""
        self._require_engine()
        try:
            with self.engine.connect() as connection:
                return customs_declaration_dao.suppliers_of(connection, account)
        except SQLAlchemyError:
            raise ApiError(503, "供应商读取失败，请检查业务数据库及迁移状态") from None

    def accounts(self):
        self._require_engine()
        try:
            with self.engine.connect() as connection:
                return customs_declaration_dao.accounts(connection)
        except SQLAlchemyError:
            raise ApiError(503, "报关单读取失败，请检查业务数据库及迁移状态") from None

    def details(self, declaration_ids):
        """按给定顺序返回多张报关单的完整内容（同一连接读取）。"""
        self._require_engine()
        try:
            with self.engine.connect() as connection:
                contents = snapshots(connection, declaration_ids)
                return [contents.get(declaration_id) for declaration_id in declaration_ids]
        except SQLAlchemyError:
            raise ApiError(503, "报关单读取失败，请检查业务数据库及迁移状态") from None

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
        with (
            write_lock.locked(self.engine, sync_lock_name(self.engine, account)) as connection,
            connection.begin(),
        ):
            yield connection

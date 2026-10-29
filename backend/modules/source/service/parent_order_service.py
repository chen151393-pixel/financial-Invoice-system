"""母采购单头保存：复用来源事务与主数据，保留 NS 供应商引用和原始快照。"""

from backend.core.errors import ApiError

from ..dao import parent_order_dao, raw_record_dao, supplier_dao
from ..mapper.storage_mapper import map_parent, map_parent_supplier


def save_header(connection, account, parent_ns_id, header, currency, now):
    """调用方持有来源账户锁与账本写锁；不自行提交，也不调用 NS。"""
    party = map_parent_supplier(header)
    supplier_id = None
    if party:
        supplier_id = supplier_dao.reference_id(connection, account, party["ns_internal_id"])
        if supplier_id is None:
            if not party["name"]:
                raise ApiError(422, "母采购供应商尚无本地档案且来源未提供名称，未保存")
            supplier_id = supplier_dao.upsert(connection, account, party, now)
    raw_id = raw_record_dao.save(connection, account, "purchaseOrder", parent_ns_id, header, now)
    parent_id = parent_order_dao.upsert(
        connection,
        account,
        parent_ns_id,
        {
            **map_parent(header, currency),
            "supplier_id": supplier_id,
            "raw_record_id": raw_id,
            "currency_internal_id": str(header.get("currency") or "") or None,
        },
        now,
    )
    return parent_id, raw_id

"""结汇客户登记与存量名称初始化；原始回执和银行流水不改写。"""

from datetime import UTC, datetime

from backend.modules.review.public import settlement_consignee_names

from ..dao import bank_receipt_dao, batch_dao, consignee_dao
from ..policy.consignee_policy import consignee_key


def register(connection, names, now):
    """同一事务中只新增不存在的名称；按键排序，避免多客户并发写入时锁顺序相反。"""
    unique = {}
    for name in names:
        if key := consignee_key(name):
            unique.setdefault(key, name)
    consignee_dao.add_missing(
        connection,
        [
            dict(name_key=key, display_name=unique[key], created_at=now, updated_at=now)
            for key in sorted(unique)
        ],
    )


def on_customs_receipts_saved(connection, event):
    register(connection, event.consignees, event.saved_at)


def initialize(engine):
    """启动工作线程前兼容存量数据；每次幂等补缺，已有名称不覆盖。"""
    with engine.connect() as connection:
        records = settlement_consignee_names(connection)
        records.extend(bank_receipt_dao.consignee_history(connection))
        records.extend(batch_dao.consignee_history(connection))
    records.sort(key=lambda row: (str(row[0]), row[1], row[2]))
    with engine.begin() as connection:
        register(connection, (row[3] for row in records), datetime.now(UTC).replace(tzinfo=None))

"""合成 Excel 缺少购买方；补齐测试票面后重新生成真实 100% 整单建议。"""

from backend.core.names import normalize_name
from backend.tests.test_task import USER
from sqlalchemy import text


def complete_buyer(engine, world, invoice_id):
    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE invoice_headers SET buyer_name=:name, buyer_name_normalized=:normalized WHERE id=:id"
            ),
            {"name": "采购公司A", "normalized": normalize_name("采购公司A"), "id": invoice_id},
        )
    world["proposals"].generate_now([invoice_id], USER)

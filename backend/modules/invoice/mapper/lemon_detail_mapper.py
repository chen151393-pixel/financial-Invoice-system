"""已校验商品行转换：不以来源显示序号冒充稳定行身份。"""

from collections import Counter

from backend.core.names import normalize_name

from ..entity import items
from .import_mapper import checked, payload_digest


def item_values(rows, number):
    result, seen = [], Counter()
    for index, row in enumerate(rows, 1):
        # 沿用版本管理的品名、规格、单位身份；同身份多行换版时交由现有歧义保护处理。
        identity = payload_digest({key: row[key] for key in ("item_name", "specification", "unit")})
        seen[identity] += 1
        values = {
            **row,
            "source_line_key": f"lemon:{identity}:{seen[identity]}",
            "line_no": str(index),
            "item_name_normalized": normalize_name(row["item_name"])[:500] or None,
        }
        result.append(checked(items, values, number))
    return result

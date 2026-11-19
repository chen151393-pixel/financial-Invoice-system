"""银行收款抬头汇总：三个指定主体分别展示，不将账套编号当作收款抬头。

只合并规范化后全称一致的抬头，不按相似名称猜测归属；其他抬头保留汇总并单独展示。
"""

from decimal import Decimal

from backend.core.names import normalize_name

RECEIVING_COMPANIES = (
    "上海绎色数码科技有限公司",
    "上海绎视数码科技有限公司",
    "上海毅鑫实业有限公司",
)
_NAMES = {normalize_name(name): name for name in RECEIVING_COMPANIES}


def company_totals(rows):
    currencies = sorted({row["currency"] for row in rows}) or ["USD"]
    groups = {}

    def group(name, currency):
        key = (normalize_name(name), currency)
        return groups.setdefault(
            key,
            {
                "receiving_company": _NAMES.get(key[0], name),
                "currency": currency,
                "featured_company": key[0] in _NAMES,
                "count": 0,
                "amount": Decimal(0),
                "third_party_count": 0,
                "third_party_amount": Decimal(0),
            },
        )

    for currency in currencies:
        for name in RECEIVING_COMPANIES:
            group(name, currency)
    for row in rows:
        target = group(row["receiving_company"], row["currency"])
        for field in ("count", "amount", "third_party_count", "third_party_amount"):
            target[field] += row[field] or 0
    return list(groups.values())

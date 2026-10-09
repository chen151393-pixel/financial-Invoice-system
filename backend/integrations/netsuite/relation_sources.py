"""同步关联依据的固定只读查询；没有接收浏览器 SQL 或任意 URL 的入口。"""

import json
import re
from decimal import Decimal

import httpx

from backend.core.errors import ApiError

QUERIES = {
    "packing_by_customs": (
        "SELECT * FROM customrecord_swc_packinglist WHERE custrecord_swc_declare_record IN ({ids}) ORDER BY id"
    ),
    "packing_by_id": "SELECT * FROM customrecord_swc_packinglist WHERE id IN ({ids}) ORDER BY id",
    "purchase_links": (
        "SELECT previousdoc,previousline,nextdoc,nextline,linktype,previoustype,nexttype "
        "FROM NextTransactionLineLink WHERE previousdoc IN ({ids}) "
        "AND nexttype = 'PurchOrd' AND previoustype = 'SalesOrd' "
        "ORDER BY previousdoc,previousline,nextdoc,nextline,linktype"
    ),
    "parent_lines": (
        "SELECT transaction,id,uniquekey,item,quantity,units,foreignamount,mainline,taxline "
        "FROM transactionline WHERE transaction IN ({ids}) ORDER BY transaction,id"
    ),
}


def read_relation_rows(ns, kind, ids):
    if (
        kind not in QUERIES
        or not isinstance(ids, list)
        or not 1 <= len(ids) <= 300
        or len(set(ids)) != len(ids)
        or any(not isinstance(value, str) or not re.fullmatch(r"[1-9][0-9]{0,19}", value) for value in ids)
    ):
        raise ApiError(422, "关联来源查询范围无效")
    query = QUERIES[kind].format(ids=",".join(ids))
    url = f"https://{ns.settings.account}.suitetalk.api.netsuite.com/services/rest/query/v1/suiteql"
    rows, seen, size = [], set(), 0
    # 不使用远端 next 链接，限制整次返回行数与字节数；任意页失败不返回部分成功。
    for offset in range(0, 5000, 1000):
        try:
            with ns.client.stream(
                "POST",
                url,
                params={"limit": 1000, "offset": offset},
                headers={"Authorization": f"Bearer {ns.token()}", "Prefer": "transient"},
                json={"q": query},
                timeout=60,
                follow_redirects=False,
            ) as response:
                if not response.is_success:
                    raise ApiError(502, f"NS 关联依据读取失败（HTTP {response.status_code}），未保存本页")
                chunks = []
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > 8 * 1024 * 1024:
                        raise ApiError(422, "关联依据超过读取上限，请缩小每页单据数")
                    chunks.append(chunk)
            data = json.loads(b"".join(chunks), parse_float=Decimal)
        except httpx.HTTPError:
            raise ApiError(502, "NS 关联依据读取超时或失败，未保存本页") from None
        except (ValueError, UnicodeError):
            raise ApiError(502, "NS 关联依据响应格式无效，未保存本页") from None
        if not isinstance(data, dict) or not isinstance(data.get("items"), list):
            raise ApiError(502, "NS 关联依据响应不完整")
        items, more = data["items"], data.get("hasMore")
        if not isinstance(more, bool) or len(items) > 1000 or (more and len(items) != 1000):
            raise ApiError(502, "NS 关联依据分页不完整")
        for item in items:
            if not isinstance(item, dict):
                raise ApiError(502, "NS 关联依据行格式无效")
            row = {key: value for key, value in item.items() if key != "links"}
            if kind == "purchase_links":
                key = tuple(
                    str(row.get(field, ""))
                    for field in ("previousdoc", "previousline", "nextdoc", "nextline", "linktype")
                )
            elif kind == "parent_lines":
                key = (str(row.get("transaction", "")), str(row.get("id", "")))
            else:
                key = str(row.get("id", ""))
            if not key or (isinstance(key, tuple) and not all(key)) or key in seen:
                raise ApiError(502, "NS 关联依据行身份缺失或重复")
            seen.add(key)
            rows.append(row)
        if not more:
            return rows
    raise ApiError(422, "关联依据超过5000行，请缩小每页单据数；未保存截断结果")

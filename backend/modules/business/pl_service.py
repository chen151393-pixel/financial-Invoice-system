"""按 PL 按需联查；整次读取失败不伪装为完整结果，不触发任何 NS 写入。"""

from datetime import datetime, timezone

from backend.core.errors import ApiError

from .pl_config import parse_config
from .pl_mapper import project, reference, text
from .pl_reader import PlReader


class PlLookupService:
    def __init__(self, ns):
        self.ns = ns

    def configuration(self):
        try:
            parse_config(self.ns.settings)
        except ApiError as exc:
            return {"ready": False, "reason": str(exc)}
        return {"ready": True, "reason": "按 PL 查询实时 NS 数据；仅分组展示，不自动匹配商品"}

    def query(self, pl_number, page=1):
        reader = PlReader(self.ns)
        config = reader.config
        bundle = reader.collect(pl_number)
        rows, warnings = [], bundle["warnings"]
        for purchase_id, purchase, lines in bundle["purchases"]:
            customs_id = reference(purchase.get(config.purchase.customs))
            company_id = reference(purchase.get(config.purchase.company))
            company_name = text(purchase.get(config.purchase.company))
            for line_id, line in lines:
                rows.append(
                    {
                        "source": "采购",
                        "id": line_id,
                        "group": f"{customs_id or '未关联报关单'} / {pl_number} / {company_id or company_name or '公司未填写'}",
                        "values": {
                            **project(purchase, config.purchase),
                            **project(line, config.purchase_line),
                            "pl": pl_number,
                            "company": company_name,
                        },
                    }
                )
        for customs_id, customs, lines in bundle["customs"]:
            for line_id, line in lines:
                if reference(line.get(config.customs_line.pl)) != bundle["pl_id"]:
                    continue
                company_id = reference(line.get(config.customs_line.company))
                company_name = text(line.get(config.customs_line.company))
                rows.append(
                    {
                        "source": "报关",
                        "id": line_id,
                        "group": f"{customs_id} / {pl_number} / {company_id or company_name or '公司未填写'}",
                        "values": {
                            **project(customs, config.customs),
                            **project(line, config.customs_line),
                            "pl": pl_number,
                            "company": company_name,
                        },
                    }
                )
        rows.sort(key=lambda row: (row["group"], 0 if row["source"] == "报关" else 1, row["id"]))
        return {
            "pl": pl_number,
            "rows": rows[(page - 1) * 50 : page * 50],
            "total": len(rows),
            "page": page,
            "hasNext": page * 50 < len(rows),
            "warnings": warnings,
            "queriedAt": datetime.now(timezone.utc).isoformat(),
        }

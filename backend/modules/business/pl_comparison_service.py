"""真实PL＋公司只读核对：按公司内部标识归组，不做跨行金额计算。"""

from datetime import datetime, timezone

from backend.core.errors import ApiError

from .pl_comparison_mapper import comparison_rows
from .pl_export import comparison_download
from .pl_reader import PlReader


class PlComparisonService:
    def __init__(self, ns):
        self.ns = ns

    def query(self, pl, company=""):
        reader = PlReader(self.ns)
        if not reader.config.company_record_type:
            raise ApiError(503, "请配置 company_record_type，确认采购和报关的公司字段引用同一记录类型")
        bundle = reader.collect(pl, discover_customs=True)
        rows = comparison_rows(bundle, reader.config, pl)
        groups = {}
        seen = set()
        warnings = list(bundle["warnings"])
        for row in rows:
            if row["id"] in seen:
                raise ApiError(502, "NS返回了重复明细，未生成不完整核对结果")
            seen.add(row["id"])
            if company and not (
                company == row["companyId"] or company.casefold() in row["company"].casefold()
            ):
                continue
            # 缺失公司ID的源行独立展示，禁止仅凭同名公司将两侧记录拼在一起。
            company_key = row["companyId"] or f"unknown:{row['id']}"
            key = f"{bundle['pl_id']}:{reader.config.company_record_type}:{company_key}"
            if key not in groups:
                groups[key] = {"id": key, "pl": pl, "company": row["company"], "customs": [], "purchases": []}
            group = groups[key]
            group[row["source"]].append({key: row[key] for key in ("id", "headId", "currency", "cells")})
            if not row["companyId"]:
                warnings.append(f"{row['id']} 缺少公司内部标识，已独立展示，请核实公司关联")
        result_groups = list(groups.values())
        for group in result_groups:
            customs, purchases = len(group["customs"]), len(group["purchases"])
            group["summary"] = f"报关 {customs} 行 · 采购 {purchases} 行"
            group["status"] = (
                "待核对" if customs and purchases else "缺少报关明细" if purchases else "缺少采购明细"
            )
        result_groups.sort(key=lambda group: (group["company"], group["id"]))
        queried_at = datetime.now(timezone.utc).isoformat()
        result = {
            "pl": pl,
            "company": company,
            "account": self.ns.settings.account,
            "queriedAt": queried_at,
            "source": "netsuite-rest",
            "groups": result_groups,
            "warnings": list(dict.fromkeys(warnings)),
            "download": None,
        }
        if result_groups:
            result["download"] = comparison_download(result)
        return result

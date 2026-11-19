"""批次资料现状：提单、应有的销售合同（即形式发票）、已生成的合同、报关单文件与齐全度。只读，供资料接口、批次状态校验与打包共用。"""

from backend.modules.review.public import settlement_declaration_lines

from ..dao import bill_dao, contract_dao, party_dao
from ..policy.contract_policy import plan
from ..policy.document_policy import checklist
from ..policy.route_policy import HK_TRANSIT
from .contract_party_reader import resolve


class DocumentReader:
    def __init__(self, *, lead_days=28, declaration_files=None):
        self.lead_days = lead_days
        # 报关单文件现状（DeclarationFiles）；未提供时不展示、不打包报关单
        self.declaration_files = declaration_files

    def state(self, connection, batch, items):
        """返回提单、合同计划、双方来源绑定、当前文件与齐全度；不写主数据。"""
        bills = bill_dao.active(connection, batch["id"])
        lines = settlement_declaration_lines(connection, [item["declaration_no"] for item in items])
        planned, plan_issues = plan(batch, items, lines, bills, lead_days=self.lead_days)
        contracts = contract_dao.of_batch(connection, batch["id"])
        bindings, party_issues = resolve(connection, items, planned)
        parties = party_dao.by_ids(
            connection, {row[key] for row in contracts for key in ("seller_party_id", "buyer_party_id")}
        )
        result = checklist(items, bills, planned, plan_issues, contracts, bindings, party_issues)
        files = self.declaration_files.state(connection, items) if self.declaration_files else []
        # 报关单文件未归档只提示，不阻止确认资料已出
        result["warnings"] = result["warnings"] + [row["note"] for row in files if row["note"]]
        return {
            "bills": bills,
            "planned": planned,
            "plan_issues": plan_issues,
            "contracts": contracts,
            "parties": parties,
            "contract_parties": bindings,
            "party_issues": party_issues,
            "declaration_files": files,
            **result,
        }

    def blocking_reason(self, connection, batch, items):
        """香港批次确认资料已出前的校验；直接收汇资料不参与该批次状态转换。"""
        if batch["route"] != HK_TRANSIT:
            return ""
        issues = self.state(connection, batch, items)["issues"]
        if not issues:
            return ""
        more = f" 等 {len(issues)} 项" if len(issues) > 1 else ""
        return f"资料未齐：{issues[0]}{more}"

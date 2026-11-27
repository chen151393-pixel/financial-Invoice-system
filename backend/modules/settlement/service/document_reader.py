"""批次资料现状：提单、应有的销售合同（即形式发票）、已生成的合同、报关单文件与齐全度。只读，供资料接口、批次状态校验与打包共用。"""

from backend.modules.review.public import settlement_declaration_lines

from ..dao import bill_dao, contract_dao, party_dao
from ..policy.contract_policy import plan
from ..policy.document_policy import checklist
from ..policy.route_policy import HK_TRANSIT
from .contract_party_reader import resolve, source_facts


class DocumentReader:
    def __init__(self, *, lead_days=28, declaration_files=None):
        self.lead_days = lead_days
        # 报关单文件现状（DeclarationFiles）；未提供时不展示、不打包报关单
        self.declaration_files = declaration_files

    def state(self, connection, batch, items, *, snapshot=None):
        """返回提单、合同计划、双方来源绑定、当前文件与齐全度；不写主数据。"""
        group_id = batch.get("document_group_id")
        bills = snapshot["bills"][group_id] if snapshot else bill_dao.active(connection, batch["id"])
        lines = (
            snapshot["lines"]
            if snapshot
            else settlement_declaration_lines(connection, [item["declaration_no"] for item in items])
        )
        planned, plan_issues = plan(batch, items, lines, bills, lead_days=self.lead_days)
        if batch.get("document_issue"):
            plan_issues.append(batch["document_issue"])
        contracts = (
            snapshot["contracts"][group_id] if snapshot else contract_dao.of_batch(connection, batch["id"])
        )
        bindings, party_issues = resolve(
            connection, items, planned, facts=snapshot["facts"] if snapshot else None
        )
        parties = (
            snapshot["parties"]
            if snapshot
            else party_dao.by_ids(
                connection, {row[key] for row in contracts for key in ("seller_party_id", "buyer_party_id")}
            )
        )
        result = checklist(items, bills, planned, plan_issues, contracts, bindings, party_issues)
        files = (
            [
                snapshot["files"][item["declaration_no"]]
                for item in items
                if item["declaration_no"] in snapshot["files"]
            ]
            if snapshot
            else self.declaration_files.state(connection, items)
            if self.declaration_files
            else []
        )
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

    def group_states(self, connection, contexts):
        """一次请求批量读取选中组的资料依据，不随组数重复查询。"""
        if not contexts:
            return {}
        ids = list(contexts)
        items = [item for _, rows in contexts.values() for item in rows]
        facts = source_facts(connection, items)
        snapshot = dict(
            bills=bill_dao.by_groups(connection, ids),
            contracts=contract_dao.by_groups(connection, ids),
            lines=settlement_declaration_lines(connection, [item["declaration_no"] for item in items]),
            facts=facts,
            parties={party["id"]: party for party in facts["parties"].values()},
            files={
                row["declaration_no"]: row
                for row in (self.declaration_files.state(connection, items) if self.declaration_files else [])
            },
        )
        return {
            group_id: self.state(connection, context, rows, snapshot=snapshot)
            for group_id, (context, rows) in contexts.items()
        }

    def states(self, connection, contexts):
        """批量读取混合作用域；共享来源事实，提单、合同及返回主体仍按作用域隔离。"""
        if not contexts:
            return {}
        references = list(contexts)
        items = [item for _, rows in contexts.values() for item in rows]
        facts = source_facts(connection, items)
        bills = bill_dao.by_scopes(connection, references)
        contracts = contract_dao.by_scopes(connection, references)
        lines = settlement_declaration_lines(connection, [item["declaration_no"] for item in items])
        # 合同可能引用已停用主体，不能只从当前启用主体中取回显示资料。
        parties = party_dao.by_ids(
            connection,
            {
                row[key]
                for rows in contracts.values()
                for row in rows
                for key in ("seller_party_id", "buyer_party_id")
            },
        )
        files = {
            row["declaration_no"]: row
            for row in (self.declaration_files.state(connection, items) if self.declaration_files else [])
        }
        result = {}
        for reference, (context, rows) in contexts.items():
            group_id = context.get("document_group_id")
            party_ids = {
                row[key] for row in contracts[reference] for key in ("seller_party_id", "buyer_party_id")
            }
            snapshot = dict(
                bills={group_id: bills[reference]},
                contracts={group_id: contracts[reference]},
                lines=lines,
                facts=facts,
                files=files,
                parties={identity: party for identity, party in parties.items() if identity in party_ids},
            )
            result[reference] = self.state(connection, context, rows, snapshot=snapshot)
        return result

    def blocking_reason(self, connection, batch, items):
        """香港批次确认资料已出前的校验；直接收汇资料不参与该批次状态转换。"""
        if batch["route"] != HK_TRANSIT:
            return ""
        issues = self.state(connection, batch, items)["issues"]
        if not issues:
            return ""
        more = f" 等 {len(issues)} 项" if len(issues) > 1 else ""
        return f"资料未齐：{issues[0]}{more}"

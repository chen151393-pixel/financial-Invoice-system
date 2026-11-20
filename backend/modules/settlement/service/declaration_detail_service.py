"""报关单结汇详情：复用收汇快照、批次和资料读取；不创建资料组，不执行任何业务写入。"""

from backend.core.errors import ApiError

from ..mapper import document_mapper
from ..mapper.batch_mapper import detail as batch_detail
from ..mapper.batch_mapper import stamp
from ..policy import declaration_detail_policy as rules
from ..policy.contract_policy import document_key
from ..vo.declaration_detail_vo import DeclarationDetail
from .direct_document_source import DirectDocumentSource
from .receivable_service import _item


class DeclarationDetailService:
    def __init__(self, receivables, *, fee_alert):
        self.receivables = receivables
        self.engine = receivables.engine
        self.reader = receivables.reader
        self.fee_alert = fee_alert

    def _load(self, connection, number):
        snapshot = self.receivables.snapshot(connection)
        matches = [row for row in snapshot[0] if row["declaration_no"] == number]
        if len(matches) != 1:
            raise ApiError(404, "未找到当前报关单结汇依据，请刷新列表后重试")
        row = matches[0]
        self.receivables._documents(connection, [row], snapshot[3], snapshot[4])
        return row, snapshot

    def get(self, number):
        if self.engine is None:
            raise ApiError(503, "业务数据库未配置")
        with self.engine.connect() as connection:
            row, (rows, _, receipts, _, items, today) = self._load(connection, number)
            batch = row["batch"] if row["route"] == "hk_transit" else None
            if batch:
                context, linked = batch, items[batch["id"]]
            elif row["route"] == "direct":
                context, linked = DirectDocumentSource(self.receivables.candidates).for_row(connection, row)
            else:
                context, linked = DirectDocumentSource.context(row)
            # 香港未登记批次不能借用直接收汇资料作用域。
            state = (
                self.reader.state(connection, context, linked) if batch or row["route"] == "direct" else None
            )
            evidence, balance = ([], "")
            if row["route"] == "direct" and row["usable"]:
                direct_receipts = [
                    r
                    for r in receipts
                    if self.receivables.candidates.route(r["customer_name"])[0] == "direct"
                ]
                evidence, balance = rules.direct_evidence(row, rows, direct_receipts)
            issue = state["issues"][0] if state and state["issues"] else ""
            return DeclarationDetail(
                item=_item(row),
                steps=rules.steps(row, state),
                batch=batch_detail(batch, linked, self.fee_alert, issue) if batch else None,
                allocations=evidence,
                ledgerBalance=balance,
                ledgerNote="同一境外收货人、收款抬头、币种，按出口日期和银行收汇日期先后推算；不保存人工分配关系。余额为全部历史出口减收汇，负数表示超收。"
                if evidence
                else "",
                documents=self._documents(connection, number, row, linked, state, context),
                events=self._events(batch, state),
                asOf=str(today),
            )

    def _documents(self, connection, number, row, linked, state, context):
        files = self.reader.declaration_files
        originals = files.state(connection, [row]) if files else []
        original = originals[0] if originals else None
        scope = (
            "batch"
            if row["batch"] and row["route"] == "hk_transit"
            else "single"
            if row["route"] == "direct"
            else "none"
        )
        if context.get("document_group_id"):
            scope = "group"
        label = (
            row["batch"]["batch_no"]
            if scope == "batch"
            else context["group_no"]
            if scope == "group"
            else "本报关单资料"
            if scope == "single"
            else "登记回款后办理"
        )
        bills, contracts = [], []
        if state:
            bills = [
                document_mapper.bill(b) for b in state["bills"] if number in (b["declaration_nos"] or [])
            ]
            generated = {document_key(r): r for r in state["contracts"]}
            for planned in state["planned"]:
                if number not in planned["declaration_nos"]:
                    continue
                contract = generated.get(document_key(planned))
                contracts.append(
                    dict(
                        planned=document_mapper.planned(
                            planned, row["currency"], state["contract_parties"][document_key(planned)]
                        ),
                        contract=document_mapper.contract(contract, state["parties"], state["stale"])
                        if contract
                        else None,
                        label="未生成"
                        if not contract
                        else "需重新生成"
                        if document_key(contract) in state["stale"]
                        else "已生成",
                    )
                )
        return dict(
            groupId=context.get("document_group_id"),
            scopeKind=scope,
            scopeLabel=label,
            scopeNumbers=[r["declaration_no"] for r in linked] if scope != "none" else [],
            note="提单与合同在所在批次办理；跨报关单的同号合同按批次合并生成一份。"
            if scope == "batch"
            else "本报关单在资料组统一办理提单和合同；本页只读，不影响收款推算与自动结汇。"
            if scope == "group"
            else "当前按单票留存资料；不影响收款推算与自动结汇。"
            if scope == "single"
            else "请先在香港中转登记回款并建立批次。",
            original=dict(
                statusLabel=original["label"] if original else "未接入归档",
                archived=bool(original and original["status"] == "archived"),
                files=[
                    dict(name=f["filename"], url=f"/api/settlement/receivables/{number}/originals/{index}")
                    for index, f in enumerate(original["files"])
                ]
                if original
                else [],
                note=original["note"] if original else "报关单原件由开票跟进下载归档。",
            ),
            bills=bills,
            contracts=contracts,
            issues=state["issues"] if state else [],
            warnings=state["warnings"] if state else [],
        )

    @staticmethod
    def _events(batch, state):
        events = []

        def add(at, actor, description):
            if at:
                events.append(dict(at=stamp(at), actor=actor or "", description=description))

        if batch:
            add(batch["created_at"], batch["created_by"], "登记香港到账并建立批次")
            add(batch["documents_ready_at"], batch["documents_ready_by"], "确认资料已出")
            add(batch["settled_at"], batch["settled_by"], "登记汇回并确认结汇")
        if state:
            for bill in state["bills"]:
                add(
                    bill["uploaded_at"], bill["uploaded_by"], f"上传提单 {bill['bl_no'] or bill['file_name']}"
                )
            for contract in state["contracts"]:
                add(
                    contract["generated_at"],
                    contract["generated_by"],
                    f"生成销售合同 {contract['contract_no']}",
                )
        return sorted(events, key=lambda e: e["at"], reverse=True)

    def original(self, number, index):
        if self.engine is None:
            raise ApiError(503, "业务数据库未配置")
        if self.reader.declaration_files is None:
            raise ApiError(404, "报关单原件归档未接入")
        with self.engine.connect() as connection:
            row, _ = self._load(connection, number)
            original = self.reader.declaration_files.state(connection, [row])[0]
            if original["status"] != "archived" or index < 0 or index >= len(original["files"]):
                raise ApiError(404, "报关单归档原件不存在，请刷新后重试")
            file = original["files"][index]
            content, reason = self.reader.declaration_files.read(file)
            if content is None:
                raise ApiError(409, reason)
            return file["filename"], content

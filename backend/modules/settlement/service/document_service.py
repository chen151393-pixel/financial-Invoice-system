"""批次资料视图：提单、销售合同、齐全度与可操作判断。写入用例（提单、合同）完成后也返回本视图。"""

from backend.core.errors import ApiError

from ..dao import batch_dao, batch_item_dao
from ..mapper import document_mapper as mapper
from ..policy.batch_state_policy import status_label
from ..policy.route_policy import HK_TRANSIT
from ..vo.batch_vo import Action
from ..vo.document_vo import BatchDocuments, ContractDefaults
from .contract_pdf import template


def _action(reason):
    return Action(allowed=not reason, reason=reason)


def edit_reason(batch):
    """资料只在香港中转批次“香港已收”阶段可修改；确认资料已出后只读。"""
    if batch.get("document_kind") == "direct":
        return batch["document_issue"]
    if batch["route"] != HK_TRANSIT:
        return "仅香港中转批次需要资料包"
    if batch["status"] != "collected":
        return f"批次{status_label(batch['route'], batch['status'])}，资料不能再修改"
    return ""


def load(connection, batch_id, *, lock=False):
    batch = batch_dao.get(connection, batch_id, lock=lock)
    if batch is None:
        raise ApiError(404, "结汇批次不存在")
    return batch, batch_item_dao.of_batches(connection, [batch_id])[batch_id]


class DocumentService:
    def __init__(self, engine, reader, source=None):
        self.engine = engine
        self.reader = reader
        self.source = source

    def load(self, connection, reference, *, lock=False):
        return (
            self.source.load(connection, reference, lock=lock)
            if self.source
            else load(connection, reference, lock=lock)
        )

    def get(self, batch_id):
        if self.engine is None:
            raise ApiError(503, "业务数据库未配置")
        with self.engine.connect() as connection:
            batch, items = self.load(connection, batch_id)
            return self.view(connection, batch, items)

    def view(self, connection, batch, items):
        state = self.reader.state(connection, batch, items)
        bindings = list(state["contract_parties"].values())
        sellers = list(
            {binding["seller"]["id"]: binding["seller"] for binding in bindings if binding["seller"]}.values()
        )
        buyer_names = list(
            dict.fromkeys(binding["buyer_name"] for binding in bindings if binding["buyer_name"])
        )
        used = state["contracts"][0] if state["contracts"] else None
        defaults = template()
        editable = edit_reason(batch)
        generate = editable
        if not generate and state["plan_issues"]:
            generate = state["plan_issues"][0]
        if not generate and state["party_issues"]:
            generate = state["party_issues"][0]
        package = ""
        if batch["status"] == "cancelled":
            package = "批次已作废"
        elif batch["route"] != HK_TRANSIT and batch.get("document_kind") != "direct":
            package = "仅香港中转批次需要资料包"
        elif state["issues"]:
            package = f"资料未齐，还有 {len(state['issues'])} 项待处理"
        return BatchDocuments(
            batchId=batch["id"] if not self.source else None,
            declarationNos=[item["declaration_no"] for item in items],
            bills=[mapper.bill(row) for row in state["bills"]],
            planned=[
                mapper.planned(item, batch["currency"], state["contract_parties"][item["contract_no"]])
                for item in state["planned"]
            ],
            contracts=[mapper.contract(row, state["parties"], state["stale"]) for row in state["contracts"]],
            buyerName="、".join(buyer_names),
            buyerReady=bool(bindings) and all(binding["buyer"] is not None for binding in bindings),
            sellers=[mapper.party_option(row) for row in sellers],
            defaults=ContractDefaults(
                sellerPartyId=sellers[0]["id"] if len(sellers) == 1 else None,
                tradeTerm=used["trade_term"] if used else "FOB",
                paymentTermsCn=used["payment_terms_cn"] if used else defaults["default_payment_terms_cn"],
                paymentTermsEn=used["payment_terms_en"] if used else defaults["default_payment_terms_en"],
            ),
            complete=not state["issues"],
            issues=state["issues"],
            warnings=state["warnings"],
            declarationFiles=[mapper.declaration_file(row) for row in state["declaration_files"]],
            edit=_action(editable),
            generate=_action(generate),
            package=_action(package),
            packageUrl=f"{mapper.document_base(batch)}/package",
        )

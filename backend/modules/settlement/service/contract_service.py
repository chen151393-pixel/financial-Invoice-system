"""销售合同用例：按模板为批次内每个出口合同号生成 PDF。

顺序：读取生成依据 → 事务外渲染并写文件 → 短事务内重新读取依据并核对摘要未变，再整批替换合同记录；
提交后删除被替换的旧文件。金额、日期、口岸全部由后端按规则取数。
"""

from datetime import UTC, datetime

from sqlalchemy.exc import SQLAlchemyError

from backend.core import write_lock
from backend.core.errors import ApiError

from ..dao import contract_dao
from ..policy.contract_policy import digest, document_key
from .contract_pdf import render
from .document_service import edit_reason


def _now():
    return datetime.now(UTC).replace(tzinfo=None)


def _basis(drafts):
    # 抬头身份也参与生成期间重校验，防止两个不同主体的展示字段相同时漏掉来源变化。
    return [(draft["digest"], draft["buyer"]["id"], draft["seller"]["id"]) for draft in drafts]


class ContractService:
    def __init__(self, engine, store, reader, documents, *, font_path=None):
        self.engine, self.store, self.reader, self.documents = engine, store, reader, documents
        self.font_path = font_path

    def generate(self, batch_id, body, owner):
        if owner.startswith("service:"):
            raise ApiError(403, "服务身份只读，不能生成销售合同")
        terms = {
            "trade_term": body.tradeTerm.upper(),
            "payment_terms_cn": body.paymentTermsCn,
            "payment_terms_en": body.paymentTermsEn,
        }
        with self.engine.connect() as connection:
            batch, drafts = self._drafts(connection, batch_id, body.sellerPartyId, terms)
            if batch["id"] != batch_id:
                raise ApiError(409, "资料组已合并，请刷新后在新组生成合同")
        files = []
        try:
            for draft in drafts:
                stamps, missing = self._stamps(draft["buyer"], draft["seller"])
                content = render(
                    draft["contract"],
                    draft["buyer"],
                    draft["seller"],
                    terms,
                    batch["currency"],
                    stamps,
                    font_path=self.font_path,
                )
                file_id, sha256 = self.store.save(content, "pdf")
                files.append((draft, file_id, sha256, len(content), missing))
            now = _now()
            with write_lock.transaction(self.engine, "settlement") as connection:
                batch, current = self._drafts(connection, batch_id, body.sellerPartyId, terms, lock=True)
                if _basis(current) != _basis(drafts):
                    raise ApiError(409, "生成期间提单、海关回执或合同抬头发生变化，请重新生成")
                old = contract_dao.of_batch(connection, batch_id)
                contract_dao.replace(
                    connection,
                    batch_id,
                    [self._row(draft, terms, batch, file, owner, now) for draft, *file in files],
                    now,
                )
                _, items = self.documents.load(connection, batch_id)
                view = self.documents.view(connection, batch, items)
        except ApiError:
            self._discard(files)
            raise
        except SQLAlchemyError:
            self._discard(files)
            raise ApiError(503, "销售合同保存失败，请检查业务数据库及迁移状态") from None
        for row in old:
            self.store.remove(row["file_id"], "pdf")
        return view

    def file(self, batch_id, contract_id):
        """返回 (文件名, PDF 字节)。"""
        with self.engine.connect() as connection:
            context, _ = self.documents.load(connection, batch_id)
            row = contract_dao.get(connection, context["id"], contract_id)
        if row is None:
            raise ApiError(404, "销售合同不存在，可能已重新生成，请刷新")
        return f"销售合同{row['contract_no']}.pdf", self.store.read(row["file_id"], "pdf")

    def _drafts(self, connection, batch_id, seller_id, terms, *, lock=False):
        batch, items = self.documents.load(connection, batch_id, lock=lock)
        reason = edit_reason(batch)
        if reason:
            raise ApiError(409, reason)
        state = self.reader.state(connection, batch, items)
        if state["plan_issues"]:
            raise ApiError(409, "不能生成销售合同：" + "；".join(state["plan_issues"][:3]))
        if state["party_issues"]:
            raise ApiError(409, "不能生成销售合同：" + "；".join(state["party_issues"][:3]))
        if not state["planned"]:
            raise ApiError(409, "没有可生成销售合同的明细")
        drafts = []
        for contract in state["planned"]:
            binding = state["contract_parties"][document_key(contract)]
            buyer, seller = binding["buyer"], binding["seller"]
            # 旧客户端仍可传卖方 ID，但不能覆盖当前 NS 申报抬头的匹配结果。
            if seller_id == buyer["id"]:
                raise ApiError(422, "卖方不能与买方相同")
            if seller_id is not None and seller_id != seller["id"]:
                raise ApiError(422, "合同卖方必须与对应 NS 报关单的申报抬头一致，请刷新资料后重试")
            drafts.append(
                {
                    "contract": contract,
                    "buyer": buyer,
                    "seller": seller,
                    "digest": digest(contract, buyer, seller, terms),
                }
            )
        return batch, drafts

    def _stamps(self, buyer, seller):
        stamps, missing = {}, []
        for role, label, party in (("buyer", "买方", buyer), ("seller", "卖方", seller)):
            if party["stamp_file_id"]:
                stamps[role] = self.store.path(party["stamp_file_id"], party["stamp_extension"])
                if not stamps[role].exists():
                    raise ApiError(409, f"{label}印章图片文件缺失，请在“合同抬头”中重新上传")
            else:
                missing.append(label)
        return stamps, missing

    @staticmethod
    def _row(draft, terms, batch, file, owner, now):
        file_id, sha256, size, missing = file
        contract = draft["contract"]
        return {
            "contract_no": contract["contract_no"],
            "document_key": contract.get("document_key"),
            "contract_date": contract["contract_date"],
            "declaration_nos": contract["declaration_nos"],
            "buyer_party_id": draft["buyer"]["id"],
            "seller_party_id": draft["seller"]["id"],
            **terms,
            "port_of_loading": contract["port_of_loading"],
            "port_of_destination": contract["port_of_destination"],
            "currency": batch["currency"],
            "amount": contract["amount"],
            "source_digest": draft["digest"],
            "file_id": file_id,
            "sha256": sha256,
            "size_bytes": size,
            "stamp_note": f"{'、'.join(missing)}未上传印章，合同未盖该方印章" if missing else None,
            "generated_by": owner,
            "generated_at": now,
        }

    def _discard(self, files):
        for _, file_id, *_ in files:
            self.store.remove(file_id, "pdf")

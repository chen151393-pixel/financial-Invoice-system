"""批次资料行 → VO 的纯转换。"""

from urllib.parse import quote

from ..policy.bill_parse_policy import missing_fields
from ..vo.document_vo import Bill, Contract, DeclarationFile, PartyOption, PlannedContract
from ..vo.party_vo import Party
from .batch_mapper import amount, stamp, text

BASE = "/api/settlement"


def document_base(row):
    if row.get("direct_declaration_no"):
        return f"{BASE}/direct-documents/{quote(row['direct_declaration_no'], safe='')}"
    return f"{BASE}/batches/{row['batch_id'] if 'batch_id' in row else row['id']}"


def bill(row):
    return Bill(
        id=row["id"],
        fileName=row["file_name"],
        fileUrl=f"{document_base(row)}/bills/{row['id']}/file",
        blNo=text(row["bl_no"]),
        portOfLoading=text(row["port_of_loading"]),
        portOfDischarge=text(row["port_of_discharge"]),
        onBoardDate=text(row["on_board_date"]),
        declarationNos=list(row["declaration_nos"] or []),
        missing=missing_fields(row),
        parseNote=text(row["parse_note"]),
        uploadedBy=row["uploaded_by"],
        uploadedAt=stamp(row["uploaded_at"]),
    )


def contract(row, parties, stale):
    seller = parties.get(row["seller_party_id"])
    return Contract(
        id=row["id"],
        contractNo=row["contract_no"],
        fileUrl=f"{document_base(row)}/contracts/{row['id']}/file",
        contractDate=text(row["contract_date"]),
        currency=row["currency"],
        amount=amount(row["amount"]),
        declarationNos=list(row["declaration_nos"] or []),
        sellerName=seller["name"] if seller else "",
        tradeTerm=row["trade_term"],
        portOfLoading=row["port_of_loading"],
        portOfDestination=row["port_of_destination"],
        stale=row["contract_no"] in stale,
        stampNote=text(row["stamp_note"]),
        generatedBy=row["generated_by"],
        generatedAt=stamp(row["generated_at"]),
    )


def planned(item, currency):
    return PlannedContract(
        contractNo=item["contract_no"],
        currency=currency,
        amount=amount(item["amount"]),
        declarationNos=item["declaration_nos"],
    )


def party_option(row):
    return PartyOption(id=row["id"], name=row["name"], hasStamp=bool(row["stamp_file_id"]))


def party(row):
    return Party(
        id=row["id"],
        name=row["name"],
        nameCn=text(row["name_cn"]),
        nameEn=row["name_en"],
        addressCn=text(row["address_cn"]),
        addressEn=row["address_en"],
        phone=text(row["phone"]),
        hasStamp=bool(row["stamp_file_id"]),
        stampUrl=f"{BASE}/parties/{row['id']}/stamp" if row["stamp_file_id"] else "",
        updatedBy=row["updated_by"],
        updatedAt=stamp(row["updated_at"]),
    )


def declaration_file(row):
    return DeclarationFile(
        declarationNo=row["declaration_no"],
        recordNo=row["record_no"],
        status=row["status"],
        statusLabel=row["label"],
        archived=row["status"] == "archived",
        fileNames=[file["filename"] for file in row["files"]],
    )

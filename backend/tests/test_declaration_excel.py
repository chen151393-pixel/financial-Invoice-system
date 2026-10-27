"""Excel XML 原件解码与归档；假 NS、SQLite 和临时目录，不操作真实共享盘。"""

import base64
from pathlib import Path

import httpx
import pytest
from backend.core.errors import ApiError
from backend.integrations.netsuite.declaration_documents import read_documents
from backend.integrations.netsuite.declaration_file import decode_file
from backend.tests.test_task_documents import PDF, declaration_adapter, files_payload
from backend.tests.test_task_documents_completion import app_services as app_services
from backend.tests.test_task_documents_completion import approved as approved  # 共用真实审核夹具
from backend.tests.test_task_documents_completion import declaration_rows
from backend.tests.test_task_documents_completion import engine as engine
from backend.tests.test_task_documents_completion import ns as ns
from backend.tests.test_task_documents_completion import services as services

XML = b""" <?xml version="1.0"?>
<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet"
 xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">
 <Worksheet ss:Name="invoice"><Table><Row><Cell><Data ss:Type="String">A &amp; B</Data>
 </Cell></Row></Table></Worksheet></Workbook>"""


def excel_payload(content=XML, *, kind="invoice", format_name="excel_xml"):
    return {
        "id": "870",
        "type": kind,
        "files": [
            {
                "filename": "../../evil.pdf",
                "format": format_name,
                "contentBase64": base64.b64encode(content).decode(),
            }
        ],
    }


@pytest.mark.parametrize("kind", ["invoice", "customs_declaration"])
def test_excel_xml_uses_explicit_format_and_preserves_original_bytes(kind):
    ns = declaration_adapter(lambda _: httpx.Response(200, json=excel_payload(kind=kind)))
    try:
        result = read_documents(ns, "CD870", "REAL870", kind)
        assert result["files"] == [{"content": XML, "format": "excel_xml", "extension": ".xls"}]
    finally:
        ns.client.close()


@pytest.mark.parametrize(
    "payload",
    [
        excel_payload(PDF),
        excel_payload(b"PKfake-xlsx", format_name="xlsx"),
        excel_payload(b"<html>login</html>"),
        excel_payload(
            XML.replace(b"<Workbook", b'<?xml-stylesheet href="https://example.test/style"?><Workbook')
        ),
        excel_payload(XML[:-10]),
        excel_payload(XML.replace(b"<Cell>", b'<Cell ss:Formula="=1+1">')),
        excel_payload(XML.replace(b"<Cell>", b'<Cell ss:HRef="https://example.test/">')),
        excel_payload(XML.replace(b"<Workbook ", b'<!DOCTYPE Workbook [<!ENTITY x "bad">]><Workbook ')),
        excel_payload(XML.replace(b"<Table>", b"<Other>").replace(b"</Table>", b"</Other>")),
        excel_payload(XML, format_name="xls"),
        files_payload([XML]),  # 缺少格式标记时仍按 PDF 校验，不按扩展名猜格式
    ],
)
def test_invalid_or_active_spreadsheet_fails_closed(payload):
    ns = declaration_adapter(lambda _: httpx.Response(200, json=payload))
    try:
        with pytest.raises(ApiError) as error:
            read_documents(ns, "CD870", "REAL870", "invoice")
        assert error.value.status == 502
    finally:
        ns.client.close()


def test_excel_is_not_enabled_for_unconfirmed_sales_contract():
    with pytest.raises(ValueError, match="unsupported"):
        decode_file(excel_payload()["files"][0], "sales_contract")


def test_worker_archives_excel_and_redownload_cannot_change_format_or_file_count(engine, services, approved):
    excel = decode_file(excel_payload()["files"][0], "invoice")
    contracts = services["contracts"]
    contracts.declaration_files["invoice"] = [excel]
    contracts.declaration_files["customs_declaration"] = [excel]
    services["worker"].run_once()
    files = declaration_rows(engine)["invoice"]["files"]
    path = Path(files[0]["path"])
    assert path.name == "发票_CD870.xls" and path.read_bytes() == XML
    assert path.parent.name == "CD870_REAL870"
    services["declarations"].retry(approved["id"], "invoice", "user:admin")
    assert declaration_rows(engine)["invoice"]["files"] == files
    for changed in ([PDF], [excel, excel], [{**excel, "content": XML + b" "}]):
        contracts.declaration_files["invoice"] = changed
        with pytest.raises(ApiError) as error:
            services["declarations"].retry(approved["id"], "invoice", "user:admin")
        assert error.value.status == 409
        row = declaration_rows(engine)["invoice"]
        assert row["status"] == "archived" and row["files"] == files
        assert list(path.parent.glob("发票*")) == [path]
        assert path.read_bytes() == XML

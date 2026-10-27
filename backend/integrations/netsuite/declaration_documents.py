"""报关资料（报关单、销售合同、发票）只读下载；按 CD 编号重新定位报关单，绝不复用其他环境的内部 ID。

RESTlet 约定（由 NS 侧提供，见本目录 README）：
GET 参数 script、deploy、id（报关单内部 ID）、type（customs_declaration / sales_contract / invoice），
files 项含 filename、contentBase64、可选 format（pdf 或 excel_xml）；旧响应默认 PDF。
"""

import binascii

from backend.core.errors import ApiError

from .declaration_file import decode_file
from .restlet_file import fetch_json

RECORD_TYPE = "customrecord_swc_declare_record"
REAL_NUMBER_FIELD = "custrecord_swc_realno"
DOCUMENT_TYPES = {"customs_declaration": "报关单", "sales_contract": "销售合同", "invoice": "发票"}
MAX_FILES = 10
TOTAL_LIMIT = 20 * 1024 * 1024


def unavailable_reason(settings):
    if not settings.declaration_doc_script or not settings.declaration_doc_deploy:
        return "报关资料下载接口尚未配置"
    if not {"restlets", "rest_webservices"}.issubset(settings.scope):
        return "报关资料下载连接需要 restlets 与 rest_webservices 只读授权"
    return ""


def read_documents(ns, record_no, declaration_no, doc_type):
    """返回 {ns_id, environment, files: [{content, format, extension}]}；全部校验后返回。"""
    settings = ns.settings
    reason = unavailable_reason(settings)
    if reason:
        raise ApiError(503, reason)
    label = DOCUMENT_TYPES.get(doc_type)
    if label is None:
        raise ApiError(422, "不支持的报关资料类型")
    ids = ns.filtered_ids(RECORD_TYPE, "name", record_no)
    if len(ids) != 1 or not str(ids[0]).isdigit():
        raise ApiError(409, "下载环境中未找到唯一的同编号报关单，请核对 CD 编号")
    ns_id = str(ids[0])
    record = ns.request("GET", RECORD_TYPE, ns_id)["data"]
    if (
        not isinstance(record, dict)
        or record.get("name") != record_no
        or str(record.get("id")) != ns_id
        or (record.get(REAL_NUMBER_FIELD) or "") != declaration_no
    ):
        raise ApiError(409, "下载环境的报关单编号或真实报关单号与本系统不一致，未下载文件")
    data = fetch_json(
        ns,
        settings.declaration_doc_script,
        settings.declaration_doc_deploy,
        {"id": ns_id, "type": doc_type},
        label,
    )
    try:
        if not isinstance(data, dict) or str(data.get("id")) != ns_id or data.get("type") != doc_type:
            raise ValueError("unexpected record")
        files = data.get("files")
        if not isinstance(files, list) or len(files) > MAX_FILES:
            raise ValueError("unexpected files")
        contents = [decode_file(item, doc_type) for item in files]
    except (ValueError, UnicodeError, binascii.Error):
        raise ApiError(502, f"{label}返回的记录或文件格式无效、不完整，未保存文件") from None
    if not contents:
        raise ApiError(404, f"NS 中暂无该报关单的{label}文件，请在 NS 补齐后重试")
    if sum(len(item["content"]) for item in contents) > TOTAL_LIMIT:
        raise ApiError(502, f"{label}文件合计超过 20 MB，未保存")
    return {"ns_id": ns_id, "environment": settings.account, "files": contents}

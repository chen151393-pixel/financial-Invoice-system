"""专用子采购合同只读下载；按业务编号重新定位，绝不复用沙箱内部 ID。"""

import binascii
import re
from dataclasses import replace

from dotenv import dotenv_values

from backend.core.config import load_settings
from backend.core.errors import ApiError

from .restlet_file import decode_pdf, fetch_json


def connection_settings(settings):
    if settings.subpo_connection_file is None:
        return settings
    path = settings.subpo_connection_file
    if not path.is_file():
        raise ValueError("子采购合同专用连接配置文件不存在")
    values = dotenv_values(path, interpolate=False)
    # 只读取认证配置，不继承外部项目的数据库、服务入口或写入能力。
    values = {
        key: value
        for key, value in values.items()
        if key
        in {
            "NETSUITE_ACCOUNT_ID",
            "NETSUITE_CLIENT_ID",
            "NETSUITE_CERTIFICATE_ID",
            "NETSUITE_PRIVATE_KEY_PATH",
            "NETSUITE_JWT_ALGORITHM",
        }
    }
    if values.get("NETSUITE_PRIVATE_KEY_PATH"):
        values["NETSUITE_PRIVATE_KEY_PATH"] = str(
            (path.parent / values["NETSUITE_PRIVATE_KEY_PATH"]).resolve()
        )
    values.update(
        NETSUITE_RECORD_TYPES="customrecord_swc_subpo",
        NETSUITE_WRITE_ENABLED="false",
        NETSUITE_SCOPE="restlets,rest_webservices",
    )
    target = load_settings(values)
    return replace(
        target,
        subpo_contract_script=settings.subpo_contract_script,
        subpo_contract_deploy=settings.subpo_contract_deploy,
        declaration_doc_script=settings.declaration_doc_script,
        declaration_doc_deploy=settings.declaration_doc_deploy,
    )


def read_contract(ns, number, supplier, declaration):
    settings = ns.settings
    if not settings.subpo_contract_script or not settings.subpo_contract_deploy:
        raise ApiError(503, "子采购合同下载接口尚未配置")
    if not {"restlets", "rest_webservices"}.issubset(settings.scope):
        raise ApiError(503, "合同下载连接需要 restlets 与 rest_webservices 只读授权")
    ids = ns.filtered_ids("customrecord_swc_subpo", "name", number)
    if len(ids) != 1 or not re.fullmatch(r"[1-9][0-9]{0,19}", ids[0]):
        raise ApiError(409, "下载环境中未找到唯一的同编号子采购单，请核对来源单号")
    zid = ids[0]
    record = ns.request("GET", "customrecord_swc_subpo", zid)["data"]
    vendor = record.get("custrecord_swc_subpo_vendor") if isinstance(record, dict) else None
    customs = record.get("custrecord_swc_subpo_baoguannum") if isinstance(record, dict) else None
    if (
        not isinstance(record, dict)
        or record.get("name") != number
        or str(record.get("id")) != zid
        or not isinstance(vendor, dict)
        or vendor.get("refName") != supplier
        or not isinstance(customs, dict)
        or customs.get("refName") != declaration
    ):
        raise ApiError(409, "下载环境的单号、供应商或报关单与审核任务不一致，未下载文件")
    data = fetch_json(
        ns,
        settings.subpo_contract_script,
        settings.subpo_contract_deploy,
        {"zid": zid},
        "子采购合同",
        limit=10 * 1024 * 1024,
    )
    try:
        if not isinstance(data, dict) or str(data.get("zid")) != zid:
            raise ValueError("unexpected record")
        pdf = decode_pdf(data.get("contentBase64"))
    except (ValueError, UnicodeError, binascii.Error):
        raise ApiError(502, "子采购合同返回的记录或 PDF 不完整，未保存文件") from None
    return {
        "ns_id": zid,
        "environment": settings.account,
        "filename": f"subpo-contract-{zid}.pdf",
        "content": pdf,
    }

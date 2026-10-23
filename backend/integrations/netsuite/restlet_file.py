"""只读 RESTlet 文件下载的共用步骤：限长读取 JSON 响应、解码并校验 PDF。

子采购合同与报关资料共用；业务身份核对由各自调用方在请求文件前完成。
"""

import base64
import json

import httpx

from backend.core.errors import ApiError

RESPONSE_LIMIT = 30 * 1024 * 1024
PDF_LIMIT = 7 * 1024 * 1024


def fetch_json(ns, script, deploy, params, label, *, limit=RESPONSE_LIMIT):
    """GET 指定 RESTlet，返回解析后的对象；兼容 NS 把 JSON 再包一层字符串返回。"""
    url = f"https://{ns.settings.account}.restlets.api.netsuite.com/app/site/hosting/restlet.nl"
    try:
        with ns.client.stream(
            "GET",
            url,
            params={"script": script, "deploy": deploy, **params},
            headers={"Authorization": f"Bearer {ns.token()}", "Accept": "application/json"},
            timeout=90,
            follow_redirects=False,
        ) as response:
            if not response.is_success:
                raise ApiError(502, f"{label}下载失败（HTTP {response.status_code}），请核对接口权限")
            chunks, size = [], 0
            for chunk in response.iter_bytes():
                size += len(chunk)
                if size > limit:
                    raise ApiError(502, f"{label}响应超过 {limit // 1024 // 1024} MB，未保存截断文件")
                chunks.append(chunk)
        data = json.loads(b"".join(chunks))
        return json.loads(data) if isinstance(data, str) else data
    except httpx.HTTPError:
        raise ApiError(502, f"{label}下载连接失败或超时，请稍后重试") from None
    except (ValueError, UnicodeError):
        raise ApiError(502, f"{label}返回的内容不是有效 JSON，未保存文件") from None


def decode_pdf(encoded):
    """解码 base64 PDF；不完整、过大或不是 PDF 时抛 ValueError，由调用方转为业务错误。"""
    if not isinstance(encoded, str):
        raise ValueError("missing PDF")
    pdf = base64.b64decode(encoded, validate=True)
    if len(pdf) > PDF_LIMIT or not pdf.startswith(b"%PDF-") or b"%%EOF" not in pdf[-1024:]:
        raise ValueError("invalid PDF")
    return pdf

"""回写字段许可与快照比较规则。"""

import hashlib
import json
import re
import time

from backend.core.errors import ApiError


def millis():
    return int(time.time() * 1000)


def encode(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def fingerprint(value):
    def clean(v):
        if isinstance(v, dict):
            return {k: clean(v[k]) for k in sorted(v) if k != "links"}
        if isinstance(v, list):
            return [clean(item) for item in v]
        return v

    return hashlib.sha256(encode(clean(value)).encode()).hexdigest()


class WritebackPolicy:
    def __init__(self, settings, ns):
        self.settings, self.ns = settings, ns

    def validate(self, body):
        if not isinstance(body, dict) or body.get("operation") not in ("create", "update"):
            raise ApiError(400, "请选择创建或更新")
        record_type, operation, payload = body.get("type"), body["operation"], body.get("payload")
        record_id = body.get("id") if operation == "update" else None
        self.ns.validate(record_type, record_id)
        if operation == "update" and (
            not isinstance(record_id, str) or not re.fullmatch(r"[0-9]{1,40}", record_id)
        ):
            raise ApiError(400, "更新必须指定 NS Internal ID")
        if not isinstance(payload, dict) or not payload:
            raise ApiError(400, "写入内容必须是非空 JSON 对象")
        allowed = self.settings.write_fields.get(record_type, [])
        if any(
            k not in allowed or k in ("id", "links", "__proto__", "constructor", "prototype") for k in payload
        ):
            raise ApiError(400, "包含未允许写入的字段，请先配置该记录的字段白名单")
        if operation == "update" and "externalId" in payload:
            raise ApiError(400, "更新不允许修改 externalId")
        if operation == "create" and (
            not isinstance(payload.get("externalId"), str)
            or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", payload["externalId"])
        ):
            raise ApiError(400, "创建必须提供稳定且唯一的 externalId（字母、数字、下划线或短横线）")
        try:
            if len(encode(payload).encode()) > 128 * 1024:
                raise ValueError()
        except (ValueError, TypeError, RecursionError):
            raise ApiError(400, "写入内容无效或过大") from None

"""企业微信客户群只读接口；凭证和令牌仅在服务端，目录持久化由业务模块管理。"""

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from hashlib import sha256
from threading import Lock

import httpx

from backend.core.errors import ApiError

BASE_URL = "https://qyapi.weixin.qq.com/cgi-bin/"


class WeComError(ApiError):
    def __init__(self, code, message):
        super().__init__(502, message)
        self.code = code


class WeComGroups:
    def __init__(self, settings, client=None):
        self.settings = settings
        self.client = client or httpx.Client(timeout=20, follow_redirects=False, trust_env=False)
        self._token = None
        self._token_lock = Lock()

    def close(self):
        self.client.close()

    def _credentials(self):
        corpid, secret = self.settings.wecom_corp_id, self.settings.wecom_secret
        if self.settings.wecom_connection_file:
            try:
                data = json.loads(self.settings.wecom_connection_file.read_text(encoding="utf-8-sig"))
                if not isinstance(data, dict):
                    raise ValueError()
                corpid, secret = data.get("corpid"), data.get("secret")
            except (OSError, ValueError):
                raise ApiError(503, "企微连接配置无法读取，请联系管理员检查配置文件") from None
        if (
            not isinstance(corpid, str)
            or not corpid.strip()
            or not isinstance(secret, str)
            or not secret.strip()
        ):
            raise ApiError(503, "企微查询尚未配置，请管理员配置企业 ID 和客户联系 Secret")
        return corpid.strip(), secret.strip()

    def _request(self, method, path, *, params, body=None):
        try:
            with self.client.stream(method, BASE_URL + path, params=params, json=body) as response:
                if not response.is_success:
                    raise ApiError(502, f"企微查询失败（HTTP {response.status_code}），请稍后重试")
                chunks, size = [], 0
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > 8 * 1024 * 1024:
                        raise ApiError(502, "企微返回数据过大，请缩小应用可见范围")
                    chunks.append(chunk)
            data = json.loads(b"".join(chunks))
        except httpx.HTTPError:
            raise ApiError(502, "无法连接企微，请检查网络后重试") from None
        except (ValueError, UnicodeError):
            raise ApiError(502, "企微返回的数据格式异常，请稍后重试") from None
        if not isinstance(data, dict) or type(data.get("errcode")) is not int:
            raise ApiError(502, "企微返回的数据格式异常，请稍后重试")
        return data

    @staticmethod
    def _check(data):
        code = data["errcode"]
        if code == 0:
            return data
        reason = {
            60011: "当前应用无权读取该客户群，请检查群主可见范围",
            60020: "调用服务器出口 IP 未加入企微应用的可信 IP",
            48002: "应用缺少客户联系权限，或群主不在可见范围内",
            48009: "应用缺少客户联系权限，或群主不在可见范围内",
            301002: "群主客户联系权限不可用，请检查应用可见范围及授权",
            81017: "企微应用可见范围过大，请管理员缩小到采购群主所在范围",
            45009: "企微查询频率已达上限，请稍后重试",
            41063: "该客户群不存在或当前应用无权访问，请重新查询选择",
            40014: "企微访问凭证无效，请检查连接配置",
            42001: "企微访问凭证过期，请重新查询",
            40001: "企微凭证校验失败，请检查企业 ID 和 Secret",
        }.get(code, "请检查企微应用配置、客户联系权限及群主可见范围")
        # 不回传 errmsg，其中可能包含凭证或上游请求地址。
        raise WeComError(code, f"企微查询失败（{code}）：{reason}")

    def token(self):
        with self._token_lock:
            corpid, secret = self._credentials()
            if self._token and self._token[1] > time.monotonic() and self._token[2:] == (corpid, secret):
                return self._token[0]
            data = self._check(
                self._request("GET", "gettoken", params={"corpid": corpid, "corpsecret": secret})
            )
            token, expires = data.get("access_token"), data.get("expires_in")
            if not isinstance(token, str) or not token or type(expires) is not int or expires <= 0:
                raise ApiError(502, "企微返回的访问凭证格式异常")
            self._token = token, time.monotonic() + max(1, expires - 120), corpid, secret
            return token

    def corp_id(self):
        return self._credentials()[0]

    def token_for(self, corp_id):
        token = self.token()
        with self._token_lock:
            if not self._token or self._token[0] != token or self._token[2] != corp_id:
                raise ApiError(409, "企微企业凭证已变化，请核实原企业配置")
        return token

    def _read(self, path, body, expected_corp=None):
        for attempt in range(2):
            token = self.token_for(expected_corp) if expected_corp else self.token()
            data = self._request("POST", path, params={"access_token": token}, body=body)
            if attempt == 0 and data["errcode"] in (40014, 42001):
                with self._token_lock:
                    if self._token and self._token[0] == token:
                        self._token = None
                continue
            return self._check(data)

    def group(self, chat_id, expected_corp=None):
        data = self._read(
            "externalcontact/groupchat/get", {"chat_id": chat_id, "need_name": 1}, expected_corp
        )
        group = data.get("group_chat")
        if not isinstance(group, dict) or group.get("chat_id") != chat_id:
            raise ApiError(502, "企微返回的客户群身份不一致，请重新查询")
        owner, name, members = group.get("owner"), group.get("name"), group.get("member_list")
        if (
            not isinstance(owner, str)
            or not owner
            or not isinstance(name, str)
            or not isinstance(members, list)
        ):
            raise ApiError(502, "企微返回的群信息不完整，请重新查询")
        employee = next(
            (
                m.get("name")
                for m in members
                if isinstance(m, dict)
                and m.get("type") == 1
                and m.get("userid") == owner
                and isinstance(m.get("name"), str)
                and m["name"]
            ),
            owner,
        )
        created = group.get("create_time")
        return {
            "groupName": name.strip() or "未命名客户群",
            "chatId": chat_id,
            "employee": employee,
            "userid": owner,
            "memberCount": len(members),
            "createdAt": created if type(created) is int and 0 <= created <= 253402300799 else None,
        }

    def _visible_group(self, chat_id, expected_corp):
        try:
            return self.group(chat_id, expected_corp)
        except WeComError as error:
            # 列表可能短暂包含已失去访问权限或解散的群；明确计入未读取数量。
            if error.code in (60011, 41063):
                return None
            raise

    def directory_scope(self):
        # 只向业务层暴露不可逆的范围标识，不将 Secret 写入目录数据库。
        return sha256(json.dumps(self._credentials(), ensure_ascii=False).encode()).hexdigest()

    def groups(self, *, progress=None, expected_scope=None):
        scope = self._credentials()
        if expected_scope is not None and self.directory_scope() != expected_scope:
            raise ApiError(409, "企微连接配置已变化，请重新查询")
        result = self._load_groups(scope, progress)
        if self._credentials() != scope:
            raise ApiError(409, "企微连接配置已变化，请重新查询")
        return result

    def _load_groups(self, scope, progress=None):
        ids, seen, cursors, cursor = [], set(), set(), ""
        for _ in range(100):
            data = self._read(
                "externalcontact/groupchat/list",
                {"status_filter": 0, "cursor": cursor, "limit": 100},
                scope[0],
            )
            rows = data.get("group_chat_list")
            if not isinstance(rows, list):
                raise ApiError(502, "企微返回的客户群列表格式异常")
            for row in rows:
                chat_id = row.get("chat_id") if isinstance(row, dict) else None
                if not isinstance(chat_id, str) or not chat_id:
                    raise ApiError(502, "企微返回的客户群列表格式异常")
                if chat_id not in seen:
                    seen.add(chat_id)
                    ids.append(chat_id)
            if progress:
                progress("listing", len(ids), 0, None)
            if len(ids) > 5000:
                raise ApiError(502, "可见客户群超过查询上限，请缩小企微应用可见范围")
            cursor = data.get("next_cursor", "")
            if not isinstance(cursor, str) or cursor in cursors:
                raise ApiError(502, "企微分页数据异常，未使用不完整的群清单")
            if not cursor:
                break
            cursors.add(cursor)
        else:
            raise ApiError(502, "企微分页超过查询上限，请缩小应用可见范围")
        rows = []
        if progress:
            progress("details", len(ids), 0, len(ids))
        with ThreadPoolExecutor(max_workers=6) as pool:
            futures = [pool.submit(self._visible_group, chat_id, scope[0]) for chat_id in ids]
            try:
                for future in as_completed(futures):
                    rows.append(future.result())
                    if progress:
                        progress("details", len(ids), len(rows), len(ids))
            except Exception:
                # 出错后取消尚未开始的请求，避免继续全量查询；已开始的请求由客户端超时收口。
                for future in futures:
                    future.cancel()
                raise
        if self._credentials() != scope:
            raise ApiError(409, "企微连接配置已变化，请重新查询")
        return {
            "items": tuple(row for row in rows if row is not None),
            "unavailableCount": sum(row is None for row in rows),
        }

"""企微只读适配器：游标、凭证缓存、权限缺失和错误脱敏，不访问真实服务。"""

import json
from dataclasses import replace

import httpx
import pytest
from backend.core.config import load_settings
from backend.core.errors import ApiError
from backend.integrations.wecom import WeComGroups


def group(chat_id, *, owner="buyer1", name="采购群"):
    return {
        "errcode": 0,
        "group_chat": {
            "chat_id": chat_id,
            "name": name,
            "owner": owner,
            "create_time": 100,
            "member_list": [{"type": 1, "userid": owner, "name": "采购员"}],
        },
    }


def api(handler):
    settings = load_settings({"WECOM_CORP_ID": "test-corp", "WECOM_SECRET": "test-secret"})
    return WeComGroups(settings, httpx.Client(transport=httpx.MockTransport(handler)))


def test_cursor_cache_refresh_duplicate_names_and_fresh_detail():
    calls = []
    owner = ["buyer1"]

    def handler(request):
        calls.append(request.url.path)
        if request.url.path.endswith("/gettoken"):
            assert request.url.params["corpsecret"] == "test-secret"
            return httpx.Response(200, json={"errcode": 0, "access_token": "test-token", "expires_in": 7200})
        assert request.url.params["access_token"] == "test-token"
        body = json.loads(request.content)
        if request.url.path.endswith("/list"):
            return httpx.Response(
                200,
                json={
                    "errcode": 0,
                    "group_chat_list": [{"chat_id": "wr_1" if not body["cursor"] else "wr_2"}],
                    "next_cursor": "next" if not body["cursor"] else "",
                },
            )
        return httpx.Response(200, json=group(body["chat_id"], owner=owner[0]))

    client = api(handler)
    try:
        first = client.groups()
        assert len(first["items"]) == 2 and first["unavailableCount"] == 0
        assert {r["groupName"] for r in first["items"]} == {"采购群"}
        before = len(calls)
        assert client.groups() == first and len(calls) == before
        owner[0] = "new_owner"
        assert client.group("wr_1")["userid"] == "new_owner"
        client.groups(refresh=True)
        assert calls.count("/cgi-bin/gettoken") == 1
        assert calls.count("/cgi-bin/externalcontact/groupchat/list") == 4
    finally:
        client.close()


def test_expired_token_refreshes_once():
    tokens, reads = [], []

    def handler(request):
        if request.url.path.endswith("/gettoken"):
            tokens.append(1)
            return httpx.Response(
                200, json={"errcode": 0, "access_token": f"token-{len(tokens)}", "expires_in": 7200}
            )
        reads.append(request.url.params["access_token"])
        return httpx.Response(200, json={"errcode": 42001} if len(reads) == 1 else group("wr_1"))

    client = api(handler)
    try:
        assert client.group("wr_1")["chatId"] == "wr_1"
        assert reads == ["token-1", "token-2"]
    finally:
        client.close()


def test_unavailable_groups_are_counted_but_network_errors_fail():
    fail = [False]

    def handler(request):
        if request.url.path.endswith("/gettoken"):
            return httpx.Response(200, json={"errcode": 0, "access_token": "token", "expires_in": 7200})
        if request.url.path.endswith("/list"):
            return httpx.Response(
                200,
                json={
                    "errcode": 0,
                    "group_chat_list": [{"chat_id": "wr_1"}, {"chat_id": "wr_2"}],
                    "next_cursor": "",
                },
            )
        body = json.loads(request.content)
        if body["chat_id"] == "wr_2":
            if fail[0]:
                raise httpx.ReadTimeout("secret url", request=request)
            return httpx.Response(200, json={"errcode": 60011, "errmsg": "test-secret"})
        return httpx.Response(200, json=group("wr_1"))

    client = api(handler)
    try:
        result = client.groups()
        assert len(result["items"]) == 1 and result["unavailableCount"] == 1
        fail[0] = True
        with pytest.raises(ApiError) as error:
            client.groups(refresh=True)
        assert "secret" not in error.value.message
    finally:
        client.close()


@pytest.mark.parametrize(
    "response",
    [
        {"errcode": 60020, "errmsg": "test-secret token=private"},
        {"errcode": 0, "group_chat": {"chat_id": "wrong"}},
        [],
        {"errcode": "0"},
    ],
)
def test_malformed_or_denied_response_fails_safely(response):
    def handler(request):
        if request.url.path.endswith("/gettoken"):
            return httpx.Response(200, json={"errcode": 0, "access_token": "token", "expires_in": 7200})
        return httpx.Response(200, json=response)

    client = api(handler)
    try:
        with pytest.raises(ApiError) as error:
            client.group("wr_1")
        assert error.value.status == 502
        assert "test-secret" not in error.value.message and "private" not in error.value.message
    finally:
        client.close()


def test_repeated_cursor_is_rejected():
    def handler(request):
        if request.url.path.endswith("/gettoken"):
            return httpx.Response(200, json={"errcode": 0, "access_token": "token", "expires_in": 7200})
        return httpx.Response(200, json={"errcode": 0, "group_chat_list": [], "next_cursor": "same"})

    client = api(handler)
    try:
        with pytest.raises(ApiError, match="分页数据异常"):
            client.groups()
    finally:
        client.close()


def test_missing_and_local_file_credentials(tmp_path):
    settings = load_settings({})
    client = WeComGroups(settings)
    try:
        with pytest.raises(ApiError) as error:
            client.token()
        assert error.value.status == 503
    finally:
        client.close()
    path = tmp_path / "wecom.json"
    path.write_text(json.dumps({"corpid": "local-corp", "secret": "local-secret"}))
    settings = replace(settings, wecom_connection_file=path)

    def handler(request):
        assert request.url.params["corpid"] == "local-corp"
        assert request.url.params["corpsecret"] == "local-secret"
        return httpx.Response(200, json={"errcode": 0, "access_token": "token", "expires_in": 7200})

    client = WeComGroups(settings, httpx.Client(transport=httpx.MockTransport(handler)))
    try:
        assert client.token() == "token"
        assert "local-secret" not in repr(settings)
    finally:
        client.close()

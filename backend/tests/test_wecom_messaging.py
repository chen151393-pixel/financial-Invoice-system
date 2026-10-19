"""基于官方接口结构的适配测试，不访问真实企微。"""

import json

import httpx
import pytest
from backend.core.errors import ApiError
from backend.integrations.wecom_messaging import WeComMessaging, WeComRejected
from backend.tests.test_wecom_groups import api


def client(handler):
    def transport(request):
        if request.url.path.endswith("/gettoken"):
            return httpx.Response(
                200, json={"errcode": 0, "access_token": "hidden-token", "expires_in": 7200}
            )
        return handler(request)

    return WeComMessaging(api(transport))


def test_multipart_and_single_target_payload():
    calls = []

    def handler(request):
        calls.append(request)
        if request.url.path.endswith("/upload"):
            assert request.url.params["type"] == "file"
            assert b'name="media"' in request.content and b"%PDF-test" in request.content
            return httpx.Response(200, json={"errcode": 0, "media_id": "media"})
        body = json.loads(request.content)
        assert body["chat_type"] == "group" and body["chat_id_list"] == ["target"]
        assert body["sender"] == "owner" and body["text"] == {"content": "请开票"}
        assert body["attachments"] == [{"msgtype": "file", "file": {"media_id": "media"}}]
        return httpx.Response(200, json={"errcode": 0, "msgid": "msg", "fail_list": []})

    channel = client(handler)
    media = channel.upload("test-corp", "contract.pdf", b"%PDF-test")
    assert channel.create("test-corp", "target", "owner", "请开票", [media]) == "msg"
    assert len(calls) == 2


@pytest.mark.parametrize("kind", ["timeout", "auth", "invalid", "http"])
def test_create_never_retries_or_leaks_token(kind):
    calls = []

    def handler(request):
        calls.append(1)
        if kind == "timeout":
            raise httpx.ReadTimeout("hidden-token", request=request)
        if kind == "auth":
            return httpx.Response(200, json={"errcode": 42001, "errmsg": "hidden-token"})
        if kind == "http":
            return httpx.Response(500)
        return httpx.Response(200, content=b"not json")

    channel = client(handler)
    with pytest.raises(ApiError) as error:
        channel.create("test-corp", "target", "owner", "message", ["media"])
    assert len(calls) == 1 and "hidden-token" not in error.value.message


def test_target_rejection_keeps_channel_id():
    channel = client(
        lambda _: httpx.Response(200, json={"errcode": 0, "msgid": "msg", "fail_list": ["target"]})
    )
    with pytest.raises(WeComRejected) as error:
        channel.create("test-corp", "target", "owner", "message", ["media"])
    assert error.value.msgid == "msg"


def test_all_receipt_pages_and_duplicate_cursor():
    calls = []

    def handler(request):
        body = json.loads(request.content)
        calls.append(body)
        return httpx.Response(
            200,
            json={
                "errcode": 0,
                "send_list": [{"chat_id": "other" if not body["cursor"] else "target"}],
                "next_cursor": "next" if not body["cursor"] else "",
            },
        )

    channel = client(handler)
    assert [r["chat_id"] for r in channel.results("test-corp", "msg", "owner")] == ["other", "target"]
    assert all(call["msgid"] == "msg" and call["userid"] == "owner" for call in calls)
    broken = client(
        lambda _: httpx.Response(200, json={"errcode": 0, "send_list": [], "next_cursor": "same"})
    )
    with pytest.raises(ApiError, match="分页"):
        broken.results("test-corp", "msg", "owner")


def test_corp_change_does_not_reuse_previous_token():
    channel = client(lambda _: httpx.Response(200, json={"errcode": 0, "send_list": []}))
    channel.groups.token_for("test-corp")
    channel.groups.settings.wecom_corp_id = "other-corp"
    with pytest.raises(ApiError, match="企业凭证"):
        channel.results("test-corp", "msg", "owner")

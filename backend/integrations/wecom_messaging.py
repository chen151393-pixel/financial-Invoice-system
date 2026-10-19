"""企微客户群群发适配。创建请求只执行一次；传输异常绝不自动重试。"""

import httpx

from backend.core.errors import ApiError

from .wecom import BASE_URL


class WeComRejected(ApiError):
    def __init__(self, code, msgid=None):
        self.code = str(code)
        self.msgid = msgid
        super().__init__(502, f"企微明确拒绝请求（{code}），请核实权限与渠道限制")


class WeComMessaging:
    def __init__(self, groups):
        self.groups = groups

    def corp_id(self):
        return self.groups.corp_id()

    def group(self, corp_id, chat_id):
        return self.groups.group(chat_id, expected_corp=corp_id)

    def upload(self, corp_id, filename, content):
        token = self.groups.token_for(corp_id)
        try:
            response = self.groups.client.post(
                BASE_URL + "media/upload",
                params={"access_token": token, "type": "file"},
                files={"media": (filename, content, "application/pdf")},
            )
            if not response.is_success or len(response.content) > 1024 * 1024:
                raise ApiError(502, "企微合同上传失败，未创建群发")
            data = response.json()
        except (httpx.HTTPError, ValueError):
            raise ApiError(502, "企微合同上传失败，未创建群发") from None
        self._check(data)
        media_id = data.get("media_id")
        if not isinstance(media_id, str) or not media_id:
            raise ApiError(502, "企微未返回合同素材编号，未创建群发")
        return media_id

    @staticmethod
    def _check(data):
        if not isinstance(data, dict) or type(data.get("errcode")) is not int:
            raise ApiError(502, "企微响应格式异常，请核实发送结果")
        if data["errcode"] != 0:
            raise WeComRejected(data["errcode"])

    def create(self, corp_id, chat_id, sender, message, media_ids):
        # 不使用 _read 的令牌刷新重试；缺失目标时拒绝，绝不退化为群主全部客户群。
        if not chat_id or not sender or not media_ids:
            raise ApiError(400, "企微目标群、群主和合同不能为空")
        token = self.groups.token_for(corp_id)
        data = self.groups._request(
            "POST",
            "externalcontact/add_msg_template",
            params={"access_token": token},
            body={
                "chat_type": "group",
                "chat_id_list": [chat_id],
                "sender": sender,
                "text": {"content": message},
                "attachments": [{"msgtype": "file", "file": {"media_id": item}} for item in media_ids],
            },
        )
        self._check(data)
        msgid = data.get("msgid")
        if not isinstance(msgid, str) or not msgid or len(msgid) > 190:
            raise ApiError(502, "企微响应缺少有效消息编号，结果待核实")
        # fail_list 的类型/语义仍依部署契约验收；任何非空拒绝列表均不得宣称成功。
        failures = data.get("fail_list", [])
        if (
            isinstance(failures, list)
            and all(isinstance(item, str) for item in failures)
            and chat_id in failures
        ):
            raise WeComRejected("target_rejected", msgid)
        if not isinstance(failures, list) or failures:
            raise ApiError(502, "企微返回目标拒绝或异常清单，结果待核实")
        return msgid

    def _pages(self, corp_id, path, body, key):
        result, seen, cursor = [], set(), ""
        for _ in range(100):
            data = self.groups._read(path, {**body, "limit": 100, "cursor": cursor}, corp_id)
            items = data.get(key)
            if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
                raise ApiError(502, "企微回执列表格式异常")
            result.extend(items)
            cursor = data.get("next_cursor", "")
            if not isinstance(cursor, str) or cursor in seen:
                raise ApiError(502, "企微回执分页异常，未使用不完整结果")
            if not cursor:
                return result
            seen.add(cursor)
        raise ApiError(502, "企微回执超过分页上限，需进一步核实")

    def results(self, corp_id, msgid, sender):
        return self._pages(
            corp_id,
            "externalcontact/get_groupmsg_send_result",
            {"msgid": msgid, "userid": sender},
            "send_list",
        )

    def records(self, corp_id, start, end):
        return self._pages(
            corp_id,
            "externalcontact/get_groupmsg_list_v2",
            {"chat_type": "group", "start_time": start, "end_time": end, "filter_type": 0},
            "group_msg_list",
        )

    def members(self, corp_id, msgid):
        return self._pages(corp_id, "externalcontact/get_groupmsg_task", {"msgid": msgid}, "task_list")

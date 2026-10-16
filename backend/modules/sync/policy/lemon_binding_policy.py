"""账号绑定配置与能力判断；不执行网络请求。"""

from urllib.parse import urlsplit

CALLBACK_PATH = "/api/lemon/oauth/callback"


def configuration_reason(settings):
    if not settings.lemon_app_id or not settings.lemon_app_secret:
        return "请管理员配置柠檬云应用编号和密钥"
    if (
        len(settings.lemon_app_id) > 10
        or not settings.lemon_app_id.isascii()
        or not settings.lemon_app_id.isdigit()
        or not 0 < int(settings.lemon_app_id) < 2**31
    ):
        return "柠檬云应用编号须为有效正整数"
    if settings.lemon_host not in {"https://open2.ningmengyun.com", "https://open2test.ningmengyun.com"}:
        return "柠檬云服务地址须使用官方 open2 环境"
    callback = urlsplit(settings.lemon_redirect_uri)
    if (
        callback.scheme != "https"
        or callback.username
        or callback.password
        or callback.query
        or callback.fragment
        or callback.path != CALLBACK_PATH
        or f"{callback.scheme}://{callback.netloc}" != settings.origin
    ):
        return "请管理员配置与本站同域的 HTTPS 回调地址，并在柠檬云登记"
    return ""


def mask_mobile(mobile):
    return mobile[:3] + "****" + mobile[-4:] if mobile else ""

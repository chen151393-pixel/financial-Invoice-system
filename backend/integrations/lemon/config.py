"""柠檬云 open2 记账开放平台客户端配置。

凭证全部来自环境变量（LEMON_OPEN2_*），不写死在代码中。本模块只负责读取与校验配置，
不发起任何网络请求、不读写数据库。token 等运行态凭据由 auth.TokenStore 负责持久化。

对照文档：open2 文档「全局公共参数」$ACCAPI_HOST = https://open2.ningmengyun.com（记账系统接口地址）；
「获取账号授权 → 已有账号」给出授权地址与 token 换取接口的真实路径，请填到下方 *_URL 占位。
"""

import os
import re
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[3]


@dataclass
class LemonOpen2Settings:
    host: str = "https://open2.ningmengyun.com"  # $ACCAPI_HOST 记账系统接口地址
    app_key: str = ""  # 第三方应用标识（商务注册后获得），等同 OAuth client_id
    app_secret: str = ""  # 第三方应用密钥，等同 OAuth client_secret
    asid: str = ""  # 目标账套 ID（如 200896951）；GetInvoice 按此账套返回进项票
    redirect_uri: str = ""  # 已有账号授权回调地址，需与柠檬云后台登记一致
    authorize_url: str = ""  # 引导用户授权的地址（待从「获取账号授权→已有账号」抄真实路径）
    token_url: str = ""  # 用 code/refresh_token 换取 access_token 的地址（同上来源）
    detail_url: str = ""  # 单张发票明细接口（GetInvoice 不含明细时补齐用；路径待文档确认）
    scope: str = ""  # 授权范围（如有，按文档填写）
    token_store_path: Path | None = None  # 运行态 token 持久化文件（生产应换加密存储/DB）

    @property
    def api_base(self):
        return self.host.rstrip("/")

    def missing(self):
        return [
            name
            for name, value in {
                "LEMON_OPEN2_APP_KEY": self.app_key,
                "LEMON_OPEN2_APP_SECRET": self.app_secret,
                "LEMON_OPEN2_ASID": self.asid,
                "LEMON_OPEN2_REDIRECT_URI": self.redirect_uri,
                "LEMON_OPEN2_AUTHORIZE_URL": self.authorize_url,
                "LEMON_OPEN2_TOKEN_URL": self.token_url,
                "LEMON_OPEN2_DETAIL_URL": self.detail_url,
            }.items()
            if not value
        ]


def load_lemon_open2_settings(source=None):
    env = (
        source
        if source is not None
        else {
            **dotenv_values(ROOT / ".env", interpolate=False),
            **dotenv_values(ROOT / ".env.local", interpolate=False),
            **os.environ,
        }
    )

    def get(key, default=""):
        return env.get(key) or default

    host = get("LEMON_OPEN2_HOST", "https://open2.ningmengyun.com").strip().rstrip("/")
    if not re.fullmatch(r"https://[a-zA-Z0-9.\-]+(?::\d+)?", host):
        raise ValueError("LEMON_OPEN2_HOST 须为 https 地址")
    if len(host) > 200:
        raise ValueError("LEMON_OPEN2_HOST 过长")

    app_key = get("LEMON_OPEN2_APP_KEY").strip()
    if app_key and len(app_key) > 200:
        raise ValueError("LEMON_OPEN2_APP_KEY 过长")
    app_secret = get("LEMON_OPEN2_APP_SECRET").strip()
    asid = get("LEMON_OPEN2_ASID").strip()
    if asid and not re.fullmatch(r"[0-9A-Za-z_\-]{1,40}", asid):
        raise ValueError("LEMON_OPEN2_ASID 格式错误")
    redirect_uri = get("LEMON_OPEN2_REDIRECT_URI").strip()
    if redirect_uri and not re.fullmatch(r"https://[a-zA-Z0-9.\-]+(?::\d+)?/[^\s]*", redirect_uri):
        raise ValueError("LEMON_OPEN2_REDIRECT_URI 须为 https 回调地址")

    authorize_url = get("LEMON_OPEN2_AUTHORIZE_URL").strip()
    token_url = get("LEMON_OPEN2_TOKEN_URL").strip()
    detail_url = get("LEMON_OPEN2_DETAIL_URL").strip()
    scope = get("LEMON_OPEN2_SCOPE").strip()

    token_store = Path(get("LEMON_OPEN2_TOKEN_STORE_PATH")) if get("LEMON_OPEN2_TOKEN_STORE_PATH") else None
    if token_store and not token_store.is_absolute():
        token_store = (ROOT / token_store).resolve()

    return LemonOpen2Settings(
        host=host,
        app_key=app_key,
        app_secret=app_secret,
        asid=asid,
        redirect_uri=redirect_uri,
        authorize_url=authorize_url,
        token_url=token_url,
        detail_url=detail_url,
        scope=scope,
        token_store_path=token_store,
    )

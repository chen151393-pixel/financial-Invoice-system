"""免费版明细使用独立网页会话及授权账套上下文，不借用专业版服务。"""

from contextlib import contextmanager

from backend.core.errors import ApiError

from .professional_accounts import ACCOUNT_HOST, LemonProfessionalAccounts


class LemonFreeAccounts(LemonProfessionalAccounts):
    host = "https://japi.ningmengyun.com"
    label = "免费版"

    @contextmanager
    def open(self, token):
        if self.settings.lemon_host != "https://open2.ningmengyun.com":
            raise ApiError(422, "免费版商品明细仅支持已验证的柠檬云正式环境")
        with self.session_factory() as session:
            self.request(
                session,
                ACCOUNT_HOST + "/api/AuthorizationCookie.ashx",
                "session",
                params={"token": token},
                expect_json=False,
            )
            if not session.cookies:
                raise ApiError(502, "柠檬云未建立免费版查询会话，请核实应用授权")
            payload = self.request(session, self.host + "/api/AccountSetOnlyAuth/TopInfoV2", "free_accounts")
            yield session, {}, self.account_rows(payload)

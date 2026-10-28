import json
import os
import re
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import dotenv_values

from .database import business_database_url

ROOT = Path(__file__).resolve().parents[2]


@dataclass
class Settings:
    account: str = ""
    client_id: str = field(default="", repr=False)
    certificate_id: str = field(default="", repr=False)
    private_key: Path | None = field(default=None, repr=False)
    algorithm: str = "PS256"
    scope: list[str] = field(default_factory=lambda: ["rest_webservices"])
    record_types: list[str] = field(default_factory=list)
    write_fields: dict[str, list[str]] = field(default_factory=dict)
    write_enabled: bool = False
    pl_lookup: dict = field(default_factory=dict)
    sync_date_format: str = "YYYY-MM-DD"
    sync_read_workers: int = 2
    pl_restlet_script: str = ""
    pl_restlet_deploy: str = ""
    finance_source_script: str = ""
    finance_source_deploy: str = ""
    subpo_contract_script: str = ""
    subpo_contract_deploy: str = ""
    declaration_doc_script: str = ""
    declaration_doc_deploy: str = ""
    subpo_connection_file: Path | None = field(default=None, repr=False)
    subpo_archive_root: Path | None = None
    signed_upload_root: Path = ROOT / "data" / "signed-contract-uploads"
    origin: str = "http://localhost:3000"
    admin_user: str = "admin"
    admin_password: str = field(default="", repr=False)
    # 应急管理员账号密码登录；日常使用飞书登录（docs/feishu-identity-plan.md）
    admin_password_login: bool = True
    feishu_app_id: str = ""
    feishu_app_secret: str = field(default="", repr=False)
    # 填写后飞书登录只接受该企业的账号
    feishu_tenant_key: str = ""
    service_key: str = field(default="", repr=False)
    business_database_url: str = field(default="", repr=False)
    review_unit_price_tolerance_cny: Decimal = Decimal("0.10")
    wecom_corp_id: str = field(default="", repr=False)
    wecom_secret: str = field(default="", repr=False)
    wecom_connection_file: Path | None = field(default=None, repr=False)
    wecom_send_enabled: bool = False
    wecom_group_daily_limit: int = 1
    host: str = "127.0.0.1"
    port: int = 3000
    tls_cert: str = ""
    tls_key: str = field(default="", repr=False)
    web_root: Path = ROOT / "frontend" / "dist"
    lemon_app_id: str = ""
    lemon_app_secret: str = field(default="", repr=False)
    lemon_host: str = "https://open2.ningmengyun.com"
    lemon_redirect_uri: str = ""

    @property
    def feishu_redirect_uri(self):
        """须与飞书开放平台“重定向 URL”中登记的地址完全一致。"""
        return f"{self.origin}/api/session/feishu/callback"

    @property
    def token_url(self):
        return f"https://{self.account}.suitetalk.api.netsuite.com/services/rest/auth/oauth2/v1/token"

    @property
    def record_url(self):
        return f"https://{self.account}.suitetalk.api.netsuite.com/services/rest/record/v1"

    def missing(self):
        return [
            name
            for name, value in {
                "NETSUITE_ACCOUNT_ID": self.account,
                "NETSUITE_CLIENT_ID": self.client_id,
                "NETSUITE_CERTIFICATE_ID": self.certificate_id,
                "NETSUITE_PRIVATE_KEY_PATH": self.private_key and self.private_key.is_file(),
                "NETSUITE_RECORD_TYPES": self.record_types,
            }.items()
            if not value
        ]


def load_settings(source=None):
    env = (
        source
        if source is not None
        else {
            **dotenv_values(ROOT / ".env", interpolate=False),
            **os.environ,
        }
    )

    def get(key, default=""):
        return env.get(key) or default

    review_tolerance = get("REVIEW_UNIT_PRICE_TOLERANCE_CNY", "0.10").strip()
    if not re.fullmatch(r"[0-9]+(?:\.[0-9]{1,2})?", review_tolerance):
        raise ValueError("REVIEW_UNIT_PRICE_TOLERANCE_CNY 须为非负人民币金额，最多两位小数")

    sync_date_format = get("NETSUITE_SYNC_DATE_FORMAT", "YYYY-MM-DD")
    if sync_date_format not in {"YYYY-MM-DD", "M/D/YYYY", "D/M/YYYY"}:
        raise ValueError("NETSUITE_SYNC_DATE_FORMAT 须为 YYYY-MM-DD、M/D/YYYY 或 D/M/YYYY")

    workers = get("NETSUITE_SYNC_READ_WORKERS", "2")
    if workers not in {"1", "2", "3", "4"}:
        raise ValueError("NETSUITE_SYNC_READ_WORKERS 须为 1 至 4 的整数")

    account = get("NETSUITE_ACCOUNT_ID").strip().lower().replace("_", "-")
    if account and not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", account):
        raise ValueError("NETSUITE_ACCOUNT_ID 格式错误")
    if len(account) > 100:
        raise ValueError("NETSUITE_ACCOUNT_ID 过长")
    origin = get("APP_ORIGIN", "http://localhost:3000")
    url = urlsplit(origin)
    if (
        url.scheme not in ("http", "https")
        or not url.hostname
        or url.username
        or url.password
        or url.path
        or url.query
        or url.fragment
    ):
        raise ValueError("APP_ORIGIN 必须是完整 origin，不含路径")
    if url.scheme != "https" and url.hostname not in ("localhost", "127.0.0.1", "::1"):
        raise ValueError("非本机入口必须使用 HTTPS")
    private_key = Path(get("NETSUITE_PRIVATE_KEY_PATH")) if get("NETSUITE_PRIVATE_KEY_PATH") else None
    if private_key:
        private_key = (ROOT / private_key).resolve()
        if private_key.is_relative_to(ROOT / "frontend"):
            raise ValueError("NS 私钥不能放在前端或公开目录")
    try:
        fields = json.loads(get("NETSUITE_WRITE_FIELDS", "{}"))
    except ValueError:
        raise ValueError("NETSUITE_WRITE_FIELDS 必须是 JSON 对象") from None
    if not isinstance(fields, dict) or any(
        not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,99}", key)
        or not isinstance(values, list)
        or any(not isinstance(v, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,99}", v) for v in values)
        for key, values in fields.items()
    ):
        raise ValueError("NS 写入字段配置无效")
    business_url = business_database_url(env)
    types = [v.strip() for v in get("NETSUITE_RECORD_TYPES").split(",") if v.strip()]
    if any(not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,99}", v) for v in types):
        raise ValueError("NETSUITE_RECORD_TYPES 格式错误")
    enabled = get("NETSUITE_WRITE_ENABLED", "false")
    try:
        pl_lookup = json.loads(get("NETSUITE_PL_LOOKUP", "{}"))
        if not isinstance(pl_lookup, dict):
            raise ValueError()
    except ValueError:
        raise ValueError("NETSUITE_PL_LOOKUP 必须是 JSON 对象") from None
    if enabled not in ("true", "false"):
        raise ValueError("NETSUITE_WRITE_ENABLED 必须为 true 或 false")
    if len(get("ADMIN_USERNAME", "admin")) > 190:
        raise ValueError("ADMIN_USERNAME 过长")
    pl_script = get("NETSUITE_PL_RESTLET_SCRIPT").strip()
    pl_deploy = get("NETSUITE_PL_RESTLET_DEPLOY").strip()
    finance_script = get("NETSUITE_FINANCE_SOURCE_SCRIPT").strip()
    finance_deploy = get("NETSUITE_FINANCE_SOURCE_DEPLOY").strip()
    contract_script = get("NETSUITE_SUBPO_CONTRACT_SCRIPT").strip()
    contract_deploy = get("NETSUITE_SUBPO_CONTRACT_DEPLOY").strip()
    declaration_script = get("NETSUITE_DECLARATION_DOC_SCRIPT").strip()
    declaration_deploy = get("NETSUITE_DECLARATION_DOC_DEPLOY").strip()
    archive_root = Path(get("NETSUITE_SUBPO_ARCHIVE_ROOT")) if get("NETSUITE_SUBPO_ARCHIVE_ROOT") else None
    if archive_root and not archive_root.is_absolute():
        raise ValueError("NETSUITE_SUBPO_ARCHIVE_ROOT 必须为绝对路径或 UNC 共享路径")
    for value, prefix in (
        (pl_script, "customscript"),
        (pl_deploy, "customdeploy"),
        (finance_script, "customscript"),
        (finance_deploy, "customdeploy"),
        (contract_script, "customscript"),
        (contract_deploy, "customdeploy"),
        (declaration_script, "customscript"),
        (declaration_deploy, "customdeploy"),
    ):
        if value and not re.fullmatch(rf"(?:[0-9]{{1,20}}|{prefix}_[a-zA-Z0-9_]{{1,100}})", value):
            raise ValueError("RESTlet 脚本或部署编号无效")
    if bool(finance_script) != bool(finance_deploy):
        raise ValueError("原始报关行接口的脚本和部署编号须同时填写")
    if bool(contract_script) != bool(contract_deploy):
        raise ValueError("子采购合同接口的脚本和部署编号须同时填写")
    if bool(declaration_script) != bool(declaration_deploy):
        raise ValueError("报关资料接口的脚本和部署编号须同时填写")
    password_login = get("ADMIN_PASSWORD_LOGIN_ENABLED", "true").lower()
    if password_login not in {"true", "false"}:
        raise ValueError("ADMIN_PASSWORD_LOGIN_ENABLED 须为 true 或 false")
    feishu_app_id = get("FEISHU_APP_ID").strip()
    if feishu_app_id and not re.fullmatch(r"cli_[A-Za-z0-9]{1,64}", feishu_app_id):
        raise ValueError("FEISHU_APP_ID 格式错误，应以 cli_ 开头")
    if bool(feishu_app_id) != bool(get("FEISHU_APP_SECRET")):
        raise ValueError("FEISHU_APP_ID 与 FEISHU_APP_SECRET 须同时填写")
    wecom_send = get("WECOM_SEND_ENABLED", "false").lower()
    wecom_limit = get("WECOM_GROUP_DAILY_LIMIT", "1")
    if wecom_send not in {"true", "false"}:
        raise ValueError("WECOM_SEND_ENABLED 须为 true 或 false")
    if not wecom_limit.isdigit() or not 1 <= int(wecom_limit) <= 31:
        raise ValueError("WECOM_GROUP_DAILY_LIMIT 须为 1 至 31 的整数")
    return Settings(
        account=account,
        client_id=get("NETSUITE_CLIENT_ID"),
        certificate_id=get("NETSUITE_CERTIFICATE_ID"),
        private_key=private_key,
        algorithm=get("NETSUITE_JWT_ALGORITHM", "PS256"),
        scope=re.split(r"[ ,]+", get("NETSUITE_SCOPE", "rest_webservices")),
        record_types=types,
        write_fields=fields,
        write_enabled=enabled == "true",
        pl_lookup=pl_lookup,
        sync_date_format=sync_date_format,
        sync_read_workers=int(workers),
        pl_restlet_script=pl_script,
        pl_restlet_deploy=pl_deploy,
        finance_source_script=finance_script,
        finance_source_deploy=finance_deploy,
        subpo_contract_script=contract_script,
        subpo_contract_deploy=contract_deploy,
        declaration_doc_script=declaration_script,
        declaration_doc_deploy=declaration_deploy,
        subpo_archive_root=archive_root,
        signed_upload_root=(
            ROOT / get("SIGNED_CONTRACT_UPLOAD_ROOT", "data/signed-contract-uploads")
        ).resolve(),
        subpo_connection_file=(ROOT / get("NETSUITE_SUBPO_CONNECTION_FILE")).resolve()
        if get("NETSUITE_SUBPO_CONNECTION_FILE")
        else None,
        origin=origin,
        admin_user=get("ADMIN_USERNAME", "admin"),
        admin_password=get("ADMIN_PASSWORD"),
        admin_password_login=password_login == "true",
        feishu_app_id=feishu_app_id,
        feishu_app_secret=get("FEISHU_APP_SECRET"),
        feishu_tenant_key=get("FEISHU_TENANT_KEY").strip(),
        service_key=get("SERVICE_API_KEY"),
        business_database_url=business_url,
        review_unit_price_tolerance_cny=Decimal(review_tolerance),
        wecom_corp_id=get("WECOM_CORP_ID"),
        wecom_send_enabled=wecom_send == "true",
        wecom_group_daily_limit=int(wecom_limit),
        wecom_secret=get("WECOM_SECRET"),
        wecom_connection_file=(ROOT / get("WECOM_CONNECTION_FILE")).resolve()
        if get("WECOM_CONNECTION_FILE")
        else None,
        host=get("HOST", "127.0.0.1"),
        port=int(get("PORT", "3000")),
        tls_cert=get("TLS_CERT_PATH"),
        tls_key=get("TLS_KEY_PATH"),
        lemon_app_id=get("LEMON_OPEN2_APP_KEY").strip(),
        lemon_app_secret=get("LEMON_OPEN2_APP_SECRET"),
        lemon_host=get("LEMON_OPEN2_HOST", "https://open2.ningmengyun.com").rstrip("/"),
        lemon_redirect_uri=get("LEMON_OPEN2_REDIRECT_URI").strip(),
    )

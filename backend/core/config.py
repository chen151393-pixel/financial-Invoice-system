import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import dotenv_values
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

from .business_database import business_database_url

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
    pl_restlet_script: str = ""
    pl_restlet_deploy: str = ""
    finance_source_script: str = ""
    finance_source_deploy: str = ""
    subpo_contract_script: str = ""
    subpo_contract_deploy: str = ""
    subpo_connection_file: Path | None = field(default=None, repr=False)
    subpo_archive_root: Path | None = None
    origin: str = "http://localhost:3000"
    admin_user: str = "admin"
    admin_password: str = field(default="", repr=False)
    local_browser_access: bool = False
    service_key: str = field(default="", repr=False)
    database_url: str = field(default="", repr=False)
    business_database_url: str = field(default="", repr=False)
    wecom_corp_id: str = field(default="", repr=False)
    wecom_secret: str = field(default="", repr=False)
    wecom_connection_file: Path | None = field(default=None, repr=False)
    host: str = "127.0.0.1"
    port: int = 3000
    tls_cert: str = ""
    tls_key: str = field(default="", repr=False)
    web_root: Path = ROOT / "dist" / "web"

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
            **dotenv_values(ROOT / ".env.local", interpolate=False),
            **os.environ,
        }
    )

    def get(key, default=""):
        return env.get(key) or default

    sync_date_format = get("NETSUITE_SYNC_DATE_FORMAT", "YYYY-MM-DD")
    if sync_date_format not in {"YYYY-MM-DD", "M/D/YYYY", "D/M/YYYY"}:
        raise ValueError("NETSUITE_SYNC_DATE_FORMAT 须为 YYYY-MM-DD、M/D/YYYY 或 D/M/YYYY")

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
    local_access = get("LOCAL_BROWSER_ACCESS", "false")
    if local_access not in ("true", "false"):
        raise ValueError("LOCAL_BROWSER_ACCESS 必须为 true 或 false")
    if local_access == "true" and (
        url.hostname not in ("localhost", "127.0.0.1", "::1")
        or get("HOST", "127.0.0.1") not in ("localhost", "127.0.0.1", "::1")
    ):
        raise ValueError("免登录浏览器入口只允许本机地址与本机监听")
    private_key = Path(get("NETSUITE_PRIVATE_KEY_PATH")) if get("NETSUITE_PRIVATE_KEY_PATH") else None
    if private_key:
        private_key = (ROOT / private_key).resolve()
        if any(private_key.is_relative_to(ROOT / folder) for folder in ("public", "dist", "web", "app")):
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
    # 正式运行只读业务库配置；旧连接仅供显式隔离测试及历史库迁移。
    db_url = business_url or get("DATABASE_URL")
    if not db_url and get("DATABASE_PATH"):
        raise ValueError("DATABASE_PATH 属于旧 Node 后端，请设置业务MySQL；旧数据不会自动迁移")
    if db_url:
        try:
            parsed = make_url(db_url)
            if parsed.drivername not in ("mysql+pymysql", "sqlite") or not parsed.database:
                raise ValueError()
            if parsed.drivername == "mysql+pymysql" and (not parsed.host or not parsed.username):
                raise ValueError()
            if parsed.drivername == "sqlite":
                db_file = (ROOT / parsed.database).resolve()
                if any(db_file.is_relative_to(ROOT / name) for name in ("public", "dist", "web", "app")):
                    raise ValueError()
                parsed = parsed.set(database=str(db_file))
            else:
                parsed = parsed.update_query_dict({"charset": "utf8mb4"})
            db_url = parsed.render_as_string(hide_password=False)
        except (ValueError, TypeError, ArgumentError):
            raise ValueError("DATABASE_URL 仅供历史迁移及隔离测试，须为MySQL或非公开目录的SQLite") from None
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
    ):
        if value and not re.fullmatch(rf"(?:[0-9]{{1,20}}|{prefix}_[a-zA-Z0-9_]{{1,100}})", value):
            raise ValueError("RESTlet 脚本或部署编号无效")
    if bool(finance_script) != bool(finance_deploy):
        raise ValueError("原始报关行接口的脚本和部署编号须同时填写")
    if bool(contract_script) != bool(contract_deploy):
        raise ValueError("子采购合同接口的脚本和部署编号须同时填写")
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
        pl_restlet_script=pl_script,
        pl_restlet_deploy=pl_deploy,
        finance_source_script=finance_script,
        finance_source_deploy=finance_deploy,
        subpo_contract_script=contract_script,
        subpo_contract_deploy=contract_deploy,
        subpo_archive_root=archive_root,
        subpo_connection_file=(ROOT / get("NETSUITE_SUBPO_CONNECTION_FILE")).resolve()
        if get("NETSUITE_SUBPO_CONNECTION_FILE")
        else None,
        origin=origin,
        admin_user=get("ADMIN_USERNAME", "admin"),
        admin_password=get("ADMIN_PASSWORD"),
        local_browser_access=local_access == "true",
        service_key=get("SERVICE_API_KEY"),
        database_url=db_url,
        business_database_url=business_url,
        wecom_corp_id=get("WECOM_CORP_ID"),
        wecom_secret=get("WECOM_SECRET"),
        wecom_connection_file=(ROOT / get("WECOM_CONNECTION_FILE")).resolve()
        if get("WECOM_CONNECTION_FILE")
        else None,
        host=get("HOST", "127.0.0.1"),
        port=int(get("PORT", "3000")),
        tls_cert=get("TLS_CERT_PATH"),
        tls_key=get("TLS_KEY_PATH"),
    )

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import dotenv_values
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

from .business_database import business_database_url, ensure_separate_database

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
    origin: str = "http://localhost:3000"
    admin_user: str = "admin"
    admin_password: str = field(default="", repr=False)
    local_browser_access: bool = False
    service_key: str = field(default="", repr=False)
    database_url: str = field(default="sqlite:///./data/ns-python.sqlite", repr=False)
    business_database_url: str = field(default="", repr=False)
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
    db_url = get("DATABASE_URL", "sqlite:///./data/ns-python.sqlite")
    if not get("DATABASE_URL") and get("DATABASE_PATH"):
        raise ValueError("DATABASE_PATH 属于旧 Node 后端，请设置新的 DATABASE_URL；旧数据不会自动迁移")
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
        raise ValueError(
            "DATABASE_URL 必须指向 MySQL（mysql+pymysql）或本地 SQLite，不能放在公开目录"
        ) from None
    business_url = business_database_url(env)
    ensure_separate_database(db_url, business_url)
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
        origin=origin,
        admin_user=get("ADMIN_USERNAME", "admin"),
        admin_password=get("ADMIN_PASSWORD"),
        local_browser_access=local_access == "true",
        service_key=get("SERVICE_API_KEY"),
        database_url=db_url,
        business_database_url=business_url,
        host=get("HOST", "127.0.0.1"),
        port=int(get("PORT", "3000")),
        tls_cert=get("TLS_CERT_PATH"),
        tls_key=get("TLS_KEY_PATH"),
    )

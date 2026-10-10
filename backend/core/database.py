"""数据库连接：引擎工厂、业务 MySQL 连接配置与只读检查；不包含业务表与业务 SQL。"""

from pathlib import Path

from sqlalchemy import create_engine, event, inspect
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import ArgumentError, SQLAlchemyError


def make_engine(database_url):
    url = make_url(database_url)
    if url.drivername not in ("sqlite", "mysql+pymysql"):
        raise ValueError("数据库仅支持 MySQL 8.0 / PyMySQL 或本地 SQLite")
    if url.drivername == "sqlite":
        if url.database and url.database != ":memory:":
            Path(url.database).parent.mkdir(parents=True, exist_ok=True)
        engine = create_engine(
            url, connect_args={"check_same_thread": False, "timeout": 10}, hide_parameters=True
        )

        @event.listens_for(engine, "connect")
        def setup_sqlite(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=FULL")

        return engine
    return create_engine(
        url,
        pool_pre_ping=True,
        pool_recycle=1800,
        hide_parameters=True,
        connect_args={"connect_timeout": 10, "read_timeout": 30, "write_timeout": 30},
        isolation_level="READ COMMITTED",
    )


BUSINESS_TABLES = (
    "purchase_orders",
    "purchase_order_lines",
    "customs_declarations",
    "customs_declaration_lines",
    "invoices",
    "invoice_lines",
)


def business_database_url(env):
    """分项密码直接传给URL构造器，避免特殊字符被误解为连接串语法。"""
    raw = env.get("BUSINESS_DATABASE_URL") or ""
    user = env.get("BUSINESS_MYSQL_USER") or ""
    if not raw and not user:
        return ""
    try:
        if raw and any(value for key, value in env.items() if key.startswith("BUSINESS_MYSQL_")):
            raise ValueError()
        url = (
            make_url(raw)
            if raw
            else URL.create(
                "mysql+pymysql",
                username=user,
                password=env.get("BUSINESS_MYSQL_PASSWORD") or "",
                host=env.get("BUSINESS_MYSQL_HOST") or "127.0.0.1",
                port=int(env.get("BUSINESS_MYSQL_PORT") or "3306"),
                database=env.get("BUSINESS_MYSQL_DATABASE") or "financial_invoice_business",
            )
        )
        if (
            url.drivername != "mysql+pymysql"
            or not url.host
            or not url.username
            or not url.database
            or not 1 <= (url.port or 3306) <= 65535
        ):
            raise ValueError()
        return url.update_query_dict({"charset": "utf8mb4"}).render_as_string(hide_password=False)
    except (ArgumentError, ValueError, TypeError):
        raise ValueError(
            "业务库必须使用MySQL；请选择BUSINESS_DATABASE_URL或BUSINESS_MYSQL_*分项配置，不能混用"
        ) from None


def make_business_engine(database_url):
    if not database_url:
        return None
    if make_url(database_url).drivername != "mysql+pymysql":
        raise ValueError("业务库仅支持MySQL / PyMySQL")
    engine = make_engine(database_url)

    @event.listens_for(engine, "connect")
    def setup_business_connection(connection, _):
        with connection.cursor() as cursor:
            cursor.execute("SET time_zone = '+00:00'")

    return engine


def check_business_database(engine):
    """只检查可连接及六张基础表可见；不读取业务数据、不声明写入权限已验证。"""
    result = {
        "configured": engine is not None,
        "connected": False,
        "ready": False,
        "state": "not_configured",
        "message": "尚未配置MySQL业务库",
        "missingTables": [],
    }
    if engine is None:
        return result
    try:
        with engine.connect() as connection:
            tables = set(inspect(connection).get_table_names())
        missing = sorted(set(BUSINESS_TABLES) - tables)
        return {
            **result,
            "connected": True,
            "ready": not missing,
            "state": "schema_incomplete" if missing else "connected",
            "message": "业务库缺少基础表，请核对六表建库SQL"
            if missing
            else "MySQL连接成功，六张业务表可见；本次连接检查不写入数据",
            "missingTables": missing,
        }
    except SQLAlchemyError as error:
        # 驱动异常可能含账户、主机或SQL，接口和CLI只输出固定中文说明。
        code = getattr(getattr(error, "orig", None), "args", (None,))[0]
        message = {
            1045: "MySQL认证失败，请检查业务库用户名和密码",
            1044: "MySQL账户无权访问业务库，请检查授权",
            1049: "业务数据库不存在，请先执行六表建库SQL",
            2003: "无法连接MySQL，请检查服务、地址和端口",
        }.get(code, "MySQL连接或表检查失败，请检查业务库配置与权限")
        return {**result, "state": "connection_failed", "message": message}

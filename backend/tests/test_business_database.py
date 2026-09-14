"""独立业务库配置、安全边界及只读检查；不使用现有真实业务库。"""

from contextlib import contextmanager
from unittest.mock import Mock

import pytest
from backend.app import create_app
from backend.core import business_database as database
from backend.core.config import load_settings
from fastapi.testclient import TestClient
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError


def test_business_config_preserves_application_database_and_password(env):
    secret = "password@with:/?#%字符"
    settings = load_settings({**env, "BUSINESS_MYSQL_USER": "invoice", "BUSINESS_MYSQL_PASSWORD": secret})
    url = make_url(settings.business_database_url)
    assert url.password == secret
    assert url.host == "127.0.0.1" and url.port == 3306
    assert url.database == "financial_invoice_business"
    assert url.query["charset"] == "utf8mb4"
    assert settings.database_url.startswith("sqlite:")
    assert secret not in repr(settings)
    assert load_settings(env).business_database_url == ""


@pytest.mark.parametrize(
    "config",
    [
        {"BUSINESS_DATABASE_URL": "sqlite:///wrong.sqlite"},
        {"BUSINESS_DATABASE_URL": "mysql+pymysql://user@localhost"},
        {"BUSINESS_MYSQL_USER": "invoice", "BUSINESS_MYSQL_PORT": "wrong"},
        {"BUSINESS_MYSQL_USER": "invoice", "BUSINESS_MYSQL_PORT": "70000"},
        {
            "BUSINESS_DATABASE_URL": "mysql+pymysql://user:secret@localhost/business",
            "BUSINESS_MYSQL_USER": "other",
        },
    ],
)
def test_business_invalid_config_has_safe_error(env, config):
    with pytest.raises(ValueError) as error:
        load_settings({**env, **config})
    assert "secret" not in str(error.value)


def test_same_mysql_schema_rejected_even_with_different_users(env):
    with pytest.raises(ValueError, match="独立库名"):
        load_settings(
            {
                **env,
                "DATABASE_URL": "mysql+pymysql://application@localhost/application",
                "BUSINESS_DATABASE_URL": "mysql+pymysql://business@127.0.0.1:3306/application",
            }
        )


def test_check_missing_tables_then_ready_without_business_data_access(monkeypatch):
    inspector = Mock()
    inspector.get_table_names.return_value = ["purchase_orders"]
    monkeypatch.setattr(database, "inspect", lambda connection: inspector)
    engine = Mock()
    engine.connect.return_value.__enter__ = Mock(return_value=object())
    engine.connect.return_value.__exit__ = Mock(return_value=False)
    result = database.check_business_database(engine)
    assert result["state"] == "schema_incomplete" and result["connected"]
    assert len(result["missingTables"]) == 5 and not result["ready"]
    inspector.get_table_names.return_value = list(database.BUSINESS_TABLES)
    assert database.check_business_database(engine)["ready"]
    assert inspector.method_calls == [("get_table_names", (), {}), ("get_table_names", (), {})]


@pytest.mark.parametrize("code", [1045, 1044, 1049, 2003, 2013])
def test_driver_failure_does_not_expose_credentials(code):
    engine = Mock()
    engine.connect.side_effect = OperationalError(
        "secret SQL", {"password": "secret-password"}, Exception(code, "private host and username")
    )
    result = database.check_business_database(engine)
    assert result["state"] == "connection_failed"
    assert not result["ready"] and not result["connected"]
    assert "secret" not in str(result) and "private" not in str(result)


def test_database_endpoint_requires_login_and_keeps_existing_health(context):
    with TestClient(create_app(context.settings, context.ns, context.engine)) as client:
        assert client.get("/api/business/database-status").status_code == 401
        assert client.get("/api/health").json() == {"status": "ok"}
        response = client.get(
            "/api/business/database-status",
            headers={"Authorization": f"Bearer {context.settings.service_key}"},
        )
        assert response.status_code == 200
        assert response.json()["state"] == "not_configured"
        assert not context.ns.writes


def test_business_outage_keeps_writeback_engine_and_releases_owned_pool(context, monkeypatch):
    engine = Mock()
    engine.connect.side_effect = OperationalError("", {}, Exception(2003, "private"))
    monkeypatch.setattr("backend.app.make_business_engine", lambda url: engine)
    with TestClient(create_app(context.settings, context.ns, context.engine)) as client:
        response = client.get(
            "/api/business/database-status",
            headers={"Authorization": f"Bearer {context.settings.service_key}"},
        )
        assert response.json()["state"] == "connection_failed"
        assert client.get("/api/health").status_code == 200
        with context.engine.connect() as connection:
            assert connection.dialect.name == "sqlite"
    engine.dispose.assert_called_once()


def test_business_engine_is_mysql_only():
    assert database.make_business_engine("") is None
    with pytest.raises(ValueError, match="MySQL"):
        database.make_business_engine("sqlite:///:memory:")


def test_successful_probe_closes_connection(monkeypatch):
    released = []

    @contextmanager
    def connect():
        try:
            yield object()
        finally:
            released.append(True)

    engine = Mock(connect=connect)
    monkeypatch.setattr(
        database, "inspect", lambda conn: Mock(get_table_names=lambda: database.BUSINESS_TABLES)
    )
    assert database.check_business_database(engine)["ready"]
    assert released == [True]

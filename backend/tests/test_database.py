from io import StringIO

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from backend.core.config import ROOT, load_settings
from backend.database import metadata
from backend.manage import upgrade
from sqlalchemy.engine import make_url


def test_mysql_8_ddl_portable_locks_charset_and_text_capacity():
    output = StringIO()
    config = Config(str(ROOT / "backend" / "legacy_migrations" / "app.ini"), output_buffer=output)
    config.attributes["database_url"] = "mysql+pymysql://unused@localhost/test?charset=utf8mb4"
    command.upgrade(config, "head", sql=True)
    sql = output.getvalue()
    assert "ENGINE=InnoDB" in sql and "utf8mb4" in sql
    assert "PRIMARY KEY (account, target)" in sql and "FOREIGN KEY(preview_id)" in sql
    assert "snapshot LONGTEXT" in sql and "expires BIGINT" in sql
    assert "WHERE state" not in sql and "PRAGMA" not in sql


def test_migrations_match_models_and_are_repeatable(context):
    upgrade(context.settings.database_url)
    with context.engine.connect() as connection:
        assert compare_metadata(MigrationContext.configure(connection), metadata) == []


@pytest.mark.parametrize(
    "values",
    [
        {"NETSUITE_PRIVATE_KEY_PATH": "frontend/public/private.pem"},
        {"NETSUITE_PRIVATE_KEY_PATH": "frontend/private.pem"},
        {"DATABASE_URL": "sqlite:///./frontend/dist/secret.sqlite"},
        {"DATABASE_URL": "postgresql://user:secret@localhost/test"},
        {"APP_ORIGIN": "http://example.com"},
        {"APP_ORIGIN": "https://example.com/"},
        {"NETSUITE_WRITE_FIELDS": "[]"},
        {"NETSUITE_WRITE_ENABLED": "yes"},
        {"DATABASE_PATH": "./data/ns.sqlite"},
    ],
)
def test_bad_config_fails_closed(values):
    with pytest.raises(ValueError):
        load_settings(values)


def test_mysql_url_credentials_hidden_and_charset_configured():
    c = load_settings({"DATABASE_URL": "mysql+pymysql://user:secret%40password@127.0.0.1:3306/ns_invoice"})
    assert make_url(c.database_url).query["charset"] == "utf8mb4"
    assert make_url(c.database_url).password == "secret@password"
    assert "secret" not in repr(c)

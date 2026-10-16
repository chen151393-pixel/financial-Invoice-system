import pytest
from backend.core.config import load_settings
from sqlalchemy.engine import make_url


@pytest.mark.parametrize(
    "values",
    [
        {"NETSUITE_PRIVATE_KEY_PATH": "frontend/public/private.pem"},
        {"NETSUITE_PRIVATE_KEY_PATH": "frontend/private.pem"},
        {"BUSINESS_DATABASE_URL": "sqlite:///./frontend/dist/secret.sqlite"},
        {"BUSINESS_DATABASE_URL": "postgresql://user:secret@localhost/test"},
        {"APP_ORIGIN": "http://example.com"},
        {"APP_ORIGIN": "https://example.com/"},
        {"NETSUITE_WRITE_FIELDS": "[]"},
        {"NETSUITE_WRITE_ENABLED": "yes"},
    ],
)
def test_bad_config_fails_closed(values):
    with pytest.raises(ValueError):
        load_settings(values)


def test_mysql_url_credentials_hidden_and_charset_configured():
    c = load_settings(
        {"BUSINESS_DATABASE_URL": "mysql+pymysql://user:secret%40password@127.0.0.1:3306/ns_invoice"}
    )
    assert make_url(c.business_database_url).query["charset"] == "utf8mb4"
    assert make_url(c.business_database_url).password == "secret@password"
    assert "secret" not in repr(c)

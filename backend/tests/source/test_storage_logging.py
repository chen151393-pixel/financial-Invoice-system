"""数据库日志保留错误码和定位信息，SQL、驱动消息及业务正文不得进入日志。"""

import pytest
from backend.modules.source.service.storage_logging import log_database_error
from pymysql.err import OperationalError as DriverError
from sqlalchemy.exc import OperationalError, SQLAlchemyError


@pytest.mark.parametrize("code", [1038, 2013, "private-driver-message"])
def test_database_log_is_diagnostic_without_sensitive_exception_data(caplog, code):
    error = OperationalError(
        "SELECT private-sql",
        {"token": "private-token"},
        DriverError(code, "private-message with private-payload"),
        connection_invalidated=True,
    )
    try:
        raise error
    except OperationalError as caught:
        log_database_error(
            caught,
            operation="save_group",
            account="prod",
            kind="customs-declarations",
            group=[{"id": "990", "number": "private-number", "record": "private-payload"}],
        )
    record = caplog.records[-1]
    message = record.getMessage()
    assert "ns_storage_database_error operation=save_group" in message
    assert '"record_ids": ["990"]' in message
    assert f"db_code={code if type(code) is int else '-'}" in message
    assert "type=OperationalError" in message
    assert "connection_invalidated=True" in message
    assert "test_storage_logging.py:" in message
    assert "private-" not in caplog.text
    assert record.exc_info is None


def test_plain_database_error_and_control_characters_are_safe(caplog):
    log_database_error(
        SQLAlchemyError("private-message"),
        operation="recover_group",
        account="prod",
        group=[{"id": "990\nforged-log"}],
    )
    message = caplog.records[-1].getMessage()
    assert "db_code=-" in message and "frames=[]" in message
    assert "\n" not in message
    assert "private-message" not in message

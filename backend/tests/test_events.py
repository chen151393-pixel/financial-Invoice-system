"""进程内事件总线：同一事务执行、失败整体回滚、登记约束。"""

from dataclasses import dataclass

import pytest
from backend.core.database import make_engine
from backend.core.events import EventBus
from sqlalchemy import text


@dataclass(frozen=True)
class Approved:
    value: int


@dataclass(frozen=True)
class Other:
    value: int


@pytest.fixture
def engine(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'events.sqlite'}")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE log (value INTEGER NOT NULL)"))
    yield engine
    engine.dispose()


def rows(engine):
    with engine.connect() as connection:
        return [row.value for row in connection.execute(text("SELECT value FROM log ORDER BY rowid"))]


def test_handlers_run_in_publisher_transaction_in_order(engine):
    bus = EventBus()
    bus.subscribe(Approved, lambda c, e: c.execute(text("INSERT INTO log VALUES (:v)"), {"v": e.value}))
    bus.subscribe(Approved, lambda c, e: c.execute(text("INSERT INTO log VALUES (:v)"), {"v": e.value * 10}))
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO log VALUES (0)"))
        bus.publish(connection, Approved(1))
    assert rows(engine) == [0, 1, 10]


def test_failing_subscriber_rolls_back_publisher_and_other_subscribers(engine):
    bus = EventBus()
    bus.subscribe(Approved, lambda c, e: c.execute(text("INSERT INTO log VALUES (:v)"), {"v": e.value}))

    def fail(connection, event):
        raise ValueError("订阅方失败")

    bus.subscribe(Approved, fail)
    with pytest.raises(ValueError, match="订阅方失败"):
        with engine.begin() as connection:
            connection.execute(text("INSERT INTO log VALUES (0)"))
            bus.publish(connection, Approved(1))
    assert rows(engine) == []


def test_only_matching_event_type_is_delivered(engine):
    bus = EventBus()
    received = []
    bus.subscribe(Other, lambda c, e: received.append(e))
    with engine.begin() as connection:
        bus.publish(connection, Approved(1))
    assert received == []


def test_publish_requires_open_transaction(engine):
    bus = EventBus()
    with engine.connect() as connection:
        with pytest.raises(RuntimeError, match="事务"):
            bus.publish(connection, Approved(1))


def test_same_handler_cannot_subscribe_twice():
    bus = EventBus()

    def handler(connection, event):
        pass

    bus.subscribe(Approved, handler)
    with pytest.raises(ValueError):
        bus.subscribe(Approved, handler)

from copy import deepcopy
from types import SimpleNamespace

import pytest
from backend.core.config import load_settings
from backend.core.errors import ApiError
from backend.database import make_engine
from backend.integrations.netsuite.client import NetSuite
from backend.manage import upgrade


class FakeNS:
    def __init__(self, settings):
        self.settings = settings
        self.record = {"id": "1", "memo": "old", "links": [{"href": "https://example.invalid/1"}]}
        self.created = {}
        self.writes = []
        self.fail_write = False
        self.fail_read = False

    validate = NetSuite.validate

    def token(self):
        return "test-token-never-return-to-browser"

    def request(self, method, record_type, record_id=None, payload=None, token=None):
        self.validate(record_type, record_id)
        if method == "GET":
            if self.fail_read:
                raise ApiError(502, "read failed")
            if record_id and record_id.startswith("eid:"):
                if record_id not in self.created:
                    raise ApiError(404, "absent")
                return {"data": deepcopy(self.created[record_id])}
            return {"data": deepcopy(self.record)}
        self.writes.append((method, record_type, record_id, deepcopy(payload)))
        if self.fail_write:
            raise ApiError(502, "write timeout")
        if method == "POST":
            self.created[f"eid:{payload['externalId']}"] = {"id": "2", **deepcopy(payload)}
        else:
            self.record.update(deepcopy(payload))
        return {"data": None, "status": 204, "location": "https://example.invalid/2"}


@pytest.fixture
def env():
    return {
        "NETSUITE_ACCOUNT_ID": "123456_SB1",
        "NETSUITE_RECORD_TYPES": "vendorBill",
        "NETSUITE_WRITE_FIELDS": '{"vendorBill":["memo","externalId"]}',
        "NETSUITE_WRITE_ENABLED": "true",
        "ADMIN_PASSWORD": "test-only-password-1234",
        "SERVICE_API_KEY": "test-service-key-at-least-32-characters",
    }


@pytest.fixture
def context(tmp_path, env):
    settings = load_settings({**env, "DATABASE_URL": f"sqlite:///{tmp_path / 'test.sqlite'}"})
    upgrade(settings.database_url)
    engine = make_engine(settings.database_url)
    ns = FakeNS(settings)
    yield SimpleNamespace(settings=settings, engine=engine, ns=ns)
    engine.dispose()

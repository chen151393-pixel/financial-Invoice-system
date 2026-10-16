"""4e 启动与接口边界：只有新表即可启动，旧接口不再挂载。"""

import inspect

from backend.app import create_app
from backend.manage import verify_database
from backend.modules.source import public
from fastapi.testclient import TestClient
from sqlalchemy import inspect as db_inspect
from sqlalchemy import text


def test_new_schema_only_startup_and_retired_routes(context):
    assert "business_engine" not in inspect.signature(create_app).parameters
    assert not hasattr(public, "PlReader") and not hasattr(public, "RelationReader")
    verify_database(context.engine)
    assert "alembic_version" not in db_inspect(context.engine).get_table_names()
    app = create_app(context.settings, context.ns, context.engine)
    assert not any(path.startswith("/api/reconciliation") for path in app.openapi()["paths"])
    with TestClient(app) as client:
        assert client.get("/api/health").status_code == 200
    with context.engine.begin() as c:
        c.execute(text("UPDATE schema_version SET version_num='0001_baseline'"))
    import pytest

    with pytest.raises(RuntimeError, match="版本不匹配"):
        verify_database(context.engine)

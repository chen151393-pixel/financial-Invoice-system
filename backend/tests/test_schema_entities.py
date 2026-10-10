"""各模块 entity/ 中的表定义必须与新迁移链建出的表结构一致（数据库设计第 9 节）。

只比较已在 schema_metadata 中登记的表；模块重建时登记自己的表，本测试自动覆盖。
"""

import importlib

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from backend.core.database import make_engine
from backend.core.schema import schema_metadata
from backend.manage import upgrade_schema

# 已切换到新表的模块：导入其 entity 包即登记表定义。
MODULES = ["backend.modules.source.entity"]


@pytest.fixture(scope="module")
def migrated(tmp_path_factory):
    for module in MODULES:
        importlib.import_module(module)
    engine = make_engine(f"sqlite:///{tmp_path_factory.mktemp('entities') / 'schema.sqlite'}")
    upgrade_schema(engine.url.render_as_string(hide_password=False))
    yield engine
    engine.dispose()


def test_entities_registered():
    for module in MODULES:
        importlib.import_module(module)
    assert {name for name in schema_metadata.tables if name.startswith("source_")} == {
        "source_suppliers",
        "source_companies",
        "source_raw_records",
        "source_parent_orders",
        "source_parent_order_lines",
        "source_purchase_orders",
        "source_purchase_order_lines",
        "source_customs_declarations",
        "source_customs_lines",
        "source_customs_purchase_links",
    }


def test_entities_match_migrations(migrated):
    def include_object(obj, name, kind, reflected, compare_to):
        # 只比较已登记的表；尚未切换模块的表由迁移建出但还没有 entity 定义。
        if kind == "table":
            return name in schema_metadata.tables
        return True

    with migrated.connect() as connection:
        context = MigrationContext.configure(
            connection, opts={"include_object": include_object, "compare_type": True}
        )
        differences = compare_metadata(context, schema_metadata)
    assert differences == []

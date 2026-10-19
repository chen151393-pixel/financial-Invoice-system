"""迁移链可定位性：单一最新版本、命名与模块归属、字段字典覆盖，以及对照文档未过期。"""

import re
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from backend.migrations import schema_map


@pytest.fixture(scope="module")
def ordered():
    return schema_map.revisions()


def _scripts():
    return list(ScriptDirectory.from_config(Config(str(schema_map.SCHEMA_INI))).walk_revisions())


def test_single_head():
    heads = schema_map.heads()
    assert len(heads) == 1, (
        f"迁移链出现多个最新版本 {sorted(heads)}：并行分支各自新增了迁移，"
        "合并后请把较晚的迁移改为下一个编号，并让 down_revision 指向另一个"
    )


def test_revision_files_named_and_numbered():
    numbers = []
    for script in _scripts():
        stem = Path(script.path).stem
        assert script.revision == stem, f"{stem}：revision 必须与文件名一致"
        match = re.fullmatch(r"(\d{4})_(\w+)", stem)
        assert match, f"{stem}：文件名须为 NNNN_<module>_<说明>"
        assert stem == "0001_baseline" or match.group(2).split("_", 1)[0] in schema_map.MODULES, (
            f"{stem}：编号后须为模块名 {schema_map.MODULES}"
        )
        numbers.append(int(match.group(1)))
    assert sorted(numbers) == list(range(1, len(numbers) + 1)), "迁移编号须从 0001 连续且不重复"


def test_migration_touches_only_own_module(ordered):
    for revision in ordered:
        if revision.id in schema_map.MULTI_MODULE_REVISIONS:
            continue
        module = revision.id.split("_")[1]
        others = sorted(name for name in revision.tables if not name.startswith(f"{module}_"))
        assert not others, f"{revision.id} 只能修改 {module} 模块的表，实际还修改了 {others}"


def test_dictionary_covers_all_entity_tables():
    missing = sorted(set(schema_map.entity_tables()) - set(schema_map.dictionary_anchors()))
    assert not missing, f"docs/mysql/current-data-dictionary.md 缺少这些表的 `### 表名` 小节：{missing}"


def test_schema_map_document_is_current():
    expected = schema_map.render()
    actual = schema_map.OUTPUT.read_text(encoding="utf-8").replace("\r\n", "\n")
    assert actual == expected, "docs/mysql/schema-map.md 已过期，请运行 npm.cmd run db:map 重新生成"


def test_dictionary_anchor_rules():
    text = '<a id="a_table"></a>\n\n### a_table｜甲\n\n### `b_table`\n\n### c_table｜丙\n\n## 其他\n'
    assert schema_map.dictionary_anchors(text) == {
        "a_table": "a_table",
        "b_table": "b_table",
        "c_table": "c_table丙",
    }

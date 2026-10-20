"""表与迁移对照：从迁移链离线 MySQL DDL 反查每张表由哪个迁移新建、哪些迁移修改。

只读取迁移脚本、实体定义与字段字典，不连接数据库。备注迁移的 DDL 来自冻结 SQL 文件，
直接搜索 Python 源码会漏掉，因此以 Alembic 离线输出的真实语句为准。
"""

import importlib
import io
import re
from dataclasses import dataclass, field

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from backend.core.config import ROOT
from backend.core.schema import schema_metadata
from backend.manage import OFFLINE_MYSQL_URL, SCHEMA_INI
from backend.migrations.version_table import VERSION_TABLE

MODULES = ("source", "review", "task", "invoice", "matching", "sync")
DICTIONARY = ROOT / "docs" / "mysql" / "current-data-dictionary.md"
OUTPUT = ROOT / "docs" / "mysql" / "schema-map.md"
# 已执行的历史迁移不改名不拆分：基线一次建全部表；0003 早于“一个迁移只改一个模块”的规则。
MULTI_MODULE_REVISIONS = {"0001_baseline", "0003_task_review_revision_and_notification_fields"}

_RUNNING = re.compile(r"^-- Running upgrade .*?-> (\S+)\s*$", re.M)
_NAME = r"`?(\w+)`?"
_STATEMENTS = (
    ("created", re.compile(rf"^CREATE TABLE {_NAME}", re.M)),
    ("dropped", re.compile(rf"^DROP TABLE {_NAME}", re.M)),
    ("altered", re.compile(rf"^ALTER TABLE {_NAME}", re.M)),
    ("altered", re.compile(rf"^CREATE (?:UNIQUE )?INDEX \S+ ON {_NAME}", re.M)),
    ("altered", re.compile(rf"^DROP INDEX \S+ ON {_NAME}", re.M)),
    ("data", re.compile(rf"^(?:INSERT INTO|UPDATE|DELETE FROM) {_NAME}", re.M)),
)


@dataclass
class Revision:
    id: str
    summary: str
    tables: dict = field(default_factory=dict)  # 表名 -> {"created", "altered", ...}


@dataclass
class TableEntry:
    name: str
    module: str
    comment: str
    created_by: list = field(default_factory=list)
    altered_by: list = field(default_factory=list)
    anchor: str | None = None


def revisions():
    """按迁移顺序返回 Revision 列表（基线在前）。"""
    script = ScriptDirectory.from_config(Config(str(SCHEMA_INI)))
    ordered = [Revision(item.revision, _summary(item.doc)) for item in script.walk_revisions()]
    ordered.reverse()
    by_id = {item.id: item for item in ordered}
    for revision_id, sql in _offline_sql_by_revision().items():
        for kind, pattern in _STATEMENTS:
            for table in pattern.findall(sql):
                if table != VERSION_TABLE:
                    by_id[revision_id].tables.setdefault(table, set()).add(kind)
    return ordered


def heads():
    return ScriptDirectory.from_config(Config(str(SCHEMA_INI))).get_heads()


def entity_tables():
    for module in MODULES:
        importlib.import_module(f"backend.modules.{module}.entity")
    return schema_metadata.tables


def dictionary_anchors(text=None):
    """字段字典中每张表的锚点；未找到 `### 表名` 小节的表不在结果中。"""
    text = DICTIONARY.read_text(encoding="utf-8") if text is None else text
    explicit = set(re.findall(r'<a id="(\w+)"></a>', text))
    anchors = {}
    for heading in re.findall(r"^### (.+?)\s*$", text, re.M):
        match = re.match(r"`?(\w+)`?(?:｜|$)", heading)
        if match:
            table = match.group(1)
            anchors[table] = table if table in explicit else _slug(heading)
    return anchors


def table_entries(ordered=None):
    ordered = revisions() if ordered is None else ordered
    tables = entity_tables()
    anchors = dictionary_anchors()
    names = set(tables) | {name for item in ordered for name in item.tables}
    entries = {}
    for name in sorted(names):
        table = tables.get(name)
        entries[name] = TableEntry(
            name=name,
            module=name.split("_", 1)[0],
            comment=(table.comment or "") if table is not None else "",
            anchor=anchors.get(name),
        )
    for revision in ordered:
        for name, kinds in revision.tables.items():
            target = entries[name].created_by if "created" in kinds else entries[name].altered_by
            target.append(revision.id)
    return entries, tables


def render():
    ordered = revisions()
    entries, tables = table_entries(ordered)
    lines = [
        "# 表与迁移对照",
        "",
        "> 本文件由 `npm.cmd run db:map` 根据迁移链离线 MySQL DDL、实体定义和字段字典生成，请勿手工修改；"
        "迁移或实体变化后重新生成，`backend/tests/test_schema_map.py` 会检查是否过期。",
        "> “修改”含加列、改列、索引与中文备注；数据回填仅在线执行，不在离线 DDL 中体现。",
        "",
        f"当前最新迁移：`{ordered[-1].id}`；共 {len(ordered)} 个迁移、{len(tables)} 张实体表。",
        "",
        "## 1. 按模块查表",
        "",
    ]
    for module in MODULES:
        rows = [entry for entry in entries.values() if entry.module == module]
        lines += [
            f"### {module}",
            "",
            "| 表 | 中文说明 | 新建 | 后续修改 | 字段字典 |",
            "| --- | --- | --- | --- | --- |",
        ]
        for entry in rows:
            comment = entry.comment or (
                "（无实体定义，代码不读写；说明见字段字典）" if entry.name not in tables else ""
            )
            link = f"[查看](current-data-dictionary.md#{entry.anchor})" if entry.anchor else "**缺失**"
            lines.append(
                f"| `{entry.name}` | {_cell(comment)} | {_codes(entry.created_by)} "
                f"| {_codes(entry.altered_by)} | {link} |"
            )
        lines.append("")
    lines += [
        "## 2. 按迁移查表",
        "",
        "| 迁移 | 新建表 | 修改表 | 说明 |",
        "| --- | --- | --- | --- |",
    ]
    for revision in ordered:
        created = sorted(name for name, kinds in revision.tables.items() if "created" in kinds)
        altered = sorted(name for name, kinds in revision.tables.items() if "created" not in kinds)
        link = f"[`{revision.id}`](../../backend/migrations/versions/{revision.id}.py)"
        lines.append(f"| {link} | {_names(created)} | {_names(altered)} | {_cell(revision.summary)} |")
    return "\n".join(lines) + "\n"


def write():
    OUTPUT.write_text(render(), encoding="utf-8", newline="\n")
    return OUTPUT


def _offline_sql_by_revision():
    buffer = io.StringIO()
    config = Config(str(SCHEMA_INI), output_buffer=buffer)
    config.attributes["database_url"] = OFFLINE_MYSQL_URL
    command.upgrade(config, "head", sql=True)
    parts = _RUNNING.split(buffer.getvalue())
    return dict(zip(parts[1::2], parts[2::2], strict=True))


def _summary(doc):
    return (doc or "").strip().splitlines()[0] if doc else ""


def _slug(heading):
    # 与 GitHub/VS Code 标题锚点一致：小写、去标点、空格变连字符。
    return re.sub(r"[^\w\- ]", "", heading.strip().lower()).replace(" ", "-")


def _cell(text):
    return text.replace("|", "\\|")


def _codes(items):
    return "、".join(f"`{item[:4]}`" for item in items) or "—"


def _names(items):
    return "、".join(f"`{item}`" for item in items) or "—"

"""执行冻结的中文备注 DDL；不依赖随业务变化的实体定义。

MySQL 的 MODIFY COLUMN 必须携带完整字段声明，快照保留类型、默认值、
自增与生成表达式。SQLite 不支持持久列备注，迁移只推进版本、不重建表。
"""

from pathlib import Path

from sqlalchemy import text


def apply_comments(operations, module, direction):
    context = operations.get_context()
    if context.dialect.name == "sqlite":
        return
    if context.dialect.name != "mysql":
        raise RuntimeError("中文备注迁移仅支持 MySQL，SQLite 测试库跳过备注 DDL")
    path = Path(__file__).with_name("comments_20261015") / f"{module}_{direction}.sql"
    for statement in path.read_text(encoding="utf-8").split(";\n"):
        if statement.strip():
            # 备注中的冒号属于文字，不能被 SQLAlchemy 识别为绑定参数。
            operations.execute(text(statement.strip().replace(":", r"\:")))

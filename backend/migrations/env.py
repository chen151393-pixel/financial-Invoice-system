from alembic import context
from backend.config import load_settings
from backend.database import make_engine, metadata

config = context.config

if context.is_offline_mode():
    context.configure(
        url=config.attributes.get("database_url") or load_settings().database_url,
        target_metadata=metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = make_engine(config.attributes.get("database_url") or load_settings().database_url)
    try:
        with engine.connect() as connection:
            context.configure(connection=connection, target_metadata=metadata)
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()

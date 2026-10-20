"""sync：柠檬云后台分片并入 sync_lemon_runs，sync_runs 只保留 phase 一个批次状态。

- 每个分片原先在 sync_lemon_jobs 与 sync_lemon_runs 各存一行（同账套、同日期、同请求编号），状态还要互相抄写；
  本迁移把分片逐行并入 sync_lemon_runs（新增 run_id 指向批次，新增 queued、split 状态），
  background 由 run_id 是否为空代替后删除。
- sync_lemon_jobs 表与数据保留在库中，代码不再读写；管理员核对后可手工删除，迁移不删表。
- sync_runs 的 status、account、window_start、window_end 与 phase、scope_key、configuration 重复；
  逐行核对可完整还原后才删除，任一行无法还原即中止迁移，不静默丢弃。
降级会丢失分片归属与已删除的重复列，禁止降级。
"""

from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op
from backend.core.schema import ID, identifier

revision = "0025_sync_merge_lemon_jobs"
down_revision = "0024_sync_ns_runs"
branch_labels = None
depends_on = None

PHASES = ("queued", "discovering", "running", "completed", "partial", "failed", "unknown")
PHASE_COMMENT = (
    "批次状态：queued排队；discovering查询账套；running执行中；completed完成；"
    "partial部分成功；failed失败；unknown存在待核实分片"
)
PULL_STATUS_COMMENT = (
    "queued后台分片待执行；running执行中或待核实；completed已提交；failed未保存；split超量已拆分为两个分片"
)

# 迁移冻结自己的表视图，不依赖随业务变化的实体定义。
batches = sa.table(
    "sync_runs",
    sa.column("id", ID),
    sa.column("scope_key", sa.String),
    sa.column("phase", sa.String),
    sa.column("account", sa.String),
    sa.column("configuration", sa.JSON),
    sa.column("window_start", sa.DateTime),
    sa.column("window_end", sa.DateTime),
)
shards = sa.table(
    "sync_lemon_jobs",
    *(sa.column(name) for name in ("id", "run_id", "request_id", "asid", "account_name", "status", "error")),
    sa.column("start_date", sa.Date),
    sa.column("end_date", sa.Date),
    sa.column("created_at", sa.DateTime),
    sa.column("updated_at", sa.DateTime),
)
pulls = sa.table(
    "sync_lemon_runs",
    *(sa.column(name) for name in ("id", "scope_key", "request_id", "asid", "account_name", "status")),
    sa.column("start_date", sa.Date),
    sa.column("end_date", sa.Date),
    sa.column("result", sa.JSON),
    sa.column("error", sa.String),
    sa.column("background", sa.Boolean),
    sa.column("run_id", ID),
    sa.column("created_at", sa.DateTime),
    sa.column("updated_at", sa.DateTime),
)


def upgrade():
    online = not op.get_context().as_sql
    if online:
        # MySQL 的 DDL 会隐式提交；所有核对放在第一条 DDL 之前，失败时库保持原样。
        check_batches(op.get_bind())
        check_background(op.get_bind())
    with op.batch_alter_table("sync_lemon_runs") as batch:
        batch.add_column(sa.Column("run_id", ID, comment="所属后台批次；手动拉票为空"))
        batch.create_foreign_key("fk_sync_lemon_run_batch", "sync_runs", ["run_id"], ["id"])
        batch.create_index("ix_sync_lemon_run_batch", ["run_id", "status"])
    if online:
        merge_shards(op.get_bind())
    with op.batch_alter_table("sync_lemon_runs") as batch:
        batch.drop_column("background")
        batch.alter_column(
            "status",
            existing_type=identifier(20),
            existing_nullable=False,
            existing_comment="running执行中或待核实；completed已提交；failed未保存",
            comment=PULL_STATUS_COMMENT,
        )
    with op.batch_alter_table("sync_runs") as batch:
        batch.drop_constraint("ck_sync_run_status", type_="check")
        batch.drop_index("ix_sync_run_source")
        for name in ("status", "account", "window_start", "window_end"):
            batch.drop_column(name)
        batch.alter_column(
            "phase",
            existing_type=identifier(20),
            nullable=False,
            existing_comment="后台任务阶段",
            comment=PHASE_COMMENT,
        )
        batch.create_check_constraint("ck_sync_run_phase", f"phase IN ({','.join(map(repr, PHASES))})")
    if op.get_context().dialect.name == "mysql":
        op.create_table_comment(
            "sync_lemon_runs",
            "柠檬云拉票记录（手动或后台分片）与结果，不保存令牌",
            existing_comment="柠檬云手动拉票记录与结果，不保存令牌",
        )


def check_batches(connection):
    """删除的列必须能由保留列还原；否则中止，交由人工核对。"""
    for row in connection.execute(sa.select(batches)).mappings():
        config = row["configuration"] or {}
        windows = {
            "window_start": config.get("startDate"),
            "window_end": config.get("endDate"),
        }
        broken = (
            row["phase"] not in PHASES
            or not row["scope_key"]
            or row["account"] != row["scope_key"]
            or any(
                row[name] is not None and row[name].date().isoformat() != value
                for name, value in windows.items()
            )
        )
        if broken:
            raise RuntimeError(
                f"sync_runs id={row['id']} 的 status/account/时间窗口无法由 phase、scope_key、"
                "configuration 还原，迁移已中止且未修改数据，请人工核对"
            )


def merge_shards(connection):
    rows = connection.execute(
        sa.select(shards, batches.c.scope_key, batches.c.configuration).join(
            batches, shards.c.run_id == batches.c.id
        )
    ).mappings()
    for shard in rows:
        pull = connection.execute(
            sa.select(pulls.c.id).where(
                pulls.c.scope_key == shard["scope_key"], pulls.c.request_id == shard["request_id"]
            )
        ).first()
        if pull:
            # 原子拉票的状态是持久事实；只有“已拆分”是分片独有的，覆盖原 failed。
            values = {"run_id": shard["run_id"]}
            if shard["status"] == "split":
                values["status"] = "split"
            connection.execute(sa.update(pulls).where(pulls.c.id == pull.id).values(**values))
            continue
        # 未领取或领取前即失败的分片没有原子行；执行中/待核实却缺原子行时按执行中保留，继续阻止重试。
        status = shard["status"] if shard["status"] in ("queued", "failed", "split") else "running"
        connection.execute(
            sa.insert(pulls).values(
                scope_key=shard["scope_key"],
                request_id=shard["request_id"],
                asid=shard["asid"],
                account_name=shard["account_name"],
                start_date=shard["start_date"],
                end_date=shard["end_date"],
                status=status,
                result={
                    "businessTypes": (shard["configuration"] or {}).get("businessTypes", []),
                    "invoiceIds": [],
                },
                error=shard["error"] if status in ("failed", "split") else None,
                background=True,
                run_id=shard["run_id"],
                created_at=shard["created_at"],
                updated_at=shard["updated_at"] or datetime.now(UTC).replace(tzinfo=None),
            )
        )


def check_background(connection):
    """background 由 run_id 代替；每条后台拉票都必须找得到所属分片。"""
    owned = (
        sa.select(shards.c.id)
        .join(batches, shards.c.run_id == batches.c.id)
        .where(shards.c.request_id == pulls.c.request_id, batches.c.scope_key == pulls.c.scope_key)
    )
    orphan = connection.scalar(
        sa.select(pulls.c.id).where(pulls.c.background.is_(True), ~owned.exists()).limit(1)
    )
    if orphan is not None:
        raise RuntimeError(
            f"sync_lemon_runs id={orphan} 标记为后台执行却找不到所属分片，迁移已中止，请人工核对"
        )


def downgrade():
    raise RuntimeError("分片已并入 sync_lemon_runs 且重复列已删除，不能降级删除或还原；请保留数据")

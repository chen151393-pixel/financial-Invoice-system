ALTER TABLE `sync_runs`
  MODIFY COLUMN id BIGINT UNSIGNED NOT NULL COMMENT '本地自增主键；与 NS 内部 ID、单号分开保存' AUTO_INCREMENT,
  MODIFY COLUMN source VARCHAR(32) NOT NULL COMMENT '同步来源：ns_customs 报关；ns_purchase 采购；lemon_invoice 发票',
  MODIFY COLUMN account VARCHAR(100) NOT NULL COMMENT '同步来源账套；随 source 表示 NS 或柠檬云账套',
  MODIFY COLUMN trigger_type VARCHAR(16) NOT NULL COMMENT '触发方式：schedule 定时；manual 手动',
  MODIFY COLUMN status VARCHAR(16) NOT NULL COMMENT '同步状态：running 运行中；succeeded 成功；partial 部分成功；failed 失败',
  MODIFY COLUMN window_start DATETIME(6) COMMENT '本次同步的时间窗口起点，UTC',
  MODIFY COLUMN window_end DATETIME(6) COMMENT '本次同步的时间窗口终点，UTC',
  MODIFY COLUMN fetched_count INTEGER NOT NULL COMMENT '本次取得的来源记录数' DEFAULT 0,
  MODIFY COLUMN created_count INTEGER NOT NULL COMMENT '本次新增记录数' DEFAULT 0,
  MODIFY COLUMN updated_count INTEGER NOT NULL COMMENT '本次更新记录数' DEFAULT 0,
  MODIFY COLUMN failed_count INTEGER NOT NULL COMMENT '本次失败记录数' DEFAULT 0,
  MODIFY COLUMN message TEXT COMMENT '同步结果或失败原因，不记录凭据',
  MODIFY COLUMN started_by VARCHAR(200) NOT NULL COMMENT '发起操作者或 scheduler',
  MODIFY COLUMN started_at DATETIME(6) NOT NULL COMMENT '同步运行开始时间，UTC',
  MODIFY COLUMN finished_at DATETIME(6) COMMENT '同步运行结束时间，UTC',
  MODIFY COLUMN created_at DATETIME(6) NOT NULL COMMENT '本地记录创建时间，UTC' DEFAULT CURRENT_TIMESTAMP(6),
  MODIFY COLUMN updated_at DATETIME(6) NOT NULL COMMENT '本地记录最后更新时间，UTC；由 DAO 更新' DEFAULT CURRENT_TIMESTAMP(6),
  COMMENT = '同步运行记录';

ALTER TABLE `sync_cursors`
  MODIFY COLUMN source VARCHAR(32) NOT NULL COMMENT '同步来源：ns_customs 报关；ns_purchase 采购；lemon_invoice 发票',
  MODIFY COLUMN account VARCHAR(100) NOT NULL COMMENT '同步来源账套；随 source 表示 NS 或柠檬云账套',
  MODIFY COLUMN last_modified_at DATETIME(6) COMMENT '已完整处理的来源修改时间水位；用于下次增量同步',
  MODIFY COLUMN last_run_id BIGINT UNSIGNED COMMENT '最近关联同步运行 ID，指向 sync_runs.id',
  MODIFY COLUMN created_at DATETIME(6) NOT NULL COMMENT '本地记录创建时间，UTC' DEFAULT CURRENT_TIMESTAMP(6),
  MODIFY COLUMN updated_at DATETIME(6) NOT NULL COMMENT '本地记录最后更新时间，UTC；由 DAO 更新' DEFAULT CURRENT_TIMESTAMP(6),
  COMMENT = '增量同步水位';

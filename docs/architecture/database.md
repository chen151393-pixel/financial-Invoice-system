# 数据库设计

状态：**草案，待确认**。依据[架构设计 v2](README.md)的业务规则和 `test` 分支当前表结构编写。总体规则见[后端规则](backend-rules.md)第 8 节。

## 1. 业务规则如何决定表结构

| 业务规则 | 表结构上的做法 |
| --- | --- |
| 按子采购单开票，审核不调整 | **开票单元 = 子采购行**（`purchase_order_lines.id`）。审核通过时把子采购行的应开数量、金额**冻结**到任务行；来源以后变化不改任务行，只提示重新审核 |
| 同一子采购单只生成一次任务行 | 任务行对"有效的子采购行"加唯一约束（第 4.1 节生成列）；之后其他报关单审核通过时只追加关联记录。注：当前审核范围按 `purchase_orders.customs_declaration_id`（单值）取子采购单，同一时刻一张子采购单只属于一张报关单；唯一约束主要防止来源重新同步后子采购单改挂到另一张报关单时重复生成 |
| 多单一票、一票多单 | 分配表一行 = 一条发票行分给一条子采购行的数量和金额；一条发票行可分给多条子采购行，一条子采购行可由多条发票行分配 |
| 超开允许确认并标记 | 分配记录写 `exceeds_expected` 和说明；任务行状态 `over`，不自动算作已收齐 |
| 收票进度不能手工改 | 已收数量、金额只能由分配记录汇总得出；任务行上的 `received_*` 是缓存，可随时按分配表重算核对 |
| 重新审核不丢历史 | 旧任务和旧任务行置为 `superseded`，只读保留；新任务行的已收值按同一子采购行的分配记录重新汇总，收票进度自动延续 |
| 不删除数据 | 取消分配用 `status=cancelled`；停用的表停止写入，不删除 |

### 1.1 通用约定

- **一个库**：所有表在业务 MySQL 中，跨表一致性用同一个事务保证。
- **模块之间不建外键**：同一模块内的表建外键；跨模块只保存对方的 ID（例如任务行保存 `purchase_line_id`），一致性由 Service 在事务中校验。来源表只停用（`is_active=0`）不物理删除，保存的 ID 始终有效。
- **身份范围**：沿用现有字段，不改写历史数据。来源、发票、分配表用 `tenant_id`（登录身份的 SHA256）+ `ns_account`；审核、任务表用 `owner` + `account`。新的子表通过父表确定范围，不重复保存身份。
- **新表字段**：行类主键 `BIGINT UNSIGNED AUTO_INCREMENT`；金额 `DECIMAL(24,6)`，数量 `DECIMAL(26,8)`（与现有来源行、分配表一致）；时间 `DATETIME(6)`，存 UTC；`created_at`、`updated_at` 必填。
- **状态字段**：`VARCHAR` 加 `CHECK` 约束，允许值与 `policy/` 中的状态机一致。

## 2. 全景

```text
source（NS 来源，只由同步写入）
  parent_purchase_orders ─< parent_purchase_order_lines
  customs_declarations ─< customs_declaration_lines
  purchase_orders ─< purchase_order_lines            ← 开票单元
  customs_reconciliation_results（报关单与子采购的当前关联依据）
  unit_dictionary（申报单位字典，暂未使用）

review（财务核对）
  finance_review_snapshots ─< finance_reviews（当前审核头）
  finance_review_audit（审核历史）

task（开票跟进）
  finance_invoice_tasks ─< task_invoice_lines【新增】 ─< task_line_reviews【新增】
                        ─< finance_task_documents（合同）
                        ─< finance_task_notifications（通知版本）
  finance_supplier_groups（供应商企微群）

invoice（进项发票）
  invoices ─< invoice_lines

matching（发票分配）
  invoice_purchase_allocations【调整】：invoice_line_id × purchase_line_id
  invoice_purchase_link_batches / _pairs【停用，数据迁入分配表】

sync（同步）
  sync_runs【新增】、sync_cursors【新增】

（历史保留，无代码读写）ns_previews、ns_target_locks、ns_audit
```

跨模块引用（只存 ID，不建外键）：

```text
task_invoice_lines.purchase_line_id      → purchase_order_lines.id
task_line_reviews.snapshot_id            → finance_review_snapshots.id
invoice_purchase_allocations.purchase_line_id → purchase_order_lines.id
invoice_purchase_allocations.invoice_line_id  → invoice_lines.id
```

任务行和分配表**不互相引用**，两者都以 `purchase_line_id` 对齐。这样 `task` 不依赖 `matching` 的表，`matching` 也不依赖任务行的生命周期。

## 3. 现有表的处理

| 表 | 模块 | 处理 |
| --- | --- | --- |
| 母采购、子采购、报关及其明细 6 张，`customs_reconciliation_results` | source | 不变 |
| `unit_dictionary` | source | 不变；以后可用于发票单位与报关单位对照 |
| `invoices`、`invoice_lines` | invoice | 不变；柠檬云 API 导入复用 `external_system/external_account/external_record_id` 去重 |
| `finance_review_snapshots`、`finance_reviews`、`finance_review_audit` | review | 不变 |
| `finance_invoice_tasks` | task | 结构不变；`status` 增加收票相关取值（第 5 节）；`payload` 中的行明细改由任务行表承载，保留作历史 |
| `finance_task_documents`、`finance_task_notifications`、`finance_supplier_groups` | task | 不变 |
| `invoice_purchase_allocations` | matching | **增加列**（第 4.3 节），成为唯一的分配台账；预留但从未写入的 `review_*`、`customs_line_id` 列保留不用 |
| `invoice_purchase_link_batches`、`invoice_purchase_link_pairs` | matching | **停止写入**；现有记录迁入分配表后保留只读 |
| `ns_previews`、`ns_target_locks`、`ns_audit` | （已移出） | 保留表和数据，无代码读写 |

## 4. 新增与调整

### 4.1 任务行 `task_invoice_lines`（task）

```sql
CREATE TABLE task_invoice_lines (
  id                  BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  task_id             VARCHAR(36)   NOT NULL COMMENT '所属开票任务',
  purchase_order_id   BIGINT UNSIGNED NOT NULL COMMENT '子采购单本地ID（source）',
  purchase_line_id    BIGINT UNSIGNED NOT NULL COMMENT '子采购行本地ID（source），开票单元',
  order_no            VARCHAR(150)  NULL,
  item_name           VARCHAR(500)  NULL COMMENT '报关品名，缺失时为商品名',
  specification       VARCHAR(500)  NULL,
  currency            VARCHAR(20)   NULL,
  purchase_quantity   DECIMAL(26,8) NULL COMMENT '子采购原数量（冻结）',
  purchase_unit       VARCHAR(50)   NULL,
  declared_quantity   DECIMAL(26,8) NULL COMMENT '子采购报关数量（冻结）',
  declared_unit       VARCHAR(50)   NULL,
  expected_amount     DECIMAL(24,6) NULL COMMENT '应开含税金额（冻结）；来源缺失时为空',
  received_quantity   DECIMAL(26,8) NOT NULL DEFAULT 0 COMMENT '已分配数量缓存',
  received_amount     DECIMAL(24,6) NOT NULL DEFAULT 0 COMMENT '已分配含税金额缓存',
  status              VARCHAR(16)   NOT NULL DEFAULT 'open',
  source_digest       CHAR(64)      NOT NULL COMMENT '冻结时子采购行内容摘要',
  -- 只对有效行生效的唯一约束：superseded 行为 NULL，不参与唯一性
  active_purchase_line_id BIGINT UNSIGNED
      GENERATED ALWAYS AS (IF(status = 'superseded', NULL, purchase_line_id)) STORED,
  created_at          DATETIME(6)   NOT NULL,
  updated_at          DATETIME(6)   NOT NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uq_task_line_active_purchase (active_purchase_line_id),
  UNIQUE KEY uq_task_line_task_purchase (task_id, purchase_line_id),
  KEY ix_task_line_task_status (task_id, status),
  KEY ix_task_line_purchase (purchase_line_id),
  CONSTRAINT fk_task_line_task FOREIGN KEY (task_id) REFERENCES finance_invoice_tasks (id),
  CONSTRAINT ck_task_line_status CHECK (status IN ('open','partial','received','over','unverified','superseded'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin COMMENT='开票任务行：每条子采购行的应开与已收';
```

- 数量同时冻结采购口径和报关口径两套，因为发票单位可能与任一方一致（见第 8 节待确认）。
- `expected_amount` 为空（来源金额缺失）时，任务行状态为 `unverified`，不参与"已收齐"判断。

### 4.2 任务行的审核关联 `task_line_reviews`（task）

记录每一次覆盖到该子采购行的审核，满足"只生成一次，但显示关联的全部报关单"。

```sql
CREATE TABLE task_line_reviews (
  id               BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  task_line_id     BIGINT UNSIGNED NOT NULL,
  account          VARCHAR(100) NOT NULL,
  declaration_id   VARCHAR(190) NOT NULL COMMENT '报关单（审核头标识）',
  snapshot_id      VARCHAR(36)  NOT NULL COMMENT '审核快照（review）',
  review_revision  INT          NOT NULL,
  relation         VARCHAR(16)  NOT NULL COMMENT 'created=本次审核生成该行；covered=已有有效行，本次只关联',
  created_at       DATETIME(6)  NOT NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uq_task_line_review (task_line_id, snapshot_id),
  KEY ix_task_line_review_declaration (account, declaration_id),
  CONSTRAINT fk_task_line_review_line FOREIGN KEY (task_line_id) REFERENCES task_invoice_lines (id),
  CONSTRAINT ck_task_line_review_relation CHECK (relation IN ('created','covered'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin COMMENT='任务行与审核的关联';
```

### 4.3 统一分配台账：调整 `invoice_purchase_allocations`（matching）

```sql
ALTER TABLE invoice_purchase_allocations
  ADD COLUMN mode             VARCHAR(16) NOT NULL DEFAULT 'quantity' COMMENT 'quantity=按数量分配；link=整票关联批量写入',
  ADD COLUMN status           VARCHAR(16) NOT NULL DEFAULT 'confirmed' COMMENT 'confirmed / cancelled',
  ADD COLUMN exceeds_expected BOOL        NOT NULL DEFAULT 0 COMMENT '确认时已超过子采购行应开值',
  ADD COLUMN exceed_note      VARCHAR(300) NULL COMMENT '超开确认说明',
  ADD COLUMN cancelled_by     VARCHAR(255) NULL,
  ADD COLUMN cancelled_at     DATETIME(6)  NULL,
  ADD COLUMN cancel_reason    VARCHAR(300) NULL,
  ADD COLUMN active_pair_key  VARCHAR(41)
      GENERATED ALWAYS AS (IF(status = 'confirmed', CONCAT(invoice_line_id, ':', purchase_line_id), NULL)) STORED,
  ADD UNIQUE KEY uq_allocation_active_pair (tenant_id, active_pair_key),
  ADD KEY ix_allocation_purchase_status (tenant_id, purchase_line_id, status),
  ADD KEY ix_allocation_invoice_line_status (tenant_id, invoice_line_id, status),
  ADD CONSTRAINT ck_allocation_status CHECK (status IN ('confirmed','cancelled')),
  ADD CONSTRAINT ck_allocation_mode CHECK (mode IN ('quantity','link'));
```

- 同一条发票行和同一条子采购行之间只能有一条有效分配；要改数量先取消再重建，历史保留。
- **发票侧不允许超分配**：一条发票行已分配的数量和金额合计不能超过发票行本身。这是硬性校验，在确认事务中锁定发票行后检查。
- **采购侧允许超开**：超过子采购行应开值时可以确认，但必须填写 `exceed_note`。
- 现有列 `purchase_line_id` 为 `VARCHAR(20)`，保存的是子采购行 ID 的文本；本次不改类型，比较时由 DAO 统一转换。

### 4.4 同步记录（sync）

```sql
CREATE TABLE sync_runs (
  id            BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  tenant_id     VARCHAR(100) NOT NULL,
  source        VARCHAR(32)  NOT NULL COMMENT 'ns_customs / ns_purchase / lemon_invoice',
  account       VARCHAR(100) NOT NULL COMMENT 'NS 账套或柠檬云账套',
  trigger_type  VARCHAR(16)  NOT NULL COMMENT 'schedule / manual',
  status        VARCHAR(16)  NOT NULL COMMENT 'running / succeeded / partial / failed',
  window_start  DATETIME(6)  NULL COMMENT '本次拉取的来源修改时间范围',
  window_end    DATETIME(6)  NULL,
  fetched_count INT NOT NULL DEFAULT 0,
  created_count INT NOT NULL DEFAULT 0,
  updated_count INT NOT NULL DEFAULT 0,
  failed_count  INT NOT NULL DEFAULT 0,
  message       TEXT NULL COMMENT '中文结果或失败原因，不含凭据',
  started_by    VARCHAR(200) NOT NULL COMMENT '操作人或 scheduler',
  started_at    DATETIME(6)  NOT NULL,
  finished_at   DATETIME(6)  NULL,
  PRIMARY KEY (id),
  KEY ix_sync_run_source_started (tenant_id, source, account, started_at),
  CONSTRAINT ck_sync_run_status CHECK (status IN ('running','succeeded','partial','failed')),
  CONSTRAINT ck_sync_run_trigger CHECK (trigger_type IN ('schedule','manual'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin COMMENT='同步运行记录';

CREATE TABLE sync_cursors (
  tenant_id         VARCHAR(100) NOT NULL,
  source            VARCHAR(32)  NOT NULL,
  account           VARCHAR(100) NOT NULL,
  last_modified_at  DATETIME(6)  NULL COMMENT '已完整处理的来源修改时间水位',
  last_run_id       BIGINT UNSIGNED NULL,
  updated_at        DATETIME(6)  NOT NULL,
  PRIMARY KEY (tenant_id, source, account),
  CONSTRAINT fk_sync_cursor_run FOREIGN KEY (last_run_id) REFERENCES sync_runs (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin COMMENT='增量同步水位';
```

- 同一来源同一账套同时只运行一个同步：沿用现有 MySQL 命名锁（`dao.acquire_sync_lock`），与网页手动保存互斥。
- 只有整批成功才推进 `last_modified_at`；失败时水位不动，下次重拉，靠来源表唯一约束去重。

## 5. 状态与汇总规则

### 5.1 任务行状态（由分配汇总得出）

| 状态 | 条件 |
| --- | --- |
| `unverified` | `expected_amount` 为空（来源金额缺失） |
| `open` | 已收金额 = 0 |
| `partial` | 0 < 已收金额 < 应开金额 − 容差 |
| `received` | 已收金额与应开金额相差不超过容差 |
| `over` | 已收金额 > 应开金额 + 容差 |
| `superseded` | 所属任务被新审核版本替代 |

- **以含税金额判断是否收齐**；数量只在发票单位与采购单位或报关单位一致时做辅助校验，不一致时提示，不改变状态（见第 8 节待确认）。
- 容差处理发票两位小数与采购六位小数之间的舍入，默认每行 0.01 元，定义在 `task` 模块的 `policy/` 中。

### 5.2 任务状态

```text
documents_pending → notify_pending → awaiting_invoice ─┬→ partially_received → received → closed
                                                       └→ over_invoiced（任一行 over）
任何未完成状态 → superseded
```

- 前三个状态由现有合同、通知流程推进，不变。
- 收到第一条分配后，按任务行汇总：任一行 `over` → `over_invoiced`；全部有效行 `received` → `received`；否则 `partially_received`。`unverified` 行不计入"全部收齐"，任务停在 `partially_received` 并提示。
- `closed` 由人工确认完成（`received` 之后），记录操作人和时间。

### 5.3 一次分配确认在一个事务里做什么

```text
matching：锁定发票行 → 校验发票侧不超分配 → 写分配记录
        → 发布 AllocationChanged(purchase_line_ids)
task（订阅）：锁定这些子采购行对应的有效任务行
        → 按分配表重新汇总 received_* → 更新任务行状态 → 更新任务状态
提交；任一步失败整体回滚
```

已收值按分配表**重新汇总**而不是累加，重复处理同一事件结果不变。

## 6. 重新审核时的数据变化

报关单 A 来源变化后重新审核通过：

1. A 的旧任务、旧任务行置为 `superseded`（生成列变为 NULL，唯一约束释放）。
2. 对 A 本次范围内的每条子采购行：
   - 没有有效任务行 → 按新快照生成任务行（`relation=created`），已收值按分配表汇总，**原有收票进度自动延续**；
   - 已有其他报关单生成的有效任务行 → 不生成，只写 `task_line_reviews`（`relation=covered`）。
3. 分配记录不受影响：它们挂在子采购行上，不挂在任务行上。

## 7. 迁移计划

全部写入主迁移链 `backend/migrations`（当前 head `0009_simplify_supplier_groups`）。`manage upgrade`（`upgrade_unified`）先升级业务链，再升级主链，所以主链可以修改业务链创建的表。

**前置条件（第 3 步数据库收口时完成）**：当前 `upgrade_unified` 在库中没有 `alembic_version` 时，不执行主链迁移，而是按代码中的表定义直接建表并把主链标记为 head。这条路径会跳过之后迁移中对业务表的修改和数据转换。第 3 步须改为：首次建表后标记到 `0009`，再正常升级到 head；新表同时在 `entity/` 中定义并登记到元数据，保证两条路径结果一致。

| 迁移 | 模块 | 内容 |
| --- | --- | --- |
| `0010_task_invoice_lines` | task | 建 `task_invoice_lines`、`task_line_reviews`；**回填**：对现有非 `superseded` 任务，从其审核快照 `content.purchaseLines`（保存了子采购行全部字段，含报关数量、单位、金额）生成任务行，同一子采购行出现在多个有效任务时保留最早的任务，其余写 `covered`；已收值按现有分配汇总；由已停用的实时 NS 审核生成的任务没有本地行 ID，不回填，列出由人工重新审核；输出生成数、冲突数、未回填数 |
| `0011_matching_allocation_status` | matching | 调整 `invoice_purchase_allocations`；把 `invoice_purchase_link_pairs` 的记录转成 `mode=link` 的分配记录。整票关联没有数量：一条发票行只关联一条子采购行时取发票行数量和金额；一条发票行关联多条子采购行时无法自动拆分，迁移停止并列出这些记录，由人工分配后重跑（当前库中共 2 条，迁移前人工核对） |
| `0012_sync_runs` | sync | 建 `sync_runs`、`sync_cursors` |

每个迁移提供 `downgrade`；回填和数据转换在同一迁移事务内完成，失败整体回滚。上线前在业务库副本上执行并核对输出的计数。

## 8. 待确认

1. **收齐以含税金额为准**：数量只做辅助提示，不影响状态。这样处理发票单位与采购单位、报关单位不一致的情况，是否可以？
2. **金额容差**：每行 0.01 元是否合适？
3. **`closed` 是否需要人工确认**：还是全部任务行 `received` 后自动完成？

# 数据库设计

状态：**草案第 2 版，待确认**。依据[架构设计 v2](README.md)的业务规则和 `test` 分支当前表结构编写。总体规则见[后端规则](backend-rules.md)第 8 节。

## 1. 业务规则如何决定表结构

| 业务规则 | 表结构上的做法 |
| --- | --- |
| 按子采购单开票，审核不调整 | **开票单元 = 子采购行**（`purchase_order_lines.id`）。审核通过时把子采购行的开票数量、单位、含税金额**冻结**到任务行；来源以后变化不改任务行，只提示重新审核 |
| 发票单位与子采购单位一致 | 任务行只冻结一套数量和单位（子采购行的开票口径），发票按同一口径比对数量和金额 |
| 同一子采购单只生成一次任务行 | 任务行对"有效的子采购行"加唯一约束（第 4.1 节生成列）；之后其他报关单审核通过时只追加关联记录 |
| 多单一票、一票多单 | 分配表一行 = 一条发票行分给一条子采购行的数量和金额；两个方向都可以有多行 |
| 不一致时降低置信度，人工审核 | 系统比对生成**待审核的分配建议**，带置信度和逐项比对结果；单位、品名、数量、金额等不一致只降低置信度，不阻止人工通过。所有建议都要人工审核后才生效 |
| 人工比对通过后即结束 | 人工通过时可以选择"该子采购行已开完"，即使有差异也结束；全部任务行结束后任务自动完成，没有另外的关闭步骤 |
| 超开允许确认并标记 | 超过应开值的分配可以人工通过，必须填写说明；任务行带"超开"标记，可以结束 |
| 收票进度不能手工改 | 已收数量、金额、任务行是否结束，全部由已通过的分配记录汇总得出；任务行上的汇总值是缓存，可随时重算核对 |
| 重新审核不丢历史 | 旧任务和旧任务行置为 `superseded`，只读保留；新任务行按同一子采购行的分配记录重新汇总，收票进度自动延续 |
| 不删除数据 | 驳回、取消都用状态表示；停用的表停止写入，不删除 |

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

matching（发票比对）
  invoice_purchase_allocations【调整】：建议 → 人工通过 / 驳回 → （可取消）
  invoice_purchase_link_batches / _pairs【停用，数据迁入分配表】

sync（同步）
  sync_runs【新增】、sync_cursors【新增】

（历史保留，无代码读写）ns_previews、ns_target_locks、ns_audit
```

跨模块引用（只存 ID，不建外键）：

```text
task_invoice_lines.purchase_line_id           → purchase_order_lines.id
task_line_reviews.snapshot_id                 → finance_review_snapshots.id
invoice_purchase_allocations.purchase_line_id → purchase_order_lines.id
invoice_purchase_allocations.invoice_line_id  → invoice_lines.id
```

任务行和分配表**不互相引用**，两者都以 `purchase_line_id` 对齐。`task` 不读取 `matching` 的表，收票进度通过事件更新。

## 3. 现有表的处理

| 表 | 模块 | 处理 |
| --- | --- | --- |
| 母采购、子采购、报关及其明细 6 张，`customs_reconciliation_results` | source | 不变 |
| `unit_dictionary` | source | 不变 |
| `invoices`、`invoice_lines` | invoice | 不变；柠檬云 API 导入复用 `external_system/external_account/external_record_id` 去重 |
| `finance_review_snapshots`、`finance_reviews`、`finance_review_audit` | review | 不变 |
| `finance_invoice_tasks` | task | 结构不变；`status` 增加收票相关取值（第 6.2 节）；`payload` 中的行明细改由任务行表承载，保留作历史 |
| `finance_task_documents`、`finance_task_notifications`、`finance_supplier_groups` | task | 不变 |
| `invoice_purchase_allocations` | matching | **增加列**（第 4.3 节），成为唯一的比对与分配台账；预留但从未写入的 `review_*`、`customs_line_id` 列保留不用 |
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
  item_name           VARCHAR(500)  NULL,
  specification       VARCHAR(500)  NULL,
  currency            VARCHAR(20)   NULL,
  expected_quantity   DECIMAL(26,8) NULL COMMENT '应开数量（冻结，子采购行开票口径）',
  unit                VARCHAR(50)   NULL COMMENT '开票单位（冻结，与发票单位比对）',
  expected_amount     DECIMAL(24,6) NULL COMMENT '应开含税金额（冻结）；来源缺失时为空',
  received_quantity   DECIMAL(26,8) NOT NULL DEFAULT 0 COMMENT '已通过分配的数量合计（缓存）',
  received_amount     DECIMAL(24,6) NOT NULL DEFAULT 0 COMMENT '已通过分配的含税金额合计（缓存）',
  status              VARCHAR(16)   NOT NULL DEFAULT 'open',
  over_invoiced       BOOL          NOT NULL DEFAULT 0 COMMENT '已收超过应开（缓存）',
  closed_with_difference BOOL       NOT NULL DEFAULT 0 COMMENT '人工按差异结束（缓存）',
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
  CONSTRAINT ck_task_line_status CHECK (status IN ('open','partial','received','superseded'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin COMMENT='开票任务行：每条子采购行的应开与已收';
```

`expected_quantity`、`unit` 从子采购行的哪个字段冻结，见第 8 节待确认第 1 项。

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

注：当前审核范围按 `purchase_orders.customs_declaration_id`（单值）取子采购单，同一时刻一张子采购单只属于一张报关单；唯一约束主要防止来源重新同步后子采购单改挂到另一张报关单时重复生成。

### 4.3 比对与分配台账：调整 `invoice_purchase_allocations`（matching）

一行记录 = 一条发票行与一条子采购行的一次比对：先由系统生成**建议**，人工**通过**后才计入收票。

```sql
ALTER TABLE invoice_purchase_allocations
  ADD COLUMN mode            VARCHAR(16)  NOT NULL DEFAULT 'quantity' COMMENT 'quantity=按数量分配；link=整票关联转入',
  ADD COLUMN status          VARCHAR(16)  NOT NULL DEFAULT 'confirmed' COMMENT 'proposed / confirmed / rejected / cancelled',
  ADD COLUMN confidence      DECIMAL(5,2) NULL COMMENT '系统比对置信度 0-100；人工新建的分配为空',
  ADD COLUMN checks          JSON         NULL COMMENT '逐项比对结果：项目、发票值、采购值、是否一致、差额',
  ADD COLUMN proposed_by     VARCHAR(255) NULL COMMENT 'system 或操作人',
  ADD COLUMN proposed_at     DATETIME(6)  NULL,
  ADD COLUMN reviewed_by     VARCHAR(255) NULL COMMENT '人工通过或驳回的操作人',
  ADD COLUMN reviewed_at     DATETIME(6)  NULL,
  ADD COLUMN review_note     VARCHAR(300) NULL COMMENT '有不一致项、超开或按差异结束时必填',
  ADD COLUMN exceeds_expected BOOL        NOT NULL DEFAULT 0 COMMENT '通过时已超过子采购行应开值',
  ADD COLUMN closes_purchase_line BOOL    NOT NULL DEFAULT 0 COMMENT '通过时确认该子采购行已开完（含差异）',
  ADD COLUMN cancelled_by    VARCHAR(255) NULL,
  ADD COLUMN cancelled_at    DATETIME(6)  NULL,
  ADD COLUMN cancel_reason   VARCHAR(300) NULL,
  ADD COLUMN active_pair_key VARCHAR(41)
      GENERATED ALWAYS AS (IF(status IN ('proposed','confirmed'), CONCAT(invoice_line_id, ':', purchase_line_id), NULL)) STORED,
  ADD UNIQUE KEY uq_allocation_active_pair (tenant_id, active_pair_key),
  ADD KEY ix_allocation_purchase_status (tenant_id, purchase_line_id, status),
  ADD KEY ix_allocation_invoice_line_status (tenant_id, invoice_line_id, status),
  ADD KEY ix_allocation_review_queue (tenant_id, status, confidence),
  ADD CONSTRAINT ck_allocation_status CHECK (status IN ('proposed','confirmed','rejected','cancelled')),
  ADD CONSTRAINT ck_allocation_mode CHECK (mode IN ('quantity','link'));
```

- 现有记录迁移后默认 `status=confirmed`（都是人工确认过的）。
- 同一条发票行和同一条子采购行之间只能有一条有效记录（建议或已通过）；要改数量先取消再重建，历史保留。
- **只有 `confirmed` 计入收票**；`proposed` 只在审核队列中显示。
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
- 柠檬云拉票成功后，同一个同步用例接着为新发票生成比对建议（第 5 节）。

## 5. 发票比对：置信度与人工审核

### 5.1 比对项与置信度

比对规则写在 `matching` 模块的 `policy/`，结果写入建议记录的 `confidence` 和 `checks`。

| 比对项 | 权重 | 一致的条件 |
| --- | --- | --- |
| 子采购单号 | 20 | 发票备注中出现该子采购单号 |
| 销售方与供应商 | 20 | 发票销售方与子采购供应商一致 |
| 品名 | 15 | 发票商品名与子采购行品名一致 |
| 单位 | 15 | 发票单位与任务行开票单位一致 |
| 数量 | 15 | 发票数量与剩余应开数量一致 |
| 含税金额 | 15 | 发票含税金额与剩余应开金额相差不超过容差 |

- 置信度 = 一致项权重之和（0–100）。**80 以上为高**，50–79 为中，50 以下为低。权重和分档定义在 `policy/` 中，可以调整。
- **不一致只降低置信度**，不阻止人工通过；有不一致项时，通过必须填写说明。
- 全部建议都需要人工审核，系统不自动通过。高置信度的建议可以在页面上批量通过，仍记录操作人。

### 5.2 不能人工通过的情况（硬性校验）

以下情况说明数据本身有问题，人工也不能通过，只能先处理来源：

| 情况 | 原因 |
| --- | --- |
| 发票行已分配的数量或金额会超过发票行本身 | 同一张票不能重复使用 |
| 发票为作废或红冲状态 | 不能作为收票依据 |
| 发票币种与子采购币种不一致或未核实 | 金额无法比较 |
| 子采购来源在建议生成后已变化 | 比对依据过期，须重新比对 |
| 子采购行没有有效任务行（尚未审核通过） | 不在应开范围内 |

超开**不在**硬性校验中：子采购侧超过应开值时允许人工通过，必须填写说明，记录 `exceeds_expected=1`。

### 5.3 一次人工通过在一个事务里做什么

```text
matching：锁定发票行和建议 → 重新执行硬性校验 → 建议改为 confirmed，写审核人、说明
        → 发布 AllocationChanged(purchase_line_ids)
task（订阅）：锁定对应的有效任务行 → 按已通过的分配重新汇总 → 更新任务行状态 → 更新任务状态
提交；任一步失败整体回滚
```

已收值按分配表**重新汇总**而不是累加，重复处理同一事件结果不变。

## 6. 状态与汇总规则

### 6.1 任务行状态

| 状态 | 条件 |
| --- | --- |
| `open` | 还没有已通过的分配 |
| `partial` | 已有通过的分配，但未达到应开值，且没有人工按差异结束 |
| `received` | 已收数量等于应开数量且金额相差不超过容差；**或**人工通过时勾选"该子采购行已开完"；**或**已超开（`over_invoiced=1`） |
| `superseded` | 所属任务被新审核版本替代 |

- 应开金额为空（来源金额缺失）的行不能自动判断，只能由人工按差异结束。
- 容差处理发票两位小数与采购六位小数之间的舍入，默认每行 0.01 元，定义在 `task` 模块的 `policy/` 中。
- `over_invoiced`、`closed_with_difference` 是汇总得出的标记，用于页面提示和追溯，不影响"结束"。

### 6.2 任务状态

```text
documents_pending → notify_pending → awaiting_invoice → partially_received → completed
任何未完成状态 → superseded
```

- 前三个状态由现有合同、通知流程推进，不变。
- 有第一条通过的分配后进入 `partially_received`；**全部有效任务行为 `received` 时自动变为 `completed`**，不需要另外的关闭操作。
- 任务列表可按"含超开""含差异结束"筛选（由任务行标记汇总）。

## 7. 重新审核时的数据变化

报关单 A 来源变化后重新审核通过：

1. A 的旧任务、旧任务行置为 `superseded`（生成列变为 NULL，唯一约束释放）。
2. 对 A 本次范围内的每条子采购行：
   - 没有有效任务行 → 按新快照生成任务行（`relation=created`），已收值按分配表汇总，**原有收票进度自动延续**；
   - 已有其他报关单生成的有效任务行 → 不生成，只写 `task_line_reviews`（`relation=covered`）。
3. 分配记录不受影响：它们挂在子采购行上，不挂在任务行上。
4. 已完成的任务重新审核后，新任务按分配记录重新汇总；应开值没变时直接回到 `completed`。

## 8. 迁移计划

全部写入主迁移链 `backend/migrations`（当前 head `0009_simplify_supplier_groups`）。`manage upgrade`（`upgrade_unified`）先升级业务链，再升级主链，所以主链可以修改业务链创建的表。

**前置条件（第 3 步数据库收口时完成）**：当前 `upgrade_unified` 在库中没有 `alembic_version` 时，不执行主链迁移，而是按代码中的表定义直接建表并把主链标记为 head。这条路径会跳过之后迁移中对业务表的修改和数据转换。第 3 步须改为：首次建表后标记到 `0009`，再正常升级到 head；新表同时在 `entity/` 中定义并登记到元数据，保证两条路径结果一致。

| 迁移 | 模块 | 内容 |
| --- | --- | --- |
| `0010_task_invoice_lines` | task | 建 `task_invoice_lines`、`task_line_reviews`；**回填**：对现有非 `superseded` 任务，从其审核快照 `content.purchaseLines`（保存了子采购行全部字段）生成任务行，同一子采购行出现在多个有效任务时保留最早的任务，其余写 `covered`；已收值按现有分配汇总；由已停用的实时 NS 审核生成的任务没有本地行 ID，不回填，列出由人工重新审核；输出生成数、冲突数、未回填数 |
| `0011_matching_allocation_review` | matching | 调整 `invoice_purchase_allocations`，现有记录置为 `confirmed`；把 `invoice_purchase_link_pairs` 的记录转成 `mode=link` 的已通过分配。整票关联没有数量：一条发票行只关联一条子采购行时取发票行数量和金额；一条发票行关联多条子采购行时无法自动拆分，迁移停止并列出这些记录，由人工分配后重跑（当前库中共 2 条，迁移前人工核对） |
| `0012_sync_runs` | sync | 建 `sync_runs`、`sync_cursors` |

每个迁移提供 `downgrade`；回填和数据转换在同一迁移事务内完成，失败整体回滚。上线前在业务库副本上执行并核对输出的计数。

## 9. 需要同步修改的现有代码（第 5 步实施）

| 位置 | 现状 | 改为 |
| --- | --- | --- |
| `matching/policy.py` 的 `compare`、`capacity` | 用子采购**报关**数量、单位（`declaration_quantity/declaration_unit`）比对 | 按第 8 节待确认第 1 项确定的子采购开票口径比对 |
| 同上 `capacity` | 品名、单位、数量、金额任一不一致即 `allowed=false`，人工无法确认 | 只把第 5.2 节列出的情况作为硬性校验；其余不一致计入置信度，人工可通过 |
| 同上 `capacity` | 子采购剩余数量、金额不足时拒绝 | 允许超开，标记 `exceeds_expected` 并要求说明 |
| `MatchingService` | 候选在页面打开时临时计算，不保存 | 柠檬云拉票后生成并保存建议；页面打开时也可手动生成 |

## 10. 待确认

1. **"子采购单单位"指哪个字段**：子采购行上有两套数量和单位——
   - 采购数量、采购单位：`quantity`、`unit_name`，NS 字段 `custrecord_swc_subpo_item_unit`；
   - 报关数量、报关单位：`declaration_quantity`、`declaration_unit`，NS 字段 `custrecord_swc_subpo_item_bgunit`。

   现有匹配代码用的是**报关**那一套。发票上的单位和数量与哪一套一致？
2. **金额容差**：每行 0.01 元是否合适？
3. **置信度权重和分档**：第 5.1 节的权重和"80 以上为高"是否合适？

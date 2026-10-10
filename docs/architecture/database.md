# 数据库设计

状态：**已确认（2026-10-10），尚未实施**。按整条业务链路重新设计，不沿用现有表结构，不做旧数据迁移。原增量方案已归档到[历史方案](../history/database-incremental.md)。总体规则见[后端规则](backend-rules.md)第 8 节。

## 1. 已确认的决定

| 问题 | 决定 |
| --- | --- |
| 方案 | 按整条链路重新设计（本文），不在现有表上增量修改 |
| 旧数据 | 现有数据都是测试数据，**不迁移**；新表从空表开始 |
| 合同文件 | 数据库只保存共享盘路径和 SHA256，**不保存 PDF 内容** |
| 开票单元 | 子采购行；审核不调整金额，审核通过时冻结应开值 |
| 开票数量和单位 | 子采购行采购口径 `quantity`、`unit`（NS `custrecord_swc_subpo_item_unit`），与发票单位一致 |
| 同一子采购行 | 只生成一次有效任务行 |
| 发票比对 | 系统生成带置信度的建议，全部人工审核；不一致只降低置信度，不阻止人工通过 |
| 完成 | 人工通过时可按差异结束子采购行；全部结束后任务自动完成 |
| 超开 | 允许人工通过，必须填写说明，带超开标记 |
| 金额容差 | 每行 0.01 元 |
| 置信度分档 | 80 分以上高，50–79 中，50 以下低 |
| 供应商比对 | NS 子采购单上没有纳税人识别号，**先按名称比对**；主数据表不设税号列，以后有来源时再加 |

## 2. 业务规则如何决定表结构

| 业务规则 | 表结构上的做法 |
| --- | --- |
| 财务、采购共用数据 | 数据按组织共享，只按 **NS 账套**（正式 / 沙箱）区分；操作人记录在 `*_by` 字段 |
| 报关单与子采购单多对多 | 独立的关联表，单头级和行级关系都是普通行 |
| 审核冻结范围 | 审核通过时写入**审核行**（每条子采购行一行），不可修改；任务行从审核行复制应开值 |
| 只生成一次 | 任务行对"有效的子采购行"加唯一约束（生成列） |
| 多单一票、一票多单 | 分配表一行 = 一条发票行分给一条子采购行的数量和金额 |
| 收票进度不能手工改 | 已收值只由已通过的分配汇总得出；任务行上的汇总值是缓存，可按分配表重算 |
| 重新审核不丢进度 | 分配挂在子采购行上，不挂在任务行上；新任务行按同一子采购行重新汇总，进度自动延续 |
| 不删除业务记录 | 来源停用用 `is_active`；业务记录用状态（`superseded`、`rejected`、`cancelled`） |

## 3. 通用约定

- **表名以模块名开头**：`source_`、`review_`、`task_`、`invoice_`、`matching_`、`sync_`。
- **主键**：`id BIGINT UNSIGNED AUTO_INCREMENT`。外部系统 ID 单独成列，与账套组合唯一。
- **金额**：来源与分配 `DECIMAL(24,6)`；发票 `DECIMAL(18,2)`；数量 `DECIMAL(26,8)`。Python 中用 `Decimal`，接口传十进制字符串。
- **时间**：`DATETIME(6)`，存 UTC。每张表有 `created_at`、`updated_at`（下文 DDL 中用 `-- 公共列` 表示）：

  ```sql
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  ```

- **状态**：`VARCHAR(24)` + `CHECK`，与模块 `policy/` 中的状态机一致。
- **外键**：模块内建外键；**跨模块只存 ID，不建外键**，一致性由 Service 在事务中校验。
- **表选项**：`ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin`（下文省略）。单号、ID 类列区分大小写。
- **名称比较列**：需要按名称比对的表保存 `*_normalized`（规则见第 5.2 节），由写入方计算，建索引。

## 4. 表结构

共 24 张表。

```text
source   10：suppliers、companies、raw_records、parent_orders、parent_order_lines、
             purchase_orders、purchase_order_lines、customs_declarations、customs_lines、customs_purchase_links
review    2：records、lines
task      6：supplier_groups、tasks、lines、documents、notifications、events
invoice   3：raw_records、headers、lines
matching  1：allocations
sync      2：runs、cursors
```

```text
                         ┌──────────────── sync ────────────────┐
                         │ sync_runs   sync_cursors              │
                         └───────┬───────────────────────┬──────┘
                                 │写入                   │写入
                                 ▼                       ▼
source（NS 来源）                                  invoice（进项发票）
  suppliers  companies  raw_records                  raw_records
  parent_orders ─< parent_order_lines                headers ─< lines
  purchase_orders ─< purchase_order_lines  ← 开票单元          │
  customs_declarations ─< customs_lines                         │
  customs_purchase_links（报关 ↔ 子采购，单头级 + 行级）         │
        │ 门面读取                                              │ 门面读取
        ▼                                                       │
review：records ─< lines（冻结的子采购行）                      │
        │ 事件 ReviewApproved                                   │
        ▼                                                       │
task：supplier_groups                                           │
      tasks ─< lines（应开 / 已收）                             │
            ─< documents（共享盘路径）                          │
            ─< notifications（通知版本）                        │
            ─< events（状态历史）                               │
        ▲ 事件 AllocationChanged                                ▼
matching：allocations（发票行 ↔ 子采购行：建议 → 人工通过 / 驳回 → 可取消）
```

### 4.1 source：NS 来源（只由同步写入，其他模块经门面只读）

```sql
CREATE TABLE source_suppliers (
  id               BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  ns_account       VARCHAR(100) NOT NULL,
  ns_internal_id   VARCHAR(190) NOT NULL,
  name             VARCHAR(255) NOT NULL,
  name_normalized  VARCHAR(255) NOT NULL COMMENT '名称比对用，见第 5.2 节',
  is_active        BOOL NOT NULL DEFAULT 1,
  -- 公共列
  PRIMARY KEY (id),
  UNIQUE KEY uq_source_supplier_ns (ns_account, ns_internal_id),
  KEY ix_source_supplier_name (ns_account, name_normalized)
) COMMENT='供应商（NS vendor）';

CREATE TABLE source_companies (
  id               BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  ns_account       VARCHAR(100) NOT NULL,
  ns_internal_id   VARCHAR(190) NOT NULL,
  name             VARCHAR(255) NOT NULL,
  name_normalized  VARCHAR(255) NOT NULL,
  is_active        BOOL NOT NULL DEFAULT 1,
  -- 公共列
  PRIMARY KEY (id),
  UNIQUE KEY uq_source_company_ns (ns_account, ns_internal_id)
) COMMENT='采购公司（NS 子公司），与发票购买方比对';

CREATE TABLE source_raw_records (
  id               BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  ns_account       VARCHAR(100) NOT NULL,
  record_type      VARCHAR(100) NOT NULL COMMENT 'NS 记录类型；关联依据用 relation_evidence',
  ns_internal_id   VARCHAR(190) NOT NULL,
  payload          JSON NOT NULL COMMENT 'NS 原始单头和明细，或关联依据',
  payload_sha256   CHAR(64) NOT NULL,
  fetched_at       DATETIME(6) NOT NULL,
  -- 公共列
  PRIMARY KEY (id),
  UNIQUE KEY uq_source_raw_content (ns_account, record_type, ns_internal_id, payload_sha256)
) COMMENT='NS 原始数据；内容变化时追加一行，主表指向最新一行';

CREATE TABLE source_parent_orders (
  id                  BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  ns_account          VARCHAR(100) NOT NULL,
  ns_internal_id      VARCHAR(190) NOT NULL,
  ns_record_type      VARCHAR(100) NOT NULL,
  order_no            VARCHAR(150) NULL,
  order_date          DATE NULL,
  supplier_id         BIGINT UNSIGNED NULL,
  company_id          BIGINT UNSIGNED NULL,
  currency            VARCHAR(20) NULL,
  total_amount        DECIMAL(24,6) NULL,
  source_status       VARCHAR(100) NULL COMMENT 'NS 原始业务状态',
  source_modified_at  DATETIME(6) NULL,
  synced_at           DATETIME(6) NOT NULL,
  is_active           BOOL NOT NULL DEFAULT 1,
  raw_record_id       BIGINT UNSIGNED NULL,
  -- 公共列
  PRIMARY KEY (id),
  UNIQUE KEY uq_source_parent_ns (ns_account, ns_internal_id),
  KEY ix_source_parent_no (ns_account, order_no),
  CONSTRAINT fk_source_parent_supplier FOREIGN KEY (supplier_id) REFERENCES source_suppliers (id),
  CONSTRAINT fk_source_parent_company FOREIGN KEY (company_id) REFERENCES source_companies (id),
  CONSTRAINT fk_source_parent_raw FOREIGN KEY (raw_record_id) REFERENCES source_raw_records (id)
) COMMENT='母采购单';

CREATE TABLE source_parent_order_lines (
  id                BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  parent_order_id   BIGINT UNSIGNED NOT NULL,
  source_line_key   VARCHAR(190) NOT NULL COMMENT '稳定行键 transactionline:<uniquekey>',
  line_no           VARCHAR(40) NULL,
  item_code         VARCHAR(150) NULL,
  item_name         VARCHAR(500) NULL,
  declaration_name  VARCHAR(500) NULL,
  specification     VARCHAR(500) NULL,
  quantity          DECIMAL(26,8) NULL,
  unit              VARCHAR(50) NULL,
  unit_price        DECIMAL(24,8) NULL,
  amount            DECIMAL(24,6) NULL,
  is_active         BOOL NOT NULL DEFAULT 1,
  -- 公共列
  PRIMARY KEY (id),
  UNIQUE KEY uq_source_parent_line (parent_order_id, source_line_key),
  CONSTRAINT fk_source_parent_line_order FOREIGN KEY (parent_order_id) REFERENCES source_parent_orders (id)
) COMMENT='母采购行';

CREATE TABLE source_purchase_orders (
  id                      BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  ns_account              VARCHAR(100) NOT NULL,
  ns_internal_id          VARCHAR(190) NOT NULL,
  order_no                VARCHAR(150) NOT NULL COMMENT '子采购单号',
  order_date              DATE NULL,
  pl_no                   VARCHAR(100) NULL,
  parent_order_id         BIGINT UNSIGNED NULL,
  parent_relation_status  VARCHAR(24) NOT NULL DEFAULT 'unknown',
  supplier_id             BIGINT UNSIGNED NULL,
  company_id              BIGINT UNSIGNED NULL,
  currency                VARCHAR(20) NULL,
  total_amount            DECIMAL(24,6) NULL,
  detail_status           VARCHAR(24) NOT NULL DEFAULT 'pending' COMMENT '明细是否完整读取',
  source_modified_at      DATETIME(6) NULL,
  synced_at               DATETIME(6) NOT NULL,
  is_active               BOOL NOT NULL DEFAULT 1,
  raw_record_id           BIGINT UNSIGNED NULL,
  -- 公共列
  PRIMARY KEY (id),
  UNIQUE KEY uq_source_purchase_ns (ns_account, ns_internal_id),
  KEY ix_source_purchase_no (ns_account, order_no),
  KEY ix_source_purchase_pl (ns_account, pl_no),
  KEY ix_source_purchase_supplier (supplier_id),
  CONSTRAINT fk_source_purchase_parent FOREIGN KEY (parent_order_id) REFERENCES source_parent_orders (id),
  CONSTRAINT fk_source_purchase_supplier FOREIGN KEY (supplier_id) REFERENCES source_suppliers (id),
  CONSTRAINT fk_source_purchase_company FOREIGN KEY (company_id) REFERENCES source_companies (id),
  CONSTRAINT fk_source_purchase_raw FOREIGN KEY (raw_record_id) REFERENCES source_raw_records (id),
  CONSTRAINT ck_source_purchase_parent_status CHECK (parent_relation_status IN ('unknown','no_parent','linked')),
  CONSTRAINT ck_source_purchase_detail_status CHECK (detail_status IN ('pending','complete','failed'))
) COMMENT='子采购单';

CREATE TABLE source_purchase_order_lines (
  id                   BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  purchase_order_id    BIGINT UNSIGNED NOT NULL,
  source_line_key      VARCHAR(190) NOT NULL,
  line_no              VARCHAR(40) NULL,
  item_code            VARCHAR(150) NULL,
  item_name            VARCHAR(500) NULL,
  item_name_normalized VARCHAR(500) NULL COMMENT '品名比对用',
  declaration_name     VARCHAR(500) NULL COMMENT '报关品名',
  specification        VARCHAR(500) NULL,
  quantity             DECIMAL(26,8) NULL COMMENT '采购数量（开票口径）',
  unit                 VARCHAR(50) NULL COMMENT '采购单位（开票口径），NS custrecord_swc_subpo_item_unit；未返回时为空',
  declared_quantity    DECIMAL(26,8) NULL COMMENT '报关数量，只用于报关核对',
  declared_unit        VARCHAR(50) NULL,
  unit_price           DECIMAL(24,8) NULL COMMENT '含税单价',
  amount               DECIMAL(24,6) NULL COMMENT '含税金额；来源缺失时为空',
  amount_status        VARCHAR(24) NOT NULL DEFAULT 'matched' COMMENT 'matched / source_missing',
  parent_line_id       BIGINT UNSIGNED NULL,
  is_active            BOOL NOT NULL DEFAULT 1,
  -- 公共列
  PRIMARY KEY (id),
  UNIQUE KEY uq_source_purchase_line (purchase_order_id, source_line_key),
  CONSTRAINT fk_source_purchase_line_order FOREIGN KEY (purchase_order_id) REFERENCES source_purchase_orders (id),
  CONSTRAINT fk_source_purchase_line_parent FOREIGN KEY (parent_line_id) REFERENCES source_parent_order_lines (id),
  CONSTRAINT ck_source_purchase_line_amount CHECK (amount_status IN ('matched','source_missing'))
) COMMENT='子采购行：开票单元';

CREATE TABLE source_customs_declarations (
  id                    BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  ns_account            VARCHAR(100) NOT NULL,
  ns_internal_id        VARCHAR(190) NOT NULL,
  record_no             VARCHAR(150) NULL COMMENT 'CD 编号',
  declaration_no        VARCHAR(150) NULL COMMENT '真实报关单号',
  declaration_date      DATE NULL,
  declarant_company_id  BIGINT UNSIGNED NULL,
  detail_status         VARCHAR(24) NOT NULL DEFAULT 'pending',
  relation_status       VARCHAR(24) NOT NULL DEFAULT 'partial' COMMENT '关联依据完整性：partial / complete；不是审核结论',
  relation_issues       JSON NULL COMMENT '关联依据不完整的原因列表',
  content_sha256        CHAR(64) NULL COMMENT '报关单 + 关联子采购的展示内容摘要，审核比对用',
  source_modified_at    DATETIME(6) NULL,
  synced_at             DATETIME(6) NOT NULL,
  is_active             BOOL NOT NULL DEFAULT 1,
  raw_record_id         BIGINT UNSIGNED NULL,
  -- 公共列
  PRIMARY KEY (id),
  UNIQUE KEY uq_source_customs_ns (ns_account, ns_internal_id),
  KEY ix_source_customs_record (ns_account, record_no),
  KEY ix_source_customs_number (ns_account, declaration_no),
  CONSTRAINT fk_source_customs_company FOREIGN KEY (declarant_company_id) REFERENCES source_companies (id),
  CONSTRAINT fk_source_customs_raw FOREIGN KEY (raw_record_id) REFERENCES source_raw_records (id),
  CONSTRAINT ck_source_customs_detail_status CHECK (detail_status IN ('pending','complete','failed')),
  CONSTRAINT ck_source_customs_relation_status CHECK (relation_status IN ('partial','complete'))
) COMMENT='报关单';

CREATE TABLE source_customs_lines (
  id                     BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  customs_declaration_id BIGINT UNSIGNED NOT NULL,
  source_line_key        VARCHAR(190) NOT NULL,
  line_no                VARCHAR(40) NULL,
  pl_no                  VARCHAR(100) NULL,
  sales_order_no         VARCHAR(150) NULL,
  company_id             BIGINT UNSIGNED NULL,
  origin_place           VARCHAR(255) NULL,
  item_code              VARCHAR(150) NULL,
  declaration_name       VARCHAR(500) NULL,
  specification          VARCHAR(500) NULL,
  quantity               DECIMAL(26,8) NULL,
  unit                   VARCHAR(50) NULL,
  declared_quantity      DECIMAL(26,8) NULL,
  declared_unit          VARCHAR(50) NULL,
  unit_price             DECIMAL(24,8) NULL,
  amount                 DECIMAL(24,6) NULL,
  currency               VARCHAR(20) NULL,
  is_active              BOOL NOT NULL DEFAULT 1,
  -- 公共列
  PRIMARY KEY (id),
  UNIQUE KEY uq_source_customs_line (customs_declaration_id, source_line_key),
  KEY ix_source_customs_line_pl (pl_no),
  CONSTRAINT fk_source_customs_line_head FOREIGN KEY (customs_declaration_id) REFERENCES source_customs_declarations (id),
  CONSTRAINT fk_source_customs_line_company FOREIGN KEY (company_id) REFERENCES source_companies (id)
) COMMENT='报关明细';

CREATE TABLE source_customs_purchase_links (
  id                     BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  customs_declaration_id BIGINT UNSIGNED NOT NULL,
  purchase_order_id      BIGINT UNSIGNED NOT NULL,
  customs_line_id        BIGINT UNSIGNED NULL COMMENT '行级关系；只有单头级关系时为空',
  purchase_line_id       BIGINT UNSIGNED NULL,
  evidence               VARCHAR(24) NOT NULL COMMENT 'ns_reference / ns_v3 / local_packing',
  status                 VARCHAR(24) NOT NULL DEFAULT 'active' COMMENT 'active / stale',
  -- 唯一约束中可空列用 0 代替，避免多个空值绕过唯一性
  customs_line_key       BIGINT UNSIGNED GENERATED ALWAYS AS (IFNULL(customs_line_id, 0)) STORED,
  purchase_line_key      BIGINT UNSIGNED GENERATED ALWAYS AS (IFNULL(purchase_line_id, 0)) STORED,
  synced_at              DATETIME(6) NOT NULL,
  -- 公共列
  PRIMARY KEY (id),
  UNIQUE KEY uq_source_link (customs_declaration_id, purchase_order_id, customs_line_key, purchase_line_key),
  KEY ix_source_link_purchase (purchase_order_id, status),
  KEY ix_source_link_purchase_line (purchase_line_id),
  CONSTRAINT fk_source_link_customs FOREIGN KEY (customs_declaration_id) REFERENCES source_customs_declarations (id),
  CONSTRAINT fk_source_link_purchase FOREIGN KEY (purchase_order_id) REFERENCES source_purchase_orders (id),
  CONSTRAINT fk_source_link_customs_line FOREIGN KEY (customs_line_id) REFERENCES source_customs_lines (id),
  CONSTRAINT fk_source_link_purchase_line FOREIGN KEY (purchase_line_id) REFERENCES source_purchase_order_lines (id),
  CONSTRAINT ck_source_link_evidence CHECK (evidence IN ('ns_reference','ns_v3','local_packing')),
  CONSTRAINT ck_source_link_status CHECK (status IN ('active','stale'))
) COMMENT='报关单与子采购单的关联，支持多对多与行级';
```

- 报关单的审核范围 = 该报关单 `active` 关联中的全部子采购行。
- 关联依据的原始材料（原始行、Packing、母子采购身份）存为 `source_raw_records` 中 `record_type='relation_evidence'` 的记录；完整性结论写在报关单的 `relation_status`、`relation_issues`。

### 4.2 review：财务核对

```sql
CREATE TABLE review_records (
  id                     BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  ns_account             VARCHAR(100) NOT NULL,
  customs_declaration_id BIGINT UNSIGNED NOT NULL COMMENT 'source_customs_declarations.id',
  record_no              VARCHAR(150) NULL COMMENT '冗余，CD 编号',
  revision               INT NOT NULL COMMENT '同一报关单第几次审核',
  content_sha256         CHAR(64) NOT NULL COMMENT '审核时看到的内容摘要',
  status                 VARCHAR(24) NOT NULL DEFAULT 'active' COMMENT 'active / superseded',
  approved_by            VARCHAR(200) NOT NULL,
  approved_at            DATETIME(6) NOT NULL,
  note                   VARCHAR(300) NULL,
  active_declaration_id  BIGINT UNSIGNED
      GENERATED ALWAYS AS (IF(status = 'active', customs_declaration_id, NULL)) STORED,
  -- 公共列
  PRIMARY KEY (id),
  UNIQUE KEY uq_review_revision (customs_declaration_id, revision),
  UNIQUE KEY uq_review_active (active_declaration_id),
  CONSTRAINT ck_review_status CHECK (status IN ('active','superseded'))
) COMMENT='审核记录：一次审核通过一行，不可修改，全部行即审核历史';

CREATE TABLE review_lines (
  id                 BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  review_id          BIGINT UNSIGNED NOT NULL,
  purchase_order_id  BIGINT UNSIGNED NOT NULL COMMENT 'source_purchase_orders.id',
  purchase_line_id   BIGINT UNSIGNED NOT NULL COMMENT 'source_purchase_order_lines.id',
  customs_line_id    BIGINT UNSIGNED NULL COMMENT 'source_customs_lines.id',
  supplier_id        BIGINT UNSIGNED NULL COMMENT '任务分组用',
  company_id         BIGINT UNSIGNED NULL COMMENT '任务分组用',
  order_no           VARCHAR(150) NOT NULL,
  item_name          VARCHAR(500) NULL,
  specification      VARCHAR(500) NULL,
  currency           VARCHAR(20) NULL,
  quantity           DECIMAL(26,8) NULL COMMENT '冻结的采购口径数量',
  unit               VARCHAR(50) NULL,
  amount             DECIMAL(24,6) NULL COMMENT '冻结的含税金额',
  line_sha256        CHAR(64) NOT NULL COMMENT '冻结时子采购行内容摘要',
  -- 公共列
  PRIMARY KEY (id),
  UNIQUE KEY uq_review_line (review_id, purchase_line_id),
  KEY ix_review_line_purchase (purchase_line_id),
  CONSTRAINT fk_review_line_record FOREIGN KEY (review_id) REFERENCES review_records (id)
) COMMENT='审核冻结的子采购行范围，不可修改';
```

- **待审核不存表**：报关单没有 `active` 审核记录，或当前 `content_sha256` 与 `active` 记录不一致，即为待审核，由查询得出。
- **不保存审核预览**：列表接口返回每张报关单的 `content_sha256`；审核时前端回传，后端锁定后重新计算，一致才写入。

### 4.3 task：开票跟进

```sql
CREATE TABLE task_supplier_groups (
  id             BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  supplier_id    BIGINT UNSIGNED NOT NULL COMMENT 'source_suppliers.id',
  group_name     VARCHAR(200) NOT NULL,
  chat_id        VARCHAR(190) NOT NULL COMMENT '企微群 ID',
  owner_name     VARCHAR(100) NOT NULL,
  owner_userid   VARCHAR(190) NOT NULL,
  enabled        BOOL NOT NULL DEFAULT 1,
  version        INT NOT NULL DEFAULT 1 COMMENT '乐观锁',
  updated_by     VARCHAR(200) NOT NULL,
  -- 公共列
  PRIMARY KEY (id),
  UNIQUE KEY uq_task_supplier_group (supplier_id)
) COMMENT='供应商默认企微群';

CREATE TABLE task_tasks (
  id                     BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  review_id              BIGINT UNSIGNED NOT NULL COMMENT 'review_records.id',
  ns_account             VARCHAR(100) NOT NULL,
  customs_declaration_id BIGINT UNSIGNED NOT NULL COMMENT '冗余，便于按报关单查询',
  record_no              VARCHAR(150) NULL COMMENT '冗余，CD 编号',
  supplier_id            BIGINT UNSIGNED NULL,
  company_id             BIGINT UNSIGNED NULL,
  currency               VARCHAR(20) NULL,
  group_key              CHAR(64) NOT NULL COMMENT '供应商 + 公司 + 币种的分组键；身份缺失时按子采购单隔离',
  status                 VARCHAR(24) NOT NULL DEFAULT 'documents_pending',
  completed_at           DATETIME(6) NULL,
  -- 公共列
  PRIMARY KEY (id),
  UNIQUE KEY uq_task_review_group (review_id, group_key),
  KEY ix_task_status_supplier (status, supplier_id),
  KEY ix_task_declaration (customs_declaration_id),
  CONSTRAINT ck_task_status CHECK (status IN (
    'documents_pending','notify_pending','awaiting_invoice','partially_received','completed','superseded'))
) COMMENT='开票任务：审核通过后按 供应商 × 采购公司 × 币种 分组';

CREATE TABLE task_lines (
  id                      BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  task_id                 BIGINT UNSIGNED NOT NULL,
  review_line_id          BIGINT UNSIGNED NOT NULL COMMENT 'review_lines.id，应开值来源',
  purchase_order_id       BIGINT UNSIGNED NOT NULL,
  purchase_line_id        BIGINT UNSIGNED NOT NULL COMMENT '开票单元',
  expected_quantity       DECIMAL(26,8) NULL,
  unit                    VARCHAR(50) NULL,
  expected_amount         DECIMAL(24,6) NULL COMMENT '来源金额缺失时为空，只能人工按差异结束',
  received_quantity       DECIMAL(26,8) NOT NULL DEFAULT 0 COMMENT '已通过分配合计（缓存）',
  received_amount         DECIMAL(24,6) NOT NULL DEFAULT 0,
  status                  VARCHAR(24) NOT NULL DEFAULT 'open',
  over_invoiced           BOOL NOT NULL DEFAULT 0,
  closed_with_difference  BOOL NOT NULL DEFAULT 0,
  active_purchase_line_id BIGINT UNSIGNED
      GENERATED ALWAYS AS (IF(status = 'superseded', NULL, purchase_line_id)) STORED,
  -- 公共列
  PRIMARY KEY (id),
  UNIQUE KEY uq_task_line_active (active_purchase_line_id),
  UNIQUE KEY uq_task_line_task (task_id, purchase_line_id),
  KEY ix_task_line_purchase (purchase_line_id),
  CONSTRAINT fk_task_line_task FOREIGN KEY (task_id) REFERENCES task_tasks (id),
  CONSTRAINT ck_task_line_status CHECK (status IN ('open','partial','received','superseded'))
) COMMENT='任务行：每条子采购行的应开与已收';

CREATE TABLE task_documents (
  id                 BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  task_id            BIGINT UNSIGNED NOT NULL,
  purchase_order_id  BIGINT UNSIGNED NOT NULL,
  order_no           VARCHAR(150) NOT NULL,
  ns_environment     VARCHAR(100) NOT NULL COMMENT '合同下载的 NS 环境',
  ns_file_id         VARCHAR(40) NULL,
  filename           VARCHAR(255) NULL,
  sha256             CHAR(64) NULL,
  archive_path       VARCHAR(2048) NULL COMMENT '共享盘路径；数据库不保存文件内容',
  status             VARCHAR(24) NOT NULL DEFAULT 'pending' COMMENT 'pending / archived / failed',
  error_message      VARCHAR(500) NULL,
  archived_at        DATETIME(6) NULL,
  -- 公共列
  PRIMARY KEY (id),
  UNIQUE KEY uq_task_document (task_id, purchase_order_id),
  CONSTRAINT fk_task_document_task FOREIGN KEY (task_id) REFERENCES task_tasks (id),
  CONSTRAINT ck_task_document_status CHECK (status IN ('pending','archived','failed'))
) COMMENT='子采购合同：只记录共享盘路径';

CREATE TABLE task_notifications (
  id                  BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  task_id             BIGINT UNSIGNED NOT NULL,
  version             INT NOT NULL,
  channel             VARCHAR(24) NOT NULL DEFAULT 'manual' COMMENT 'manual / wecom',
  chat_id             VARCHAR(190) NULL,
  recipient_name      VARCHAR(200) NULL,
  content             TEXT NOT NULL,
  status              VARCHAR(24) NOT NULL DEFAULT 'draft' COMMENT 'draft / sent / failed',
  sent_by             VARCHAR(200) NULL,
  sent_at             DATETIME(6) NULL,
  channel_message_id  VARCHAR(190) NULL COMMENT '企微回执，接入自动发送后填写',
  created_by          VARCHAR(200) NOT NULL,
  -- 公共列
  PRIMARY KEY (id),
  UNIQUE KEY uq_task_notification_version (task_id, version),
  CONSTRAINT fk_task_notification_task FOREIGN KEY (task_id) REFERENCES task_tasks (id),
  CONSTRAINT ck_task_notification_channel CHECK (channel IN ('manual','wecom')),
  CONSTRAINT ck_task_notification_status CHECK (status IN ('draft','sent','failed'))
) COMMENT='供应商开票通知：每次保存一个版本';

CREATE TABLE task_events (
  id           BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  task_id      BIGINT UNSIGNED NOT NULL,
  from_status  VARCHAR(24) NULL,
  to_status    VARCHAR(24) NOT NULL,
  reason       VARCHAR(300) NULL,
  actor        VARCHAR(200) NOT NULL COMMENT '操作人或 system',
  occurred_at  DATETIME(6) NOT NULL,
  -- 公共列
  PRIMARY KEY (id),
  KEY ix_task_event_task (task_id, occurred_at),
  CONSTRAINT fk_task_event_task FOREIGN KEY (task_id) REFERENCES task_tasks (id)
) COMMENT='任务状态历史，只追加';
```

同一子采购行关联的全部报关单 = `review_lines` 中该 `purchase_line_id` 所在的全部 `active` 审核，经 review 门面查询，不另建关联表。

### 4.4 invoice：进项发票

```sql
CREATE TABLE invoice_raw_records (
  id              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  source          VARCHAR(24) NOT NULL COMMENT 'lemon_open2 / lemon_excel',
  lemon_account   VARCHAR(100) NOT NULL,
  external_id     VARCHAR(190) NOT NULL COMMENT 'API 记录 ID；Excel 为发票去重键',
  payload         JSON NOT NULL,
  payload_sha256  CHAR(64) NOT NULL,
  fetched_at      DATETIME(6) NOT NULL,
  -- 公共列
  PRIMARY KEY (id),
  UNIQUE KEY uq_invoice_raw_content (source, lemon_account, external_id, payload_sha256)
) COMMENT='柠檬云原始数据';

CREATE TABLE invoice_headers (
  id                     BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  source                 VARCHAR(24) NOT NULL COMMENT '最近一次写入来源 lemon_open2 / lemon_excel',
  lemon_account          VARCHAR(100) NOT NULL,
  external_id            VARCHAR(190) NULL COMMENT '柠檬云 API 记录 ID',
  invoice_code           VARCHAR(50) NULL COMMENT '数电发票为空',
  invoice_no             VARCHAR(100) NOT NULL,
  invoice_key            VARCHAR(160) NOT NULL COMMENT '发票代码 + 号码，Excel 与 API 导入共用的去重键',
  invoice_date           DATE NULL,
  invoice_type           VARCHAR(100) NULL,
  business_type          VARCHAR(100) NULL COMMENT '例如：采购固定资产',
  status                 VARCHAR(24) NOT NULL DEFAULT 'normal' COMMENT 'normal / red_offset / void / unknown',
  seller_name            VARCHAR(255) NULL,
  seller_name_normalized VARCHAR(255) NULL,
  seller_tax_no          VARCHAR(100) NULL COMMENT '票面信息，保存备用',
  buyer_name             VARCHAR(255) NULL,
  buyer_name_normalized  VARCHAR(255) NULL,
  buyer_tax_no           VARCHAR(100) NULL,
  currency               VARCHAR(20) NOT NULL DEFAULT 'CNY',
  amount_excluding_tax   DECIMAL(18,2) NULL,
  tax_amount             DECIMAL(18,2) NULL,
  amount_including_tax   DECIMAL(18,2) NULL,
  remark                 TEXT NULL COMMENT '备注；比对子采购单号',
  raw_record_id          BIGINT UNSIGNED NULL,
  imported_at            DATETIME(6) NOT NULL,
  -- 公共列
  PRIMARY KEY (id),
  UNIQUE KEY uq_invoice_key (lemon_account, invoice_key),
  KEY ix_invoice_date (invoice_date),
  KEY ix_invoice_seller (seller_name_normalized),
  CONSTRAINT fk_invoice_raw FOREIGN KEY (raw_record_id) REFERENCES invoice_raw_records (id),
  CONSTRAINT ck_invoice_status CHECK (status IN ('normal','red_offset','void','unknown'))
) COMMENT='进项发票';

CREATE TABLE invoice_lines (
  id                    BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  invoice_id            BIGINT UNSIGNED NOT NULL,
  source_line_key       VARCHAR(190) NOT NULL,
  line_no               VARCHAR(40) NULL,
  item_name             VARCHAR(500) NULL,
  item_name_normalized  VARCHAR(500) NULL,
  specification         VARCHAR(500) NULL,
  quantity              DECIMAL(26,8) NULL,
  unit                  VARCHAR(50) NULL,
  unit_price            DECIMAL(24,8) NULL,
  amount_excluding_tax  DECIMAL(18,2) NULL,
  tax_rate              DECIMAL(8,6) NULL,
  tax_amount            DECIMAL(18,2) NULL,
  amount_including_tax  DECIMAL(18,2) NULL,
  -- 公共列
  PRIMARY KEY (id),
  UNIQUE KEY uq_invoice_line (invoice_id, source_line_key),
  CONSTRAINT fk_invoice_line_header FOREIGN KEY (invoice_id) REFERENCES invoice_headers (id)
) COMMENT='发票行';
```

同一张发票先用 Excel 导入、后被 API 拉到时，按 `invoice_key` 识别为同一张，更新 `source`、`external_id`，不重复建行。

### 4.5 matching：发票比对

```sql
CREATE TABLE matching_allocations (
  id                    BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  invoice_id            BIGINT UNSIGNED NOT NULL COMMENT 'invoice_headers.id',
  invoice_line_id       BIGINT UNSIGNED NOT NULL COMMENT 'invoice_lines.id',
  purchase_line_id      BIGINT UNSIGNED NOT NULL COMMENT 'source_purchase_order_lines.id',
  quantity              DECIMAL(26,8) NOT NULL,
  amount                DECIMAL(24,6) NOT NULL COMMENT '分配的含税金额',
  status                VARCHAR(24) NOT NULL DEFAULT 'proposed' COMMENT 'proposed / confirmed / rejected / cancelled',
  confidence            DECIMAL(5,2) NULL COMMENT '0-100；人工新建时为空',
  checks                JSON NULL COMMENT '逐项比对：项目、发票值、采购值、结果、差额',
  exceeds_expected      BOOL NOT NULL DEFAULT 0,
  closes_purchase_line  BOOL NOT NULL DEFAULT 0 COMMENT '人工确认该子采购行已开完（含差异）',
  proposed_by           VARCHAR(200) NOT NULL COMMENT 'system 或操作人',
  proposed_at           DATETIME(6) NOT NULL,
  reviewed_by           VARCHAR(200) NULL,
  reviewed_at           DATETIME(6) NULL,
  review_note           VARCHAR(300) NULL COMMENT '有不一致项、超开或按差异结束时必填',
  cancelled_by          VARCHAR(200) NULL,
  cancelled_at          DATETIME(6) NULL,
  cancel_reason         VARCHAR(300) NULL,
  request_id            CHAR(36) NOT NULL COMMENT '幂等',
  active_pair_key       VARCHAR(41)
      GENERATED ALWAYS AS (IF(status IN ('proposed','confirmed'),
                              CONCAT(invoice_line_id, ':', purchase_line_id), NULL)) STORED,
  -- 公共列
  PRIMARY KEY (id),
  UNIQUE KEY uq_matching_request (request_id),
  UNIQUE KEY uq_matching_active_pair (active_pair_key),
  KEY ix_matching_purchase (purchase_line_id, status),
  KEY ix_matching_invoice_line (invoice_line_id, status),
  KEY ix_matching_queue (status, confidence),
  CONSTRAINT ck_matching_status CHECK (status IN ('proposed','confirmed','rejected','cancelled'))
) COMMENT='发票行与子采购行的比对与分配';
```

只有 `confirmed` 计入收票；`proposed` 只在审核队列显示。

### 4.6 sync：同步

```sql
CREATE TABLE sync_runs (
  id             BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  source         VARCHAR(32) NOT NULL COMMENT 'ns_customs / ns_purchase / lemon_invoice',
  account        VARCHAR(100) NOT NULL COMMENT 'NS 账套或柠檬云账套',
  trigger_type   VARCHAR(16) NOT NULL COMMENT 'schedule / manual',
  status         VARCHAR(16) NOT NULL COMMENT 'running / succeeded / partial / failed',
  window_start   DATETIME(6) NULL,
  window_end     DATETIME(6) NULL,
  fetched_count  INT NOT NULL DEFAULT 0,
  created_count  INT NOT NULL DEFAULT 0,
  updated_count  INT NOT NULL DEFAULT 0,
  failed_count   INT NOT NULL DEFAULT 0,
  message        TEXT NULL COMMENT '中文结果或失败原因，不含凭据',
  started_by     VARCHAR(200) NOT NULL COMMENT '操作人或 scheduler',
  started_at     DATETIME(6) NOT NULL,
  finished_at    DATETIME(6) NULL,
  -- 公共列
  PRIMARY KEY (id),
  KEY ix_sync_run_source (source, account, started_at),
  CONSTRAINT ck_sync_run_status CHECK (status IN ('running','succeeded','partial','failed')),
  CONSTRAINT ck_sync_run_trigger CHECK (trigger_type IN ('schedule','manual'))
) COMMENT='同步运行记录';

CREATE TABLE sync_cursors (
  source            VARCHAR(32) NOT NULL,
  account           VARCHAR(100) NOT NULL,
  last_modified_at  DATETIME(6) NULL COMMENT '已完整处理的来源修改时间水位',
  last_run_id       BIGINT UNSIGNED NULL,
  -- 公共列
  PRIMARY KEY (source, account),
  CONSTRAINT fk_sync_cursor_run FOREIGN KEY (last_run_id) REFERENCES sync_runs (id)
) COMMENT='增量同步水位';
```

- 同一来源同一账套同时只运行一个同步：MySQL 命名锁 `GET_LOCK`（复用现有 `acquire_sync_lock`）。
- 只有整批成功才推进水位；失败时下次重拉，靠来源表唯一约束去重。

## 5. 发票比对规则

规则写在 `matching` 模块的 `policy/`；权重、分档、容差、名称规范化集中定义在同一个文件中。

### 5.1 比对项与置信度

| 比对项 | 权重 | 一致 | 部分一致（得一半分） |
| --- | --- | --- | --- |
| 子采购单号 | 15 | 发票备注中出现该子采购单号 | — |
| 销售方与供应商 | 15 | 规范化名称相同 | 一方包含另一方 |
| 购买方与采购公司 | 10 | 规范化名称相同 | 一方包含另一方 |
| 品名 | 15 | 规范化品名相同 | 一方包含另一方 |
| 单位 | 15 | 发票单位与子采购单位相同 | — |
| 数量 | 15 | 发票数量等于子采购剩余应开数量 | — |
| 含税金额 | 15 | 与剩余应开金额相差不超过 0.01 元 | — |

- 置信度 = 各项得分之和（0–100）；80 以上为高，50–79 为中，50 以下为低。
- 子采购单位为空（NS 未返回）时，单位项记为不一致，比对结果注明"子采购单位缺失"。
- 不一致项只降低置信度；人工通过时如有不一致项，必须填写说明。
- 全部建议都要人工审核，系统不自动通过；高置信度建议可在页面上批量通过，仍记录操作人。

### 5.2 名称规范化

供应商、公司、品名比对前统一处理，写入各表的 `*_normalized` 列：

1. Unicode NFKC 规范化（全角转半角）；
2. 去掉全部空白；
3. 中英文括号统一为半角括号；
4. 英文字母转小写。

不做模糊相似度计算。以后取得 NS 供应商税号时，在 `source_suppliers` 增加税号列，销售方比对改为税号优先。

### 5.3 不能人工通过的情况

| 情况 | 原因 |
| --- | --- |
| 发票行已分配的数量或金额会超过发票行本身 | 同一张票不能重复使用 |
| 发票为作废或红冲 | 不能作为收票依据 |
| 发票币种与子采购币种不一致或未知 | 金额无法比较 |
| 子采购行内容在建议生成后已变化 | 比对依据过期，须重新比对 |
| 子采购行没有有效任务行 | 不在已审核的应开范围内 |

超开不在此列：允许人工通过，必须填写说明，记录 `exceeds_expected=1`。

## 6. 状态规则

### 6.1 任务行

| 状态 | 条件 |
| --- | --- |
| `open` | 没有已通过的分配 |
| `partial` | 有已通过的分配，未达到应开值，且未按差异结束 |
| `received` | 已收数量等于应开数量且金额相差不超过 0.01 元；或人工通过时勾选"已开完"；或已超开 |
| `superseded` | 所属任务被新审核替代 |

应开金额为空的行只能由人工按差异结束。`over_invoiced`、`closed_with_difference` 是汇总得出的标记，不影响结束。

### 6.2 任务

```text
documents_pending → notify_pending → awaiting_invoice → partially_received → completed
任何未完成状态 → superseded
```

- 合同全部归档 → `notify_pending`；登记通知已发送 → `awaiting_invoice`。
- 有第一条通过的分配 → `partially_received`；全部有效任务行 `received` → `completed`，写 `completed_at`。
- 每次状态变化写 `task_events`。

## 7. 整条链路的数据流

| 步骤 | 触发 | 写入（同一事务） |
| --- | --- | --- |
| 1 拉取 NS | 定时 / 手动 | `sync_runs`；`source_*` 主数据、单据、明细、关联、原始数据；报关单 `content_sha256`；推进 `sync_cursors` |
| 2 财务审核 | 财务审核通过（回传 `content_sha256`） | 旧 `active` 审核置 `superseded`；`review_records`、`review_lines`；→ 事件 `ReviewApproved` |
| 3 生成任务 | 事件 `ReviewApproved` | 该报关单旧任务、旧任务行置 `superseded`；`task_tasks`、`task_lines`（已有有效行的子采购行跳过）、`task_events` |
| 4 备合同 | 采购操作 | NS 下载、写共享盘在事务外；`task_documents`；全部归档 → 任务 `notify_pending` |
| 5 通知供应商 | 采购保存、登记发送 | `task_notifications`；登记发送 → 任务 `awaiting_invoice` |
| 6 拉取发票 | 定时 / 手动 | `sync_runs`、`invoice_*`；推进 `sync_cursors` |
| 7 生成比对建议 | 拉票完成后 | `matching_allocations`（`proposed`，带置信度和比对结果） |
| 8 人工比对 | 财务通过 / 驳回 | `matching_allocations` → `confirmed` / `rejected`；→ 事件 `AllocationChanged` |
| 9 更新进度 | 事件 `AllocationChanged` | 按已通过分配重新汇总 `task_lines`；任务状态；`task_events` |

## 8. 主要查询

| 查询 | 走的表与索引 |
| --- | --- |
| 待审核报关单 | `source_customs_declarations` 左连接 `review_records.uq_review_active`，比较 `content_sha256` |
| 报关单审核范围 | `source_customs_purchase_links`（`customs_declaration_id`）→ `source_purchase_order_lines` |
| 采购待办任务 | `task_tasks.ix_task_status_supplier` |
| 子采购行关联的报关单 | `review_lines.ix_review_line_purchase` → `review_records` |
| 比对审核队列 | `matching_allocations.ix_matching_queue` |
| 任务收票明细 | `task_lines`（`task_id`）→ `matching_allocations.ix_matching_purchase` → `invoice_lines` |

注："待审核报关单"一行查询跨了 source 与 review 两个模块的表。按模块边界，由 review 经 source 门面取报关单列表和摘要，再与自己的审核记录比对，不在 SQL 中直接连接对方的表。

## 9. 建表与上线

- **不做数据迁移**。新表在业务库中从空表开始，旧表不再被新代码读写。
- **一条新的迁移链**：`backend/migrations` 从 `0001_baseline` 重新开始，一次创建第 4 节全部表；版本表改名为 `schema_version`，与旧的 `alembic_version`、`business_alembic_version` 不冲突。表定义同时写在各模块 `entity/` 中，测试比对两者一致。
- **旧迁移链**（现 `backend/migrations`、`backend/business_migrations`）和旧表定义随各模块切换删除，代码历史保留在 Git 中。
- **旧表**：代码不删除数据库中的旧表。全部模块切换完成后提供旧表清单，由管理员确认后手工删除；也可以直接新建空库使用。
- **实施顺序**（架构第 4 步，每个模块一个 PR，按依赖顺序）：source → review → task → invoice → match → sync。每个模块切换时同时改为分层目录，并调整调用它的门面；之后的模块从新表读取。

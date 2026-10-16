# 数据库设计

状态：**v2 初版已确认（2026-10-10）；第 3 步建立基线迁移 `backend/migrations/versions/0001_baseline.py`，各模块在第 4 步切换到新表**。初版不迁移旧模块测试数据；本次在已有 v2 结构上追加版本与证据设计，保留 v2 台账。原增量方案已归档到[历史方案](../history/database-incremental.md)。总体规则见[后端规则](backend-rules.md)第 8 节。

**2026-10-15 修订口径**：本次修订起点为 `test/e7422b7` 的 24 张表及迁移 `0001`—`0004`；当前工作区已完成第 10 节 A—D，追加 `0005`—`0009`，共 26 张业务表；另以 `0010`—`0015` 补齐字段中文备注，保留原类型、约束和数据。第 4 节保留初版表结构说明，新增字段与两张版本表见第 10 节；当前逐字段解释见[表设计与字段字典](../mysql/current-data-dictionary.md)。2026-10-16 追加 `0016_sync_lemon_bindings`，共 27 张业务表；open2 已有账号绑定已实现，发票拉取、定时同步与目标环境部署尚待核对或接入，不能据代码认定已上线。原“不迁移”仅指旧模块测试数据；本次补强保留已进入 v2 新表的审核、分配和审计。

## 1. 已确认的决定

| 问题 | 决定 |
| --- | --- |
| 方案 | 按整条链路重新设计（本文），不在现有表上增量修改 |
| 旧数据 | 初次 v2 切换不迁移旧模块测试数据；本次版本补强保留 v2 新表已有记录并准确回填或标记待复核 |
| 合同文件 | 数据库只保存共享盘路径和 SHA256，**不保存 PDF 内容** |
| 开票单元 | 子采购行；审核不调整金额，审核通过时冻结应开值 |
| 开票数量和单位 | 采用子采购行采购口径 quantity、unit（NS `custrecord_swc_subpo_item_unit`）；不同发票单位按第 10.5 节有据换算 |
| 同一子采购行 | 只生成一次有效任务行 |
| 发票比对 | 建议全部人工审核；名称等可解释差异允许说明通过，身份、币种、版本、单位换算与发票额度必须符合硬条件 |
| 币种 | 子采购继承同账套明确关联的母采购币种；本期柠檬云人民币进项票在适配时明确写入 CNY；不做跨币种换算 |
| 完成 | 人工通过时可按差异结束子采购行；全部结束后任务自动完成 |
| 超开 | 允许人工通过并说明；只记录超开标记，不自动视为全部开完（已实施） |
| 金额容差 | 每行 0.01 元 |
| 置信度分档 | 80 分以上高，50–79 中，50 以下低 |
| 供应商比对 | NS 子采购单上没有纳税人识别号，**先按名称比对**；主数据表不设税号列，以后有来源时再加 |

## 2. 业务规则如何决定表结构

| 业务规则 | 表结构上的做法 |
| --- | --- |
| 财务、采购共用数据 | 数据按组织共享，只按 **NS 账套**（正式 / 沙箱）区分；操作人记录在 `*_by` 字段 |
| 报关单与子采购单多对多 | 独立的关联表，单头级和行级关系都是普通行 |
| 审核冻结范围 | 审核行不可修改；`review_purchase_bases` 管理跨报关单的子采购行依据版本，任务引用当前依据 |
| 只生成一次 | 任务行对"有效的子采购行"加唯一约束（生成列） |
| 多单一票、一票多单 | 分配表一行 = 一条发票行分给一条子采购行的数量和金额 |
| 收票进度不能手工改 | 已收值只由已通过的分配汇总得出；任务行上的汇总值是缓存，可按分配表重算 |
| 重新审核不丢进度 | 分配保留子采购行身份与原依据版本；后继任务按口径兼容的有效分配重新汇总，不复制旧缓存或旧差异结束标记 |
| 不删除业务记录 | 来源停用用 `is_active`；业务记录用状态（`superseded`、`rejected`、`cancelled`） |

## 3. 通用约定

- **表名以模块名开头**：`source_`、`review_`、`task_`、`invoice_`、`matching_`、`sync_`。
- **主键**：`id BIGINT UNSIGNED AUTO_INCREMENT`。外部系统 ID 单独成列，与账套组合唯一。
- **金额**：来源与分配 `DECIMAL(24,6)`；发票 `DECIMAL(18,2)`；数量 `DECIMAL(26,8)`。Python 中用 `Decimal`，接口传十进制字符串。
- **时间**：`DATETIME(6)`，存 UTC。每张表有 `created_at`、`updated_at`（下文 DDL 中用 `-- 公共列` 表示）：

  ```sql
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  ```

  `updated_at` 由 DAO 在每次更新时写入，不使用 MySQL 专有的 `ON UPDATE`，保证 SQLite 测试与 MySQL 行为一致。

- **状态**：`VARCHAR(24)` + `CHECK`，与模块 `policy/` 中的状态机一致。
- **外键**：模块内建外键；**跨模块只存 ID，不建外键**，一致性由 Service 在事务中校验。
- **表选项**：`ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin`（下文省略）。单号、ID 类列区分大小写。
- **名称比较列**：需要按名称比对的表保存 `*_normalized`（规则见第 5.2 节），由写入方计算，建索引。
- **生成列**：只用标准 `CASE`、`COALESCE` 表达式（MySQL 与 SQLite 都支持），不用 `IF()`、`IFNULL()`、`CONCAT()`。

## 4. 表结构

以下为基线 24 张表。第 10 节已新增 `review_purchase_bases`、`invoice_versions`，另见第 11 节账号绑定表，当前共 27 张；已执行的 v2 迁移与业务记录保留，旧模块迁移代码已退役。

```text
source   10：suppliers、companies、raw_records、parent_orders、parent_order_lines、
             purchase_orders、purchase_order_lines、customs_declarations、customs_lines、customs_purchase_links
review    2：records、lines
task      6：supplier_groups、tasks、lines、documents、notifications、events
invoice   3：raw_records、headers、items
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
  parent_orders ─< parent_order_lines                headers ─< items
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
  exchange_rate       DECIMAL(28,12) NULL COMMENT '母采购汇率（NS exchangerate，迁移 0004）',
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
  currency                VARCHAR(20) NULL COMMENT '取自母采购单（迁移 0004）',
  currency_source         VARCHAR(24) NOT NULL DEFAULT 'unresolved' COMMENT 'parent_order / unresolved（迁移 0004）',
  currency_issue          VARCHAR(300) NULL COMMENT '币种待核实原因（迁移 0004）',
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
  customs_line_key       BIGINT UNSIGNED GENERATED ALWAYS AS (COALESCE(customs_line_id, 0)) STORED,
  purchase_line_key      BIGINT UNSIGNED GENERATED ALWAYS AS (COALESCE(purchase_line_id, 0)) STORED,
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
      GENERATED ALWAYS AS (CASE WHEN status = 'active' THEN customs_declaration_id END) STORED,
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
  review_revision        INT NOT NULL DEFAULT 1 COMMENT '生成任务的审核版本（迁移 0003）',
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
      GENERATED ALWAYS AS (CASE WHEN status <> 'superseded' THEN purchase_line_id END) STORED,
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
  sender_name         VARCHAR(100) NULL COMMENT '负责发送的员工（迁移 0003）',
  note                VARCHAR(500) NULL COMMENT '人工登记发送说明（迁移 0003）',
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

CREATE TABLE invoice_items (
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
  UNIQUE KEY uq_invoice_item (invoice_id, source_line_key),
  CONSTRAINT fk_invoice_item_header FOREIGN KEY (invoice_id) REFERENCES invoice_headers (id)
) COMMENT='发票行';
```

当前 Excel 导入按同票内容摘要去重：相同则跳过，不同则整批拒绝；尚未接入 API 更新。未来 Excel 与 API 对齐经核实的账套命名空间后，按 `invoice_key` 识别业务同票；内容变化追加第 10.4 节的不可变发票版本，禁止原地覆盖已确认依据或按显示行号猜测明细对应关系。

### 4.5 matching：发票比对

```sql
CREATE TABLE matching_allocations (
  id                    BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  invoice_id            BIGINT UNSIGNED NOT NULL COMMENT 'invoice_headers.id',
  invoice_item_id       BIGINT UNSIGNED NOT NULL COMMENT 'invoice_items.id',
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
  active_invoice_item_id BIGINT UNSIGNED
      GENERATED ALWAYS AS (CASE WHEN status IN ('proposed','confirmed') THEN invoice_item_id END) STORED,
  -- 公共列
  PRIMARY KEY (id),
  UNIQUE KEY uq_matching_request (request_id),
  UNIQUE KEY uq_matching_active_pair (active_invoice_item_id, purchase_line_id),
  KEY ix_matching_purchase (purchase_line_id, status),
  KEY ix_matching_invoice_item (invoice_item_id, status),
  KEY ix_matching_queue (status, confidence),
  CONSTRAINT ck_matching_status CHECK (status IN ('proposed','confirmed','rejected','cancelled'))
) COMMENT='发票行与子采购行的比对与分配';
```

当前只有 `confirmed` 计入收票，`proposed` 不占额度。第 10 节补强后，`confirmed` 还须区分有效、待复核和失效：未取消的确认继续保留占用，只有有效且口径兼容的确认计入有效收票。

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
- `last_modified_at` 仅适用于 NS 等确实提供修改时间的来源；同时间戳采用包含边界重拉、稳定 ID 排序与去重，不用严格大于时间戳跳过同刻记录。柠檬云 open2 使用开票日期窗口和历史回扫，不能把 `EntryDate` 当作已经核实的修改时间水位。

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
| 数量 | 15 | 本次建议的采购口径数量落在该行剩余应开范围内，且未超过发票剩余数量 | — |
| 含税金额 | 15 | 本次分配金额符合双方剩余范围；整行结束时尾差不超过 0.01 元 | — |

- 置信度 = 各项得分之和（0–100）；80 以上为高，50–79 为中，50 以下为低。
- 数量、金额按本次分配评估，正常分次收票或一票分多单不因整票不等于整单剩余值而被判不一致；该评分规则已实施。
- 子采购单位为空时标记待核实；不同单位须有第 10.5 节的换算依据。评分不替代硬校验。
- 可解释的不一致项降低置信度，人工通过时填写说明；硬条件不满足时，即使高分或填写说明也不能通过。
- 全部建议都要人工审核，系统不自动通过；高置信度建议可在页面上批量通过，仍记录操作人。

### 5.2 名称规范化

供应商、公司、品名比对前统一处理，写入各表的 `*_normalized` 列：

1. Unicode NFKC 规范化（全角转半角）；
2. 去掉全部空白；
3. 中英文括号统一为半角括号；
4. 英文字母转小写。

不做模糊相似度计算。以后取得 NS 供应商税号时，在 `source_suppliers` 增加税号列，销售方比对改为税号优先。

- 发票未提供购买方（柠檬云 Excel 不含该列）时，购买方一项得 0 分，但不算作需要填写说明的不一致项（2026-10-15）。

### 5.3 不能人工通过的情况

| 情况 | 原因 |
| --- | --- |
| 发票行已分配的数量或金额会超过发票行本身 | 同一张票不能重复使用 |
| 发票为作废或红冲 | 不能作为收票依据 |
| 发票状态未知或明细尚不完整 | 保存来源并补全，不能以未知状态直接确认（已统一校验） |
| 发票币种与有效审核依据的币种不一致或未知 | 本期柠檬云通道固定 CNY；子采购继承母单币种，真实无母单等异常经财务有据核实后冻结于 review；读源失败须重试，不能伪装成正常继承 |
| 子采购来源、有效审核依据或发票版本已变化 | 旧建议过期；确认时重新加锁核实，不能只比较最新采购行摘要 |
| 单位缺失或不同单位没有有效换算依据 | 不能直接累计不同口径数量；不靠说明文字跳过 |
| 子采购行没有有效任务行 | 不在已审核的应开范围内 |

超开不在此列：允许人工通过，必须填写说明，记录 `exceeds_expected=1`。

## 6. 状态规则

### 6.1 任务行

| 状态 | 条件 |
| --- | --- |
| `open` | 没有有效收票；待复核占用另列，不能隐藏 |
| `partial` | 有有效收票，尚未同时满足完成条件，也没有有效差异结束决定 |
| `received` | 有效收票数量达到应开数量，金额达到应开金额（允许 0.01 元尾差）；或存在绑定当前依据和账本版本的显式差异结束决定；且没有待复核问题 |
| `superseded` | 所属任务被新审核替代 |

应开金额为空不能宣称金额一致，须有据按差异结束。`over_invoiced` 是独立标记：例如应开 100 件 / 1,000 元，收到 1 件 / 1,100 元只满足金额，不会自动结束；两侧均达到且超开已说明，或财务明确按差异结束，才可完成。当前实现把任一超开视为结束，须在补强阶段调整。

### 6.2 任务

```text
documents_pending → notify_pending → awaiting_invoice → partially_received → completed
取消、冲正：completed / partially_received → 按有效收票与资料事实回退
依据换版：包括 completed 在内的旧任务 → superseded → 后继任务承接
```

- 合同全部归档 → `notify_pending`；登记通知已发送 → `awaiting_invoice`。
- 有第一条通过的分配 → `partially_received`；全部有效任务行 `received` → `completed`，写 `completed_at`。发票可能先于合同或通知到达，此时直接进入收票节点。
- 取消已通过的分配后按实际收票退回（2026-10-15 补充）：仍有收票 → `partially_received`；没有收票 → 收票前节点（已登记通知 → `awaiting_invoice`；合同已全部归档 → `notify_pending`；否则 `documents_pending`）。
- 每次状态变化写 `task_events`。
- 已实现补强：发票失效、待复核及差异结束失效也触发重算；`requires_review` 为独立标记，存在待复核问题时不能显示完成。合同、通知节点始终按各自实际记录展示。
- 原任务因撤销回退时清除当前 `completed_at`，原完成事件保留；依据换版时保留旧任务的历史完成时间与替代事件。

## 7. 整条链路的数据流

| 步骤 | 触发 | 写入（同一事务） |
| --- | --- | --- |
| 1 拉取 NS | 定时 / 手动 | `sync_runs`；`source_*` 主数据、单据、明细、关联、原始数据；报关单 `content_sha256`；推进 `sync_cursors` |
| 2 财务审核 | 财务审核通过（回传来源摘要及版本） | `review_records`、`review_lines`；补强后复用或新建全局子采购依据版本；→ `ReviewApproved` |
| 3 生成任务 | 事件 `ReviewApproved` | 相同依据复用；依据变化替代受影响旧任务（含已完成），生成后继任务行；matching 随后重算，不能只跳过历史行 |
| 4 备合同 | 采购操作 | NS 下载、写共享盘在事务外；`task_documents`；全部归档 → 任务 `notify_pending` |
| 5 通知供应商 | 采购保存、登记发送 | `task_notifications`；登记发送 → 任务 `awaiting_invoice` |
| 6 拉取发票 | 定时 / 手动 | `sync_runs`、`invoice_*`；推进 `sync_cursors` |
| 7 生成比对建议 | 拉票完成后 | `matching_allocations`（`proposed`，带置信度和比对结果） |
| 8 人工比对 | 财务通过 / 驳回 | `matching_allocations` → `confirmed` / `rejected`；→ 事件 `AllocationChanged` |
| 9 更新进度 | 事件 `AllocationChanged` | 按已通过分配重新汇总 `task_lines`；任务状态；`task_events` |

该表为业务链路；依据版本、发票版本、换算与失效事件已按第 10 节 A—D 接入当前工作区。定时同步和 open2 仍待接入，目标库是否已执行迁移须另行核对。

## 8. 主要查询

| 查询 | 走的表与索引 |
| --- | --- |
| 待审核报关单 | `source_customs_declarations` 左连接 `review_records.uq_review_active`，比较 `content_sha256` |
| 报关单审核范围 | `source_customs_purchase_links`（`customs_declaration_id`）→ `source_purchase_order_lines` |
| 采购待办任务 | `task_tasks.ix_task_status_supplier` |
| 子采购行关联的报关单 | `review_lines.ix_review_line_purchase` → `review_records` |
| 比对审核队列 | `matching_allocations.ix_matching_queue` |
| 任务收票明细 | `task_lines`（`task_id`）→ `matching_allocations.ix_matching_purchase` → `invoice_items` |

注："待审核报关单"一行查询跨了 source 与 review 两个模块的表。按模块边界，由 review 经 source 门面取报关单列表和摘要，再与自己的审核记录比对，不在 SQL 中直接连接对方的表。

## 9. 建表与上线

- **初次 v2 切换**：新表从空表开始，不迁移旧模块测试数据。**本次补强**：已有 v2 记录按第 10.8 节准确回填或标记待复核，不能清库重建或删除既有占用。
- **新迁移链**（第 3 步已建立）：`backend/migrations`，配置 `backend/alembic.ini`，版本表 `schema_version`，基线 `0001_baseline` 一次创建第 4 节全部 24 张表。与设计稿的实现差异：
  - 发票行表名为 `invoice_items`（比对表列名 `invoice_item_id`），避免与数据库中保留的旧表 `invoice_lines` 同名；
  - 生成列使用 `CASE` / `COALESCE`；`updated_at` 由 DAO 写入，不用 `ON UPDATE`（第 3 节）。
- **后续迁移**：`0004` 增加 `source_parent_orders.exchange_rate`、`source_purchase_orders.currency_source`、`currency_issue`（子采购单币种取自母采购单）；`0002` 增加 `source_purchase_orders.parent_order_no`；`0003` 增加 `task_tasks.review_revision`（task 不读取 review，审核版本随事件写入）、`task_notifications.sender_name`、`note`（人工发送的员工与登记说明）。
- **旧迁移链**：4e 已从代码移除，历史保留在 Git；不删除数据库中的旧表、旧版本表和记录。
- **命令**：`npm.cmd run db:upgrade` 仅在线升级新迁移链（含 v2 基线回填）；`python -m backend.manage schema-sql` 输出新表结构的 MySQL DDL 供审阅，不包含数据回填；正式启动只核对 `schema_version` 在最新版本。
- **验证**：`backend/tests/test_schema_baseline.py` 在 SQLite 上验证建表、关键唯一约束、CHECK 约束与向前升级；提供 `BUSINESS_MIGRATION_TEST_SERVER_URL` 时在随机新建的 MySQL 库上执行同样的检查。
- **旧表**：代码不删除数据库中的旧表。管理员须先确认实际库清单、保留需求及回写未知结果，再决定是否手工处理；也可以直接新建空库使用。代码侧历史表清单见下方。
- **实施顺序**（架构第 4 步，每个模块一个 PR，按依赖顺序）：source → review → task → invoice → matching → sync。每个模块切换时同时改为分层目录，在 `entity/` 中定义本模块的表并由测试比对与迁移结果一致，调整调用它的门面；之后的模块从新表读取。

### 9.1 4e 退役表核对清单

下表依据退役代码与历史迁移整理，供管理员对照实际库。2026-10-15，经管理员确认旧数据不迁移、后续重新拉取后，已对本机 `127.0.0.1:3306/financial_invoice_business` 完成备份和手工清理：删除清单中实际存在的 21 张旧业务及旧版本表，共 2,487 条记录。

清理后保留 31 张表：在用新结构 27 张（含 `schema_version`）、`unit_dictionary` 及 `ns_previews`、`ns_target_locks`、`ns_audit`。保留表的记录数未变化，迁移版本仍为 `0009_matching_ledger_versions`。整库备份和执行结果位于仓库本机目录 `outputs/legacy-cleanup/20261015-175905-review/`（`before-cleanup.sql`、`execution-result.json`）。

本次清理是管理员确认后的本机手工操作；应用代码和迁移仍不自动删除旧表。本次未在其他环境执行旧表清理或验证其状态，其他环境须分别核对与确认。

| 旧用途 | 历史表名 |
| --- | --- |
| 来源与关联 | `purchase_orders`、`purchase_order_lines`、`customs_declarations`、`customs_declaration_lines`、`parent_purchase_orders`、`parent_purchase_order_lines`、`customs_reconciliation_results` |
| 旧发票与匹配 | `invoices`、`invoice_lines`、`invoice_purchase_allocations`、`invoice_purchase_link_batches`、`invoice_purchase_link_pairs` |
| 财务审核与任务 | `finance_reviews`、`finance_review_snapshots`、`finance_review_audit`、`finance_invoice_tasks`、`finance_task_documents`、`finance_task_notifications` |
| 通知群 | `finance_supplier_groups`、`finance_supplier_group_history`、`finance_wecom_group_directory` |
| 旧迁移版本 | `alembic_version`、`business_alembic_version` |
| 归档回写（特别保留） | `ns_previews`、`ns_target_locks`、`ns_audit`；必须人工确认无 executing / unknown 记录后才可另行处理 |

当前 `source_*`、`review_*`、`task_*`、`invoice_raw_records`、`invoice_headers`、`invoice_items`、`invoice_versions`、`matching_allocations`、`schema_version` 属于在用结构，不属于本清单。

## 10. 2026-10-15 修订与补强（A—D 已实现，E 待接入）

本节规定补强契约。当前分支已实现 A—D，并新增 `0005`—`0009` 分模块迁移；4e 删除旧实现，保留旧数据库表。E open2 和真实目标环境部署尚未完成。新字段与调用方整体切换，原 `0001`—`0004` 不修改；既有 v2 数据回填和无法还原证据的待复核处理见迁移测试。

### 10.1 币种来源、同步与核实

2026-10-15 在正式账户 `5939865` 只读核对：当前 REST 元数据中，`customrecord_swc_subpo` 单头与 `customrecord_swc_subpo_item` 明细均未发现独立结算币种、汇率或结算方式标记。母单引用是 `custrecord_swc_subpo_mainpo`；母采购 REST 字段为 `currency`、`exchangeRate`，SuiteQL 汇率字段为 `exchangerate`。`custrecord_swc_subpo_item_ratewithrate` 是含税单价，不能解释为汇率。当前脚本也存在无母采购的创建分支，不能认为所有子单都有母单。

| 场景 | 来源记录 | 目标行为 |
| --- | --- | --- |
| 同账套、明确内部 ID 的母采购，币种完整 | `currency_source=parent_order`，保存母单 ID、币种与原始版本 | 正常继承；无需逐张人工选币种 |
| NS 明确无母单，或业务字段确实缺币种 | `currency_source=unresolved`，保留实际原因 | 财务可准备资料；凭合同等核实后，在 review 冻结有效币种 |
| 网络、权限、查询失败或返回身份不符 | 失败诊断与同步结果 | 本页失败并重试，不当作无母单，也不清空以前有效数据 |
| 引用了母单但本次未返回该记录 | 保留引用 ID 与“母单未返回”原因 | 限制新分配，补查身份；不能自动改为无母单或 CNY |
| 柠檬云本期 `GetInvoice` 人民币进项票与现有 Excel 通道 | 规则 `lemon_cny_v1` | 适配器明确写入 CNY，标记 `currency_source=source_rule`；原始响应不补造字段，不逐票要求人工核实 |
| 明确返回其他币种的新增来源或票种 | 保留原值与来源 | 不套用本期人民币约定，另行评审接入；本期不自动换汇 |

同步依次完成：子单母单引用 ID 提取 → 按 ID 去重批量读取母单及币种字典 → 事务内保存母单原始快照、母子外键和继承值 → 刷新相关审核摘要。母单显示编号只用于展示，不能反查同名记录建立关系。金额继续保存子采购含税原值，不使用母单汇率或报关币种改算金额。

已有 `source_parent_orders.currency/exchange_rate`、`source_purchase_orders.parent_order_id/currency/currency_source/currency_issue` 复用。已补充母单币种内部 ID、继承所依据的 `source_raw_records.id`；NS 币种 ID 与 ISO 编码的转换依据同账套字典，不写死“ID 1 永远是 CNY”。母单汇率保留供追溯，本期不参与跨币种匹配。

人工核实属于 review：财务核对页针对真实缺失的子采购填写币种、合同或证据引用及说明；后端取得操作者与时间，确认时核实该证据仍对应当前子单和金额口径。同一子采购单全部行使用同一核实币种。核实内容随审核原子保存到依据版本，不能改写 NS 字段、source 原始币种或既存审核行。已审核但缺币种的历史记录，需要新审核版本；读取失败不能用人工输入绕过。

### 10.2 子采购开票依据版本

**新增 `review_purchase_bases`（review 所有）**。报关审核记录仍一单一版；开票依据按子采购行独立版本化，解决同一行在多张报关单中出现、重审及已完成后增量的问题。

| 字段 | 类型 / 约束 | 含义 |
| --- | --- | --- |
| `id`、`ns_account`、`purchase_order_id`、`purchase_line_id` | 主键及来源身份 | 不以名称、行号或列表位置作为身份 |
| `revision` | INT；唯一 `(purchase_line_id, revision)` | 子采购行的开票依据版本 |
| `status` | `active / review_required / superseded` | `review_required` 保留旧依据但限制新确认 |
| `current_purchase_line_id` | 生成列；非 superseded 时取 purchase_line_id；唯一 | 跨报关单只允许一版当前依据 |
| `supplier_id`、`company_id`、`currency`、`quantity`、`unit`、`amount` | 沿用既有金额、数量类型 | 冻结采购结算口径，来源缺失保持 NULL |
| `currency_source` | `parent_order / manual_verified / unresolved` | 人工核实仅属于审核依据 |
| `source_sha256`、`basis_sha256` | CHAR(64) | 来源关键内容与最终获批内容摘要 |
| `source_refs`、`currency_evidence` | JSON | 单据、母单、关联及币种字典的原始版本引用；人工证据、核实人、时间与说明 |
| `origin_review_id`、`approved_by`、`approved_at` | 审核来源及身份 | 来源审核被后续报关版本替代，不等于该依据自动失效 |

冻结的业务值和证据不修改；生命周期状态按 Service 转换。摘要包括账套、稳定行身份、供应商、采购公司、母单关系、数量、单位、金额、币种与业务有效性。拉取时间、显示排序、无关备注及原始快照行 ID 的单独变化不使依据过期；原始快照 ID 另存供追溯。

- `review_lines` 增加 `purchase_basis_id`，保留该次报关审核的关联与冻结展示。相同关键内容引用已有依据，不重复增加额度。
- 来源关键值变化时，review 将当前依据标记 `review_required`；同一子采购行涉及的全部报关审核及任务都显示变化原因，不能只刷新当前列表中的一张报关单。
- 再次审核当前来源时，旧依据置 `superseded`，新依据版本加一；并发审核锁定子采购行和当前依据，唯一约束作为最终保护。
- 新增或移除报关关联不直接增减采购应开总量。采购行停用或撤销进入复核，历史发票占用不能清零。
- 财务审核只确认来源值与证据，不提供修改应开数量、金额的输入。

### 10.3 任务继承、增量与差异结束

`task_lines` 增加 `purchase_basis_id`、`ledger_sha256`、`requires_review`、`closure_event_id`；任务增加后继版本关联。原有“有效子采购行唯一”约束保留，历史 `superseded` 行不占当前唯一键。

1. 同依据再次关联报关：复用当前任务行，详情展示全部报关证据。
2. 依据变化：定位该子采购行当前所属任务，不能仅按本次报关单的 `review_id` 找旧任务；包括已完成任务在内，生成后继任务版本并释放旧有效行。
3. 多行任务中一行变化：受影响任务整体换版，其他行引用原依据，后继任务重新按供应商 × 采购公司 × 币种分组；在同一事务替代旧行并建立新行，不能产生两条有效行或遗漏未变行。
4. 新任务的应开值是新依据总值；进度由 matching 重算。数量、金额变化但主体、币种、单位及行身份兼容时，可以承接已核实分配，并记录承接清单、规则和原因；任一口径不兼容时进入复核，不直接相加。只清除本次已解决的问题，不能把仍有发票版本疑问的分配恢复为有效。
5. 示例：旧依据 100 件 / 1,000 元已收齐，新依据 120 件 / 1,200 元；口径兼容时新任务已收 100 / 1,000、剩余 20 / 200，旧任务保留完成及替代历史。应开减少到已收以下时记录超开，不自动删除原分配。

“按差异结束”改为 task 的显式决定，可随匹配确认后执行，但须绑定当前 `purchase_basis_id` 和 `ledger_sha256`。`task_events` 扩展事件类型、任务行 ID、结构化详情，保存数量差、金额差、说明、操作者和时间；`closure_event_id` 指向当前决定。依据换版、有效分配新增、撤销或失效后，该决定不再适用，须重算或重新确认。现有 `matching_allocations.closes_purchase_line` 仅是旧行为，不能继续用“任一历史分配勾过已开完”永久关闭后继任务。

同一依据内取消分配时，原任务回退并保留完成历史；依据变化则走后继版本，不混成普通取消。待复核数额与有效收票分开展示，不能用缓存 0 冒充没有历史发票。

### 10.4 发票不可变版本与同票去重

**新增 `invoice_versions`（invoice 所有）**，保存规范化票头和全部明细的不可变快照。`invoice_raw_records` 仍保存原始来源，不用原始 JSON 的偶然差异代替业务版本。

| 字段 | 类型 / 约束 | 含义 |
| --- | --- | --- |
| `id`、`invoice_id`、`revision` | 主键；唯一 `(invoice_id, revision)` | 同一业务发票的内容版本 |
| `content_sha256` | CHAR(64)；索引 `(invoice_id, content_sha256)` | 与当前版本内容相同则复用；不因文件名、抓取时间或外部 ID 变化新增版本。状态从作废恢复为原值时仍追加新 revision，不复用旧生命周期 |
| `raw_record_id`、`source`、`external_id` | 来源引用 | 保留产生该版本的原始记录与外部身份 |
| `currency_source`、`source_rule_version` | 如 `source_rule / lemon_cny_v1` | 人民币接入规则的明确来源 |
| `header_snapshot`、`items_snapshot` | JSON；金额、数量存十进制字符串 | 冻结状态、主体、币种、金额与明细逻辑身份，不允许原地覆盖 |

`invoice_headers` 增加 `current_version_id`、`detail_status`（pending / complete / failed），其查询字段作为当前版本的投影；版本快照同时冻结完整性状态，是确认依据。列表可先保存待补全版本，但没有完整商品行不能确认；一次只含票头的刷新不能用空明细覆盖既存完整依据，先保留原始新来源并补查，明确作废 / 红冲仍须及时失效处理。`invoice_items.id` 继续表示同票稳定的逻辑明细身份，版本快照保存该 ID 对应的字段；新增当前有效标记，停用行不删除。不能直接把显示行号当作跨 Excel / API 的稳定身份；重排或重复同名行无法无歧义映射时，保留新来源并要求核实，禁止新确认。

`matching_allocations` 增加 `invoice_version_id` 与 `purchase_basis_id`，建议和确认均记录两端版本及比对规则版本。发票行额度按同一逻辑明细汇总所有未取消确认，不能通过换一个发票版本、外部 ID 或来源账套重复使用。

- Excel / API 合并前必须核实账套映射；现有 Excel 固定命名空间 `lemon` 不是任意 API 账套授权。不同账套不凭同票号强制合并；同主体同票跨来源须完成身份绑定，避免两份有效占用。
- 相同内容跳过；新版本追加保存，原建议置过期；已确认记录保留原发票版本与原依据，标记待复核。
- 发票明确作废、红冲时，分配失去有效收票资格，驱动任务重算；未知状态等待核实，不认定为正常。核实后通过有审计的取消、替换或恢复动作解决，不能静默覆盖。
- 在版本功能上线前，继续维持现有“同票内容冲突整批拒绝”策略，不提前开放覆盖更新。

### 10.5 数量换算、金额与额度

分配中现有 `quantity` 明确为**发票口径数量**；增加 `purchase_quantity`、`invoice_unit`、`purchase_unit`、`conversion_numerator`、`conversion_denominator`、`conversion_evidence`。沿用数量 DECIMAL(26,8)，换算因子使用足够精度的 DECIMAL；分母大于 0。约定：采购数量 = 发票数量 × numerator / denominator。

- 相同单位因子为 1；箱 / 个、千克 / 件等换算须对应具体商品、规格和来源版本，不做全系统统一“1 箱 = 10 个”。
- 同一事务分别控制：发票已占用数量 + 本次数量不超过票行数量；发票已占用金额 + 本次金额不超过票行含税金额；采购进度累计 `purchase_quantity` 与本次含税分配金额。允许采购超开不等于允许发票自身超用。
- 示例：采购 10 箱，发票 100 个，经证据核实每箱 10 个；分配记 quantity=100、purchase_quantity=10、numerator=1、denominator=10。
- 换算必须可由后端按既定精度验证；数量无法精确落在允许精度时返回待核实，不偷偷舍入。发票本身没有可核实数量的特殊票，保留来源，本期不强行套数量分配。
- 金额由后端以 Decimal 校验，总量守恒。拆分票行可按已核实份额计算并由末次分配承接分位尾差；累计不得超过票行，末次必须核对完整金额。展示单价乘数量不是唯一金额依据。
- 0.01 元是每条采购行收齐的尾差容差，不是每次分配可以额外使用的发票额度；发票净额、税额和含税额分别校验，不把税率字段当换算因子。

### 10.6 占用、有效收票与复核

保留分配 `status=proposed/confirmed/rejected/cancelled`，增加 `verification_status=valid/needs_review/invalid` 和结构化 `verification_issues`，区分来源、依据、发票版本与换算问题。每次变化保留原因、版本、操作者、时间与请求幂等信息。

| 分配情况 | 发票额度占用 | 有效收票 | 后续动作 |
| --- | --- | --- | --- |
| proposed / rejected | 否 | 否 | 重新评估或驳回 |
| confirmed + valid，且与当前依据口径兼容 | 是 | 是 | 按有效分配汇总 |
| confirmed + needs_review | 是 | 否；单列待复核占用 | 核实前限制相关新确认，不能释放后再用一次 |
| confirmed + invalid（如明确作废） | 原占用保留至有审计的取消 / 冲正 | 否 | 原票本身也禁止新确认；驱动任务回退 |
| cancelled | 否 | 否 | 原决定和证据永久保留 |

新版本使数量或金额小于原占用、单位改变或明细身份不明时，阻止相关新确认，不能按新行余额重新从零计算。恢复有效须重新核实当前两端版本并执行容量校验；跨币种、单位或主体的旧数额不能自动迁移。更换分配采用同一事务取消旧占用并确认新占用，任何一步失败均回滚。

### 10.7 门面、事件与事务契约

以下契约已由门面和同步订阅实现，不通过导入其他模块 DAO 实现。事件传稳定 ID，订阅方在同一事务通过门面读取冻结版本与摘要。

| 事件 / 门面 | 关键数据 | 处理顺序 |
| --- | --- | --- |
| source 的 `SourceChanged` | 账套、受影响子采购行、关键内容摘要、变化原因 | review 标记依据待审；涉及同一母单或子行的全部有效依据均处理 |
| review 的 `ReviewApproved` | 审核 ID、每行的依据 ID / revision / hash、冻结口径、替代关系 | app 显式登记 task 先生成 / 换版，matching 再核实承接并发布汇总；都在同一事务，不能依赖未声明的注册顺序 |
| review 的 `PurchaseBasisInvalidated` | 依据 ID、问题与来源摘要 | matching 记录复核问题并汇总；task 限制新匹配与完成 |
| invoice 的 `InvoiceChanged` | 发票 ID、旧新版本 ID、变化类型、受影响逻辑行 | matching 处理过期建议和确认复核，发布最新汇总 |
| matching 的 `AllocationChanged` | 每行当前依据 ID、有效采购数量和金额、待复核标记、`ledger_sha256` | task 用绝对合计更新投影并重算，不把同一事件作为增量重复相加 |
| review 的只读门面 | 当前依据、冻结版本、是否可分配及原因；接受调用方 Connection 与锁定选项 | matching 确认时验证当前依据；task 仅消费事件，不查询 matching 的表 |

`ledger_sha256` 由 matching 对该子采购行所有曾确认分配（含已取消历史）的稳定 ID、两端版本、数量金额、确认状态与核实问题排序计算，不包含查询时间或未确认建议。生成 / 驳回建议不改变收票账本，也不使差异结束失效。task 保存此摘要；差异结束请求须携带相同摘要。同步事件与加锁保证同一事务中的汇总顺序；修复缓存时由 matching 从台账重新发布绝对合计，不以旧 task 缓存修复台账。

所有关联写用例（来源更新、审核、确认、撤销、发票换版）先按统一顺序取得业务库级开票账本命名锁，再取得既有账户锁；数据库行锁顺序为 来源 → 开票依据 → 任务 → 任务行 → 发票 → 分配，同层按稳定 ID 升序。第一阶段用写串行化保证跨模块同步事件的安全，仍保留事务内版本与容量校验；后续按实测再细化锁域。

命名锁不是事务：外部 HTTP 仍在数据库事务外，进入短事务后复核采集版本；任何异常或提交结果未知都按现有规则核实、释放锁，不盲目重发。订阅方不调用外部系统、不另开事务、不反向补取命名锁；尤其不能先持有发票写锁，再尝试取得任务锁。发票更新入口须在写前完成受影响范围准备与按序取锁。新增锁规范、订阅顺序、跨模块门面须作为同一补强步骤实现并在 MySQL 验证，不能只改单个订阅方。

### 10.8 实施与验收

| 顺序 | 交付 | 验收出口 |
| --- | --- | --- |
| A 锁规范与来源依据 | 关联写入口统一锁顺序；复用 `0004` 继承能力，补原始版本引用、变化摘要与依赖清单 | 正常母单自动继承；网络失败不伪装缺失；全部入口锁顺序一致 |
| B 开票依据与任务后继 | review 新表、财务异常核实、门面及失效事件；task 依据引用、后继与差异结束事件 | 重复报关不重复应开；完成 100 后重审 120 正确剩余 20；其他任务行不丢失 |
| C 发票版本与分配口径 | invoice 新表；matching 版本、双数量、复核问题、台账汇总 | 重复导入不增票；变更不覆写历史；10 箱 / 100 个换算和额度分别正确 |
| D 完成与冲正 | 按统一锁规范联调全部事件、投影重算与错误恢复 | 超开不掩盖欠开；取消 / 红冲后回退；复核占用不被重复使用 |
| E open2 接入 | 账套绑定、真实票头及明细接口验证、窗口回扫 | 用户提供列表字段未包含商品明细，取得真实明细并验证后才开放行分配；不影响已有 Excel 闭环 |

A—D 是同一兼容版本的开发里程碑：锁规范、版本字段和全部调用方完成验证前，不分别启用半套确认或事件逻辑；保留现有安全链路，整体切换补强能力。新增迁移按模块依次提交，依赖当时实际 migration head，不预占版本号，不修改已执行的 `0001`—`0004`。保留 v2 已有审核、发票、分配及确认时间；能从既存快照准确还原的记录追加基线版本，不能还原的标记待复核并保留占用，不能把最新来源伪造成历史证据。字段与调用方切换完成、回填核对通过后再移除过渡逻辑。

最低验证包括：同账套母单继承与跨账套同 ID 隔离；无母单和读取失败；CNY 固定规则及外币不匹配；母单改币种触发全部相关审核失效；审核过期请求；重复报关；已完成后增加 / 减少应开；不同单位及换算证据过期；一票多单与一单多票的数量金额守恒；取消 / 作废 / 红冲后的任务与差异结束回退；发票重排和新版本不重复占用；提交结果不明与重启后的台账重算。

MySQL 上另验证迁移升级、生成列唯一约束、两票争同一子采购行、同一票被并发分配、重审与取消 / 导入并发、订阅方异常整单回滚。SQLite 可用于规则测试，不能替代 MySQL 并发验收。隔离测试覆盖规则、向前迁移、版本表扩宽、容量竞争、重审/来源变更/取消与导入交错执行；未触发真实 NS 写入或部署业务库。具体验收以本次运行结果为准。

## 11. 柠檬云已有账号绑定（2026-10-16）

迁移 `0016_sync_lemon_bindings` 新增 `sync` 所属的 `sync_lemon_bindings`，不修改旧迁移。

| 字段 | 类型与约束 | 含义 |
| --- | --- | --- |
| id | BIGINT 主键 | 绑定记录 ID |
| scope_key | VARCHAR(64)，唯一 | 官方环境、应用编号与认证 owner 的 SHA-256，隔离绑定范围 |
| owner | VARCHAR(190)，非空 | 服务端认证管理员身份 |
| mobile | VARCHAR(32)，非空 | 本次绑定的已有账号手机号 |
| status | VARCHAR(20)，非空，CHECK | unbound、binding、unknown、bound |
| verified_at | DATETIME，可空 | 最近明确成功或官方查询核实时间，UTC |
| created_at / updated_at | DATETIME，非空 | 创建与更新时刻，UTC |

不保存密码、授权码和令牌。等待授权／确认只在单进程短期上下文中，最多 10 分钟，不扩张数据库持久状态。外部请求前以 scope、手机号和原状态条件更新争用执行权；外部请求在事务外执行。网络结果不明留 unknown，进程中断留 binding；重启不清锁、不自动重发，使用官方查询核实。此表不代表已经获得发票账套权限，也不改变现有 Excel 命名空间。详情见[账号绑定说明](../lemon-account-binding.md)。

### 既有单位字典展示兼容（2026-10-16）

`unit_dictionary(unit_id, unit_name, enabled)` 由管理员维护，归 source 模块只读访问，其他模块通过 source 门面读取。该历史非前缀表只用于将数字编号显示为启用的单位名称，不属于 `schema_metadata` 新迁移链；缺表时显示来源原值，不自动建表或填充猜测字典。既有数据、冻结依据和比对规则不因展示名称改变。后续显式迁移且替换全部调用方后再退出兼容。


### 外部群目录与导入预览（2026-10-16）

迁移 `0017_task_external_groups` 新增两张 task 表，不修改旧表和历史通知。

| 表 | 主要字段与约束 | 用途 |
| --- | --- | --- |
| `task_external_groups` | id 主键；chat_id VARCHAR(190) 区分大小写唯一；group_name、owner_name、owner_userid；member_count（0020 起可空，不可识别人数不阻止导入）、department、group_created_at（UTC，可空；0019 起允许创建时间缺失或无法识别）；filename、version、updated_by、created_at/updated_at | 保存确认导入的七列 Excel 群目录，尚未关联供应商的群也保留。信息来源为文件，不表示企微实时核验通过。 |
| `task_group_imports` | UUID id 主键；owner、filename、status（pending/confirmed）；snapshot LONGTEXT、confirmation LONGTEXT；created_at/updated_at | 持久保存服务器解析的预览、目录版本与候选，预览确认有效期 24 小时；确认请求和实际结果用于幂等重放。 |

确认事务先锁导入记录，再按 chat_id 排序锁目录，最后按供应商 ID 排序锁 `task_supplier_groups`。目录按预览版本比较；绑定沿用供应商唯一键和版本校验。已有其他默认群须显式确认替换。任何一项冲突整批回滚，相同确认请求返回原结果，不重复更新版本。目录更新不会自动传播到未选中的已有绑定或历史通知。部署前执行 `npm.cmd run db:business:upgrade`，无需迁移旧供应商数据。降级拒绝自动删除目录及人工确认证据。

## 柠檬云手动同步存储（2026-10-16，迁移 0018）

归属 `sync` 模块。`0018_sync_lemon_runs` 在绑定表新增 `selected_asid VARCHAR(32)`、`selected_name VARCHAR(255)`，新增 `sync_lemon_runs`：主键 id，scope_key（已有管理员/应用身份范围）、request_id（UUID）、asid、account_name、start_date、end_date、status（running/completed/failed）、result JSON、error、created_at、updated_at。唯一键为 `(scope_key, request_id)`，另建 `(scope_key,status)` 索引；无跨模块外键，不存令牌或密码。

开始请求时锁绑定行，检查同请求和未结束请求后持久写 running；外部 HTTP 在事务外执行。发票写入复用现有账本锁及 invoice 版本事件，完成回执与所有发票数据在同一事务提交。数据库结果不确定或重启保留 running，禁止自动复位。记录为持久审计依据，迁移 downgrade 拒绝删除。

API 发票使用 `source=lemon_open2`，`lemon_account=open2:` 加 `SHA256(host|asid)`，`external_id=InvoiceId`；复用 invoice 现有票头、原始数据、不可变版本表，不另建平行发票表。无商品明细则完整性为 pending。Excel 固定命名空间尚未与真实 API 账套对齐，两个入口遇同代码/号码均拒绝跨渠道重复。接口及异常处置详见[接入说明](../lemon-invoice-sync-plan.md)。

## 合同自动归档队列（0021，2026-10-16）

新增 `task_contract_jobs`，归属 task 模块；审核生成新任务的事务中登记，不回填历史任务，不删除旧表数据。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | BIGINT UNSIGNED | 自增主键 |
| task_id | BIGINT UNSIGNED | 本模块 task_tasks 外键 |
| purchase_order_id | BIGINT UNSIGNED | source 子采购单 ID，无跨模块外键 |
| actor | VARCHAR(190) | 财务审核认证身份 |
| status | VARCHAR(20) | pending / completed / failed |
| error_message | VARCHAR(500) | 脱敏失败原因；完成后清空 |
| created_at / updated_at | DATETIME(6) | UTC 时间 |

唯一约束 `(task_id, purchase_order_id)`；检查约束限制状态；索引 `(status, id)` 支持有界消费。后台只处理已提交 pending，失败供人工重试；归档成功与作业完成在同一短事务更新。只读下载中断后允许继续，已有 PDF 通过原合同摘要保护避免覆盖。MySQL 消费者和单合同命名锁均不持有下载期间的数据库事务。详见 [task 模块](../../backend/modules/task/README.md#审核后自动归档2026-10-16)。

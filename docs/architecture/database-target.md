# 目标数据库设计（按整条链路重新设计）

状态：**草案，待确认**。本文不受现有表结构约束，按业务主线重新设计；第 7 节说明如何从现有表迁移过来。[数据库设计](database.md)是在现有表上增量修改的方案，两者二选一，见第 8 节。

依据的业务规则：[架构设计 v2](README.md)第 0 节、[数据库设计](database.md)第 1、5、6、10 节（开票单元为子采购行、只生成一次、置信度人工审核、人工通过即结束、采购口径、容差 0.01 元、置信度分档）。

## 1. 现有结构的问题与本设计的对应做法

| 现有问题 | 影响 | 本设计 |
| --- | --- | --- |
| 数据按登录人隔离：来源、发票、分配表用 `tenant_id`（登录身份哈希），审核、任务表用 `owner` | 财务、采购分别登录时互相看不到数据 | 数据按组织共享，只按 **NS 账套**（正式 / 沙箱）区分；操作人单独记录在 `*_by` 字段 |
| 时间类型混用：应用表用整数秒，业务表用 `DATETIME(6)` | 查询、排序、展示要分别处理 | 全部 `DATETIME(6)`，存 UTC |
| 主键类型混用：UUID 字符串、BIGINT、用 `VARCHAR(20)` 存数字 ID | 关联时要转换类型，容易出错 | 全部 `BIGINT UNSIGNED` 自增主键；外部系统 ID 单独成列 |
| 子采购单头只有一个 `customs_declaration_id`；报关与采购的行级关系藏在 JSON 中 | 只支持一对一；行级关系无法查询 | 独立的**报关—采购关联表**，单头级和行级关系都是普通行，支持多对多 |
| 审核范围、任务明细存为 JSON（`payload`） | 无法按子采购行查询"哪些审核、哪些任务包含它" | 审核冻结的范围存为**审核行**；任务行引用审核行 |
| 15 分钟有效的审核预览快照表 | 多一张临时表和过期逻辑 | 不保存预览：列表返回内容摘要，审核时重新计算摘要比对，一致才通过 |
| 合同 PDF 存在数据库（`LONGBLOB`） | 库体积增长、备份变慢 | 文件只存共享盘，库中保存路径和 SHA256 |
| 原始来源 JSON 与主表同行 | 主表行很大，列表查询慢 | 原始数据放独立的原始记录表，主表只放结构化字段 |
| 供应商、公司只是每张单据上的名称和 ID 文本 | 企微群、发票销售方比对只能按名称 | 供应商、公司成为主数据表，可保存税号，用于发票比对 |

## 2. 通用约定

- **表名以模块名开头**：`source_`、`review_`、`task_`、`invoice_`、`match_`、`sync_`。
- **主键**：`id BIGINT UNSIGNED AUTO_INCREMENT`。外部系统 ID 用 `ns_internal_id`、`external_id` 等列，并对（账套 + 外部 ID）建唯一约束。
- **范围**：NS 数据带 `ns_account`；柠檬云数据带 `lemon_account`。没有按登录人隔离的列。
- **金额**：来源金额 `DECIMAL(24,6)`；发票金额 `DECIMAL(18,2)`；数量 `DECIMAL(26,8)`；Python 中用 `Decimal`。
- **时间**：`DATETIME(6)` UTC；每张表有 `created_at`、`updated_at`。
- **状态**：`VARCHAR(24)` + `CHECK` 约束，与模块 `policy/` 中的状态机一致。
- **不物理删除**：来源停用用 `is_active`；业务记录用状态（`superseded`、`cancelled` 等）。
- **外键**：模块内建外键；跨模块只存 ID，不建外键（[后端规则](backend-rules.md)第 5 节）。
- **字符集**：`utf8mb4`，单号、ID 类列用 `utf8mb4_bin`。

## 3. 全景

```text
                         ┌──────────────── sync ────────────────┐
                         │ sync_runs   sync_cursors              │
                         └───────┬───────────────────────┬──────┘
                                 │写入                   │写入
                                 ▼                       ▼
source（NS 来源）                                  invoice（进项发票）
  source_suppliers                                   invoice_headers ─< invoice_lines
  source_companies                                   invoice_raw_records
  source_parent_orders ─< source_parent_order_lines
  source_purchase_orders ─< source_purchase_order_lines   ← 开票单元
  source_customs_declarations ─< source_customs_lines
  source_customs_purchase_links（报关 ↔ 子采购，单头级 + 行级）
  source_raw_records
        │ 读取                                              │ 读取
        ▼                                                   │
review（财务核对）                                          │
  review_records ─< review_lines（冻结的子采购行）           │
        │ 事件 ReviewApproved                               │
        ▼                                                   │
task（开票跟进）                                            │
  task_supplier_groups                                      │
  task_tasks ─< task_lines（应开 / 已收）                    │
            ─< task_documents（合同）                        │
            ─< task_notifications（通知版本）                │
            ─< task_events（状态历史）                       │
        ▲ 事件 AllocationChanged                            │
        │                                                   ▼
match（发票比对）
  match_allocations：invoice_line ↔ purchase_line（建议 → 人工通过 / 驳回 → 可取消）
```

## 4. 各模块表

以下列出主要列；`id`、`created_at`、`updated_at` 每张表都有，不再重复列出。

### 4.1 source（只由同步写入，其他模块只读）

**source_suppliers** 供应商主数据

| 列 | 说明 |
| --- | --- |
| `ns_account`, `ns_internal_id` | 唯一 |
| `name` | 供应商名称 |
| `tax_no` | 纳税人识别号；用于与发票销售方税号比对（需确认 NS 供应商记录是否有此字段） |
| `is_active` | |

**source_companies** 采购公司（NS 子公司）主数据：`ns_account`, `ns_internal_id`（唯一）, `name`, `tax_no`（与发票购买方税号比对）, `is_active`。

**source_parent_orders / source_parent_order_lines** 母采购单：结构同现有母采购两表，去掉 `tenant_id`、`source_data`（移到原始记录表），供应商、公司改为引用 `supplier_id`、`company_id`。

**source_purchase_orders** 子采购单

| 列 | 说明 |
| --- | --- |
| `ns_account`, `ns_internal_id` | 唯一 |
| `order_no` | 子采购单号，建索引 |
| `order_date`, `pl_no` | |
| `parent_order_id` | 母采购单，可空 |
| `parent_relation_status` | `unknown` / `no_parent` / `linked` |
| `supplier_id`, `company_id` | 引用主数据 |
| `currency` | |
| `total_amount` | DECIMAL(24,6) |
| `source_modified_at`, `synced_at`, `is_active` | |
| `raw_record_id` | 原始数据 |

不再有 `customs_declaration_id`，与报关单的关系全部在关联表中。

**source_purchase_order_lines** 子采购行（**开票单元**）

| 列 | 说明 |
| --- | --- |
| `purchase_order_id` | |
| `source_line_key` | 稳定行键，与 `purchase_order_id` 组合唯一 |
| `line_no`, `item_code`, `item_name`, `declaration_name`, `specification` | |
| `quantity`, `unit` | **采购口径**，开票比对用（NS `custrecord_swc_subpo_item_unit`） |
| `declared_quantity`, `declared_unit` | 报关口径，只用于报关核对 |
| `unit_price`, `amount` | 含税单价、含税金额 |
| `amount_status` | `matched` / `source_missing`，来源金额是否可信 |
| `parent_line_id` | 母采购行，可空 |
| `is_active` | |

**source_customs_declarations** 报关单：`ns_account` + `ns_internal_id`（唯一）, `record_no`（CD 编号）, `declaration_no`（真实报关单号）, `declaration_date`, `declarant_company_id`, `source_modified_at`, `synced_at`, `is_active`, `raw_record_id`。

**source_customs_lines** 报关明细：`customs_declaration_id`, `source_line_key`（组合唯一）, `line_no`, `pl_no`, `item_code`, `declaration_name`, `specification`, `origin_place`, `quantity`, `unit`, `declared_quantity`, `declared_unit`, `unit_price`, `amount`, `currency`, `is_active`。

**source_customs_purchase_links** 报关—子采购关联

| 列 | 说明 |
| --- | --- |
| `customs_declaration_id`, `purchase_order_id` | 单头级关系，必填 |
| `customs_line_id`, `purchase_line_id` | 行级关系，可空（只有单头级关系时为空） |
| `evidence` | `ns_v3`（NS 整单关联）/ `local_packing`（本地 Packing 定位）/ `ns_reference`（子采购引用） |
| `status` | `active` / `stale`（来源变化后失效） |
| `synced_at` | |

唯一约束：（`customs_declaration_id`, `purchase_order_id`, `customs_line_id`, `purchase_line_id`）。审核范围按此表取子采购单，支持一张子采购单关联多张报关单。

**source_raw_records** 原始数据：`ns_account`, `record_type`, `ns_internal_id`, `payload JSON`, `payload_sha256`, `fetched_at`。同一记录每次内容变化追加一行，主表 `raw_record_id` 指向最新一行。

### 4.2 review（财务核对）

**review_records** 审核记录（一次审核通过一行，不可修改）

| 列 | 说明 |
| --- | --- |
| `ns_account`, `customs_declaration_id` | 被审核的报关单 |
| `revision` | 同一报关单第几次审核，组合唯一 |
| `content_sha256` | 审核时看到的内容摘要 |
| `status` | `active` / `superseded`（来源变化后再次审核时，旧记录置为 superseded） |
| `approved_by`, `approved_at`, `note` | |

一张报关单最多一条 `active` 记录（生成列唯一约束，做法同第 4.3 节任务行）。"待审核"不存表：没有 `active` 审核记录、或当前内容摘要与 `active` 记录不一致的报关单即为待审核，由查询得出。

**review_lines** 审核冻结的范围（审核通过时写入，不可修改）

| 列 | 说明 |
| --- | --- |
| `review_id` | |
| `purchase_order_id`, `purchase_line_id` | 子采购行 |
| `customs_line_id` | 对应报关行，可空 |
| `order_no`, `item_name`, `specification`, `currency` | 冻结的展示信息 |
| `quantity`, `unit`, `amount` | 冻结的采购口径数量、单位、含税金额 |
| `line_sha256` | 冻结时子采购行内容摘要 |

唯一约束：（`review_id`, `purchase_line_id`）。替代现有的审核快照 JSON 和审核历史表：审核历史就是 `review_records` 的全部行。

### 4.3 task（开票跟进）

**task_supplier_groups** 供应商企微群：`supplier_id`（唯一）, `group_name`, `chat_id`, `owner_name`, `owner_userid`, `enabled`, `version`, `updated_by`。

**task_tasks** 开票任务（审核通过后按 供应商 × 采购公司 × 币种 分组生成）

| 列 | 说明 |
| --- | --- |
| `review_id` | 由哪次审核生成 |
| `ns_account`, `customs_declaration_id` | 冗余，便于按报关单查询 |
| `supplier_id`, `company_id`, `currency` | 分组依据；同一 `review_id` 下组合唯一 |
| `status` | `documents_pending` / `notify_pending` / `awaiting_invoice` / `partially_received` / `completed` / `superseded` |
| `completed_at` | |

**task_lines** 任务行

| 列 | 说明 |
| --- | --- |
| `task_id` | |
| `review_line_id` | 生成该行的审核行（冻结值来源） |
| `purchase_line_id` | 子采购行；**有效行唯一**（生成列 `IF(status='superseded', NULL, purchase_line_id)` 加唯一约束） |
| `expected_quantity`, `unit`, `expected_amount` | 从审核行复制的应开值 |
| `received_quantity`, `received_amount` | 已通过分配的合计（缓存，可按分配表重算） |
| `status` | `open` / `partial` / `received` / `superseded` |
| `over_invoiced`, `closed_with_difference` | 汇总得出的标记 |

"只生成一次"的关联报关单：同一 `purchase_line_id` 在 `review_lines` 中的全部有效审核即为关联报关单，由查询得出，不需要另建关联表。

**task_documents** 合同：`task_id`, `purchase_order_id`（组合唯一）, `ns_file_id`, `filename`, `sha256`, `archive_path`, `downloaded_at`, `archived_at`, `status`（`pending` / `archived` / `failed`）, `error_message`。**不存文件内容**。

**task_notifications** 通知（每次保存一个版本）：`task_id`, `version`（组合唯一）, `channel`（`manual` / `wecom`）, `chat_id`, `recipient_name`, `content`, `status`（`draft` / `sent` / `failed`）, `sent_at`, `sent_by`, `channel_message_id`（企微回执，接入后填写）。

**task_events** 任务状态历史：`task_id`, `from_status`, `to_status`, `reason`, `actor`, `occurred_at`。每次状态变化追加一行。

### 4.4 invoice（进项发票）

**invoice_headers** 发票

| 列 | 说明 |
| --- | --- |
| `source` | `lemon_open2` / `lemon_excel` |
| `lemon_account`, `external_id` | 唯一；Excel 导入时 `external_id` 用发票代码 + 号码 |
| `invoice_code`, `invoice_no`, `invoice_date`, `invoice_type` | |
| `status` | `normal` / `red_offset` / `void`，比对的硬性校验依据 |
| `seller_name`, `seller_tax_no`, `buyer_name`, `buyer_tax_no` | 税号用于与供应商、公司主数据比对 |
| `currency`, `amount_excluding_tax`, `tax_amount`, `amount_including_tax` | DECIMAL(18,2) |
| `remark` | 备注，比对子采购单号 |
| `business_type` | 例如"采购固定资产"，筛选用 |
| `raw_record_id`, `imported_at` | |

**invoice_lines** 发票行：`invoice_id`, `source_line_key`（组合唯一）, `line_no`, `item_name`, `specification`, `quantity`, `unit`, `unit_price`, `amount_excluding_tax`, `tax_rate`, `tax_amount`, `amount_including_tax`。

**invoice_raw_records** 原始数据：`source`, `lemon_account`, `external_id`, `payload JSON`, `payload_sha256`, `fetched_at`。

### 4.5 match（发票比对）

**match_allocations** 一条发票行与一条子采购行的一次比对

| 列 | 说明 |
| --- | --- |
| `invoice_line_id`, `purchase_line_id` | **有效记录唯一**（生成列：`status IN ('proposed','confirmed')` 时为两者组合，否则为空） |
| `quantity`, `amount` | 分配的数量、含税金额 |
| `status` | `proposed` / `confirmed` / `rejected` / `cancelled` |
| `confidence` | 0–100，人工新建时为空 |
| `checks` | JSON：逐项比对结果 |
| `exceeds_expected`, `closes_purchase_line` | 超开、按差异结束 |
| `proposed_by`, `proposed_at`, `reviewed_by`, `reviewed_at`, `review_note` | |
| `cancelled_by`, `cancelled_at`, `cancel_reason` | |
| `request_id` | 幂等 |

只有 `confirmed` 计入收票。规则见[数据库设计](database.md)第 5 节。

### 4.6 sync

**sync_runs**、**sync_cursors**：同[数据库设计](database.md)第 4.4 节，去掉 `tenant_id`。

## 5. 整条链路的数据流

| 步骤 | 触发 | 读 | 写（同一事务） |
| --- | --- | --- | --- |
| 1 拉取 NS | 定时 / 手动 | NS | `sync_runs`；`source_*` 主数据、单据、明细、`source_customs_purchase_links`、`source_raw_records`；推进 `sync_cursors` |
| 2 财务审核 | 财务点击审核通过 | `source_customs_*`、关联表、子采购行；重新计算内容摘要并比对 | `review_records`（旧 active 置 superseded）、`review_lines`；→ 事件 `ReviewApproved` |
| 3 生成任务 | 事件 `ReviewApproved` | `review_lines`、`task_lines`（检查有效行） | 旧任务、旧任务行置 superseded；`task_tasks`、`task_lines`（已有有效行的子采购行跳过）、`task_events` |
| 4 备合同 | 采购点击 | NS 合同接口（事务外）、共享盘（事务外） | `task_documents`；全部归档后任务 → `notify_pending`，写 `task_events` |
| 5 通知供应商 | 采购保存、登记发送 | `task_supplier_groups` | `task_notifications`；登记发送后任务 → `awaiting_invoice` |
| 6 拉取发票 | 定时 / 手动 | 柠檬云 | `sync_runs`、`invoice_headers`、`invoice_lines`、`invoice_raw_records`；推进 `sync_cursors` |
| 7 生成比对建议 | 拉票完成后 | 新发票行、有效 `task_lines` 对应的子采购行、主数据税号 | `match_allocations`（`proposed`，带置信度和比对结果） |
| 8 人工比对 | 财务通过 / 驳回 | 建议、发票行已分配合计 | `match_allocations` → `confirmed` / `rejected`；→ 事件 `AllocationChanged` |
| 9 更新收票进度 | 事件 `AllocationChanged` | 该子采购行全部 `confirmed` 分配 | `task_lines` 汇总值和状态；任务状态（全部 `received` → `completed`）；`task_events` |

## 6. 主要查询如何走索引

| 查询 | 走的表与索引 |
| --- | --- |
| 待审核报关单列表 | `source_customs_declarations` 左连接 `review_records`（`customs_declaration_id`, `status`） |
| 一张报关单的审核范围 | `source_customs_purchase_links`（`customs_declaration_id`）→ `source_purchase_order_lines` |
| 采购的待办任务 | `task_tasks`（`status`, `supplier_id`） |
| 一条子采购行被哪些报关单审核过 | `review_lines`（`purchase_line_id`）→ `review_records` |
| 发票比对待审核队列 | `match_allocations`（`status`, `confidence`） |
| 一张发票关联了哪些子采购单 | `match_allocations`（`invoice_line_id`, `status`） |
| 任务的收票明细 | `task_lines`（`task_id`）→ `match_allocations`（`purchase_line_id`, `status`）→ `invoice_lines` |

## 7. 从现有表迁移

现有数据量很小（截图中报关单约 100 张、子采购单约 130 张、发票约 30 张），可以一次性转换。遵守 [AGENTS.md](../../AGENTS.md) 第九节：**不重建数据库、不删除旧表和数据**。新表与旧表在同一个库中并存，按模块逐个切换：

| 旧表 | 新表 | 转换要点 |
| --- | --- | --- |
| 母采购、子采购、报关及明细 6 张 | `source_*` 对应表 | 去掉 `tenant_id`；`source_data` 写入 `source_raw_records`；供应商、公司拆到主数据表 |
| `purchase_orders.customs_declaration_id`、`customs_reconciliation_results` | `source_customs_purchase_links` | 单头级关系来自外键列；行级关系来自 `comparison_payload` / `lineRelations` |
| `finance_reviews`、`finance_review_snapshots`、`finance_review_audit` | `review_records`、`review_lines` | 每条审核历史转一条 `review_records`；`review_lines` 来自对应快照 `content.purchaseLines`；已过期未审核的快照不转换 |
| `finance_invoice_tasks` | `task_tasks`、`task_lines` | 任务行来自 `payload` 与审核行；整数秒时间转 `DATETIME` |
| `finance_task_documents` | `task_documents` | 已归档的保留路径和 SHA256；**数据库中暂存的 PDF 内容先导出到共享盘再转换**，未归档的标记 `pending` |
| `finance_task_notifications`、`finance_supplier_groups` | `task_notifications`、`task_supplier_groups` | 字段改名 |
| `invoices`、`invoice_lines` | `invoice_*` | 扩展列中只保留第 4.4 节列出的字段，其余随原始 JSON 保存 |
| `invoice_purchase_allocations`、`invoice_purchase_link_*` | `match_allocations` | 现有记录转为 `confirmed`；整票关联的拆分规则同[数据库设计](database.md)第 8 节 |
| `ns_previews`、`ns_target_locks`、`ns_audit` | 不转换 | 原样保留 |

做法：

1. 每个模块一个迁移：建新表 + 转换数据 + 输出逐表行数核对；失败整体回滚。
2. 该模块的 DAO 改读写新表，测试改用新表。
3. 旧表保留只读，确认运行稳定后另行决定是否删除（需单独迁移和人工确认）。
4. 切换顺序按依赖：source → invoice → review → task → match → sync。每个模块切换都是独立的 PR。

## 8. 两个方案怎么选

| | 增量方案（[数据库设计](database.md)） | 目标方案（本文） |
| --- | --- | --- |
| 改动范围 | 新增 4 张表，调整 1 张表 | 全部业务表换成新结构 |
| 代码改动 | 只改 task、matching、sync 相关代码 | 所有模块的 DAO 和大部分测试都要改 |
| 解决的问题 | 打通"审核 → 任务 → 发票比对 → 完成" | 同上，并解决第 1 节全部结构问题：财务和采购数据共享、类型统一、关系可查询、合同移出数据库 |
| 风险 | 低 | 中：数据转换和大量代码修改，需要逐模块验证 |
| 以后上线登录、多人协作 | 还要再处理一次按登录人隔离的问题 | 已经按组织共享，直接接入 |

**建议采用目标方案，并与架构第 4 步（模块重组）合并实施**：第 4 步本来就要按新分层重写每个模块，同时切换到新表，代码只改一次；每个模块独立切换、独立 PR，单次影响面可控。如果选择目标方案，[数据库设计](database.md)中的增量修改不再实施，其中已确认的业务规则（第 1、5、6、10 节）继续有效。

## 9. 待确认

1. 采用目标方案还是增量方案？
2. NS 供应商、子公司记录上是否有纳税人识别号字段？有的话发票销售方、购买方可以按税号精确比对，置信度更可靠。
3. 数据库中暂存的合同 PDF（`finance_task_documents.content`）：迁移时导出到共享盘，之后不再在数据库中保存文件内容，是否可以？

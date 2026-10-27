# 表与迁移对照

> 本文件由 `npm.cmd run db:map` 根据迁移链离线 MySQL DDL、实体定义和字段字典生成，请勿手工修改；迁移或实体变化后重新生成，`backend/tests/test_schema_map.py` 会检查是否过期。
> “修改”含加列、改列、索引与中文备注；数据回填仅在线执行，不在离线 DDL 中体现。

当前最新迁移：`0031_matching_invoice_files`；共 31 个迁移、40 张实体表。

## 1. 按模块查表

### source

| 表 | 中文说明 | 新建 | 后续修改 | 字段字典 |
| --- | --- | --- | --- | --- |
| `source_companies` | 采购公司（NS 子公司），与发票购买方比对 | `0001` | `0010` | [查看](current-data-dictionary.md#source_companies) |
| `source_customs_declarations` | 报关单 | `0001` | `0010`、`0027` | [查看](current-data-dictionary.md#source_customs_declarations) |
| `source_customs_lines` | 报关明细 | `0001` | `0010` | [查看](current-data-dictionary.md#source_customs_lines) |
| `source_customs_purchase_links` | 报关单与子采购单的关联，支持多对多与行级 | `0001` | `0010` | [查看](current-data-dictionary.md#source_customs_purchase_links) |
| `source_parent_order_lines` | 母采购行 | `0001` | `0010` | [查看](current-data-dictionary.md#source_parent_order_lines) |
| `source_parent_orders` | 母采购单 | `0001` | `0004`、`0005`、`0010` | [查看](current-data-dictionary.md#source_parent_orders) |
| `source_purchase_order_lines` | 子采购行：开票单元 | `0001` | `0010` | [查看](current-data-dictionary.md#source_purchase_order_lines) |
| `source_purchase_orders` | 子采购单 | `0001` | `0002`、`0004`、`0005`、`0010`、`0029` | [查看](current-data-dictionary.md#source_purchase_orders) |
| `source_raw_records` | NS 原始数据；内容变化时追加一行，主表指向最新一行 | `0001` | `0010` | [查看](current-data-dictionary.md#source_raw_records) |
| `source_sales_orders` | 销售单单头（币种、汇率），用于申报幅度与发票价格校验；不参与报关单内容摘要 | `0029` | — | [查看](current-data-dictionary.md#source_sales_orders) |
| `source_suppliers` | 供应商（NS vendor） | `0001` | `0010` | [查看](current-data-dictionary.md#source_suppliers) |

### review

| 表 | 中文说明 | 新建 | 后续修改 | 字段字典 |
| --- | --- | --- | --- | --- |
| `review_lines` | 审核冻结的子采购行范围，不可修改 | `0001` | `0006`、`0011` | [查看](current-data-dictionary.md#review_lines) |
| `review_purchase_bases` | 全局开票依据版本 | `0006` | `0011` | [查看](current-data-dictionary.md#review_purchase_bases) |
| `review_records` | 审核记录：一次审核通过一行，不可修改，全部行即审核历史 | `0001` | `0011` | [查看](current-data-dictionary.md#review_records) |

### task

| 表 | 中文说明 | 新建 | 后续修改 | 字段字典 |
| --- | --- | --- | --- | --- |
| `task_contract_jobs` | 财务审核提交后的合同自动归档队列，不保存 PDF | `0021` | — | [查看](current-data-dictionary.md#task_contract_jobs) |
| `task_declaration_documents` | 报关资料下载与归档记录（报关单、销售合同、发票），不保存 PDF | `0028` | — | [查看](current-data-dictionary.md#task_declaration_documents) |
| `task_documents` | 子采购合同：只记录共享盘路径 | `0001` | `0012` | [查看](current-data-dictionary.md#task_documents) |
| `task_events` | 任务状态历史，只追加 | `0001` | `0007`、`0012` | [查看](current-data-dictionary.md#task_events) |
| `task_external_groups` | Excel 导入外部群目录，待人工维护供应商关联 | `0017` | `0019`、`0020` | [查看](current-data-dictionary.md#task_external_groups) |
| `task_group_imports` | 外部群导入预览和确认留痕，不保存原始文件 | `0017` | — | [查看](current-data-dictionary.md#task_group_imports) |
| `task_lines` | 任务行：每条子采购行的应开与已收 | `0001` | `0007`、`0012` | [查看](current-data-dictionary.md#task_lines) |
| `task_notification_deliveries` | 企微通知执行及恢复证据 | `0022` | — | [查看](current-data-dictionary.md#task_notification_deliveries) |
| `task_notification_group_guards` | 同群跨任务发送互斥守卫 | `0022` | — | [查看](current-data-dictionary.md#task_notification_group_guards) |
| `task_notifications` | 供应商开票通知：每次保存一个版本 | `0001` | `0003`、`0012`、`0022` | [查看](current-data-dictionary.md#task_notifications) |
| `task_signed_contracts` | 回签合同上传记录，按子采购单一份，不保存文件正文 | `0028` | — | [查看](current-data-dictionary.md#task_signed_contracts) |
| `task_signed_upload_jobs` | 回签合同上传及后台归档队列，仅保存元数据，文件另存持久暂存目录 | `0030` | — | [查看](current-data-dictionary.md#task_signed_upload_jobs回签合同上传队列) |
| `task_supplier_groups` | 供应商默认企微群 | `0001` | `0012` | [查看](current-data-dictionary.md#task_supplier_groups) |
| `task_supplier_settings` | 供应商档案人工设置：是否开启供应商通知 | `0026` | — | [查看](current-data-dictionary.md#task_supplier_settings) |
| `task_tasks` | 开票任务：审核通过后按 供应商 × 采购公司 × 币种 分组 | `0001` | `0003`、`0007`、`0012`、`0028` | [查看](current-data-dictionary.md#task_tasks) |

### invoice

| 表 | 中文说明 | 新建 | 后续修改 | 字段字典 |
| --- | --- | --- | --- | --- |
| `invoice_headers` | 进项发票 | `0001` | `0008`、`0013` | [查看](current-data-dictionary.md#invoice_headers) |
| `invoice_items` | 发票行 | `0001` | `0008`、`0013` | [查看](current-data-dictionary.md#invoice_items) |
| `invoice_raw_records` | 柠檬云原始数据 | `0001` | `0013` | [查看](current-data-dictionary.md#invoice_raw_records) |
| `invoice_versions` | 发票不可变业务版本 | `0008` | `0013` | [查看](current-data-dictionary.md#invoice_versions) |

### matching

| 表 | 中文说明 | 新建 | 后续修改 | 字段字典 |
| --- | --- | --- | --- | --- |
| `matching_allocations` | 发票行与子采购行的比对与分配 | `0001` | `0009`、`0014` | [查看](current-data-dictionary.md#matching_allocations) |
| `matching_invoice_files` | 发票文件归档记录，按发票×报关单一份，不保存文件正文 | `0031` | — | [查看](current-data-dictionary.md#matching_invoice_files) |

### sync

| 表 | 中文说明 | 新建 | 后续修改 | 字段字典 |
| --- | --- | --- | --- | --- |
| `sync_cursors` | （无实体定义，代码不读写；说明见字段字典） | `0001` | `0015` | [查看](current-data-dictionary.md#sync_cursors) |
| `sync_lemon_bindings` | 柠檬云已有账号绑定状态，不保存凭据 | `0016` | `0018` | [查看](current-data-dictionary.md#sync_lemon_bindings) |
| `sync_lemon_jobs` | （无实体定义，代码不读写；说明见字段字典） | `0023` | — | [查看](current-data-dictionary.md#sync_lemon_jobs) |
| `sync_lemon_plans` | 柠檬云每日同步计划 | `0023` | — | [查看](current-data-dictionary.md#sync_lemon_plans) |
| `sync_lemon_runs` | 柠檬云拉票记录（手动或后台分片）与结果，不保存令牌 | `0018` | `0023`、`0025` | [查看](current-data-dictionary.md#sync_lemon_runs) |
| `sync_ns_runs` | NS 来源按批后台保存记录与结果，不保存令牌 | `0024` | — | [查看](current-data-dictionary.md#sync_ns_runs) |
| `sync_runs` | 同步运行记录 | `0001` | `0015`、`0023`、`0025` | [查看](current-data-dictionary.md#sync_runs) |

## 2. 按迁移查表

| 迁移 | 新建表 | 修改表 | 说明 |
| --- | --- | --- | --- |
| [`0001_baseline`](../../backend/migrations/versions/0001_baseline.py) | `invoice_headers`、`invoice_items`、`invoice_raw_records`、`matching_allocations`、`review_lines`、`review_records`、`source_companies`、`source_customs_declarations`、`source_customs_lines`、`source_customs_purchase_links`、`source_parent_order_lines`、`source_parent_orders`、`source_purchase_order_lines`、`source_purchase_orders`、`source_raw_records`、`source_suppliers`、`sync_cursors`、`sync_runs`、`task_documents`、`task_events`、`task_lines`、`task_notifications`、`task_supplier_groups`、`task_tasks` | — | 新表结构基线：一次创建 docs/architecture/database.md 第 4 节的 24 张表。 |
| [`0002_source_purchase_parent_order_no`](../../backend/migrations/versions/0002_source_purchase_parent_order_no.py) | — | `source_purchase_orders` | source：子采购单保存母采购单号。 |
| [`0003_task_review_revision_and_notification_fields`](../../backend/migrations/versions/0003_task_review_revision_and_notification_fields.py) | — | `task_notifications`、`task_tasks` | task：任务记录审核版本；通知记录发送员工与人工登记说明。 |
| [`0004_source_purchase_currency`](../../backend/migrations/versions/0004_source_purchase_currency.py) | — | `source_parent_orders`、`source_purchase_orders` | source：子采购单币种取自母采购单，记录币种来源与待核实原因。 |
| [`0005_source_ledger_versions`](../../backend/migrations/versions/0005_source_ledger_versions.py) | — | `source_parent_orders`、`source_purchase_orders` | source 版本化补强；不删除旧表或 v2 数据。上线后不可回退删除版本证据。 |
| [`0006_review_ledger_versions`](../../backend/migrations/versions/0006_review_ledger_versions.py) | `review_purchase_bases` | `review_lines` | review 版本化补强；不删除旧表或 v2 数据。上线后不可回退删除版本证据。 |
| [`0007_task_ledger_versions`](../../backend/migrations/versions/0007_task_ledger_versions.py) | — | `task_events`、`task_lines`、`task_tasks` | task 版本化补强；不删除旧表或 v2 数据。上线后不可回退删除版本证据。 |
| [`0008_invoice_ledger_versions`](../../backend/migrations/versions/0008_invoice_ledger_versions.py) | `invoice_versions` | `invoice_headers`、`invoice_items` | invoice 版本化补强；不删除旧表或 v2 数据。上线后不可回退删除版本证据。 |
| [`0009_matching_ledger_versions`](../../backend/migrations/versions/0009_matching_ledger_versions.py) | — | `matching_allocations` | matching 版本化补强；不删除旧表或 v2 数据。上线后不可回退删除版本证据。 |
| [`0010_source_comments`](../../backend/migrations/versions/0010_source_comments.py) | — | `source_companies`、`source_customs_declarations`、`source_customs_lines`、`source_customs_purchase_links`、`source_parent_order_lines`、`source_parent_orders`、`source_purchase_order_lines`、`source_purchase_orders`、`source_raw_records`、`source_suppliers` | source：补齐中文表与字段备注；降级仅恢复原备注，不删除业务数据。 |
| [`0011_review_comments`](../../backend/migrations/versions/0011_review_comments.py) | — | `review_lines`、`review_purchase_bases`、`review_records` | review：补齐中文表与字段备注；降级仅恢复原备注，不删除业务数据。 |
| [`0012_task_comments`](../../backend/migrations/versions/0012_task_comments.py) | — | `task_documents`、`task_events`、`task_lines`、`task_notifications`、`task_supplier_groups`、`task_tasks` | task：补齐中文表与字段备注；降级仅恢复原备注，不删除业务数据。 |
| [`0013_invoice_comments`](../../backend/migrations/versions/0013_invoice_comments.py) | — | `invoice_headers`、`invoice_items`、`invoice_raw_records`、`invoice_versions` | invoice：补齐中文表与字段备注；降级仅恢复原备注，不删除业务数据。 |
| [`0014_matching_comments`](../../backend/migrations/versions/0014_matching_comments.py) | — | `matching_allocations` | matching：补齐中文表与字段备注；降级仅恢复原备注，不删除业务数据。 |
| [`0015_sync_comments`](../../backend/migrations/versions/0015_sync_comments.py) | — | `sync_cursors`、`sync_runs` | sync：补齐中文表与字段备注；降级仅恢复原备注，不删除业务数据。 |
| [`0016_sync_lemon_bindings`](../../backend/migrations/versions/0016_sync_lemon_bindings.py) | `sync_lemon_bindings` | — | sync：持久化柠檬云绑定结果；降级拒绝丢弃绑定证据。 |
| [`0017_task_external_groups`](../../backend/migrations/versions/0017_task_external_groups.py) | `task_external_groups`、`task_group_imports` | — | task：外部群目录与导入预览；降级保留人工确认记录。 |
| [`0018_sync_lemon_runs`](../../backend/migrations/versions/0018_sync_lemon_runs.py) | `sync_lemon_runs` | `sync_lemon_bindings` | sync：持久保存账套选择与手动拉票结果；保留运行中记录，不能降级丢弃证据。 |
| [`0019_task_optional_group_time`](../../backend/migrations/versions/0019_task_optional_group_time.py) | — | `task_external_groups` | task：创建时间可缺省；无法降级为必填，以免伪造或丢弃已导入群资料。 |
| [`0020_task_optional_group_count`](../../backend/migrations/versions/0020_task_optional_group_count.py) | — | `task_external_groups` | task：群人数可缺省；无法降级为必填，以免伪造或丢弃已导入群资料。 |
| [`0021_task_contract_jobs`](../../backend/migrations/versions/0021_task_contract_jobs.py) | `task_contract_jobs` | — | task：审核事务登记合同自动归档队列，保留历史任务与合同记录。 |
| [`0022_task_notifications`](../../backend/migrations/versions/0022_task_notifications.py) | `task_notification_deliveries`、`task_notification_group_guards` | `task_notifications` | 企微发送台账与群守卫；发送证据不得通过降级删除。 |
| [`0023_sync_background`](../../backend/migrations/versions/0023_sync_background.py) | `sync_lemon_jobs`、`sync_lemon_plans` | `sync_lemon_runs`、`sync_runs` | 同步计划与持久任务队列。降级会丢弃待核实证据，明确禁止破坏性降级。 |
| [`0024_sync_ns_runs`](../../backend/migrations/versions/0024_sync_ns_runs.py) | `sync_ns_runs` | — | sync：NS 来源按批后台保存的持久请求与结果；保留执行中/待核实记录，不能降级丢弃。 |
| [`0025_sync_merge_lemon_jobs`](../../backend/migrations/versions/0025_sync_merge_lemon_jobs.py) | — | `sync_lemon_runs`、`sync_runs` | sync：柠檬云后台分片并入 sync_lemon_runs，sync_runs 只保留 phase 一个批次状态。 |
| [`0026_task_supplier_settings`](../../backend/migrations/versions/0026_task_supplier_settings.py) | `task_supplier_settings` | — | task：供应商档案"是否开启供应商通知"，人工维护，默认开启。 |
| [`0027_source_customs_created_at`](../../backend/migrations/versions/0027_source_customs_created_at.py) | — | `source_customs_declarations` | source：报关单保存 NS 创建时间，用于归档文件夹的月份（2026-10-23 业务确认按报关单创建日期）。 |
| [`0028_task_document_completion`](../../backend/migrations/versions/0028_task_document_completion.py) | `task_declaration_documents`、`task_signed_contracts` | `task_tasks` | task：报关资料与回签合同归档记录；任务新增 documents_incomplete（发票已收齐、资料待补齐）。 |
| [`0029_source_sales_orders`](../../backend/migrations/versions/0029_source_sales_orders.py) | `source_sales_orders` | `source_purchase_orders` | source：销售单单头（币种、汇率）与子采购单的销售单关联，供申报幅度与发票价格校验（2026-10-23）。 |
| [`0030_task_signed_upload_jobs`](../../backend/migrations/versions/0030_task_signed_upload_jobs.py) | `task_signed_upload_jobs` | — | task：回签合同分片上传与持久归档队列，不保存文件正文。 |
| [`0031_matching_invoice_files`](../../backend/migrations/versions/0031_matching_invoice_files.py) | `matching_invoice_files` | — | matching：发票文件归档记录（2026-10-26）。 |

# 真实业务 MySQL 数据库

## 当前代码与迁移入口

截至 2026-09-24，基础来源为[八张业务表](eight-table-relations.md)，另有[报关关联结果](customs-reconciliation-results.md)、发票数量分配及整票关联表。业务迁移代码 head 为 `0007_invoice_purchase_links`：`0004` 增加数量分配，`0005` 将报关依据移入独立表，`0006` 增加审核匹配预留字段，`0007` 增加整票关系。预留审核字段不表示匹配已经绑定财务审核，当前边界见[匹配模块](../../backend/modules/matching/README.md)。

业务迁移由 `backend/business_alembic.ini` 和 `backend/business_migrations/` 管理，使用 `npm.cmd run db:business:upgrade`。它依赖已有基础表与所需发票扩展，不是空库初始化入口；已有库不要重跑下方历史六表脚本。应用库审核、开票任务与回写使用另一套迁移和 `npm.cmd run db:upgrade`，见[双库边界](../project-structure.md)。本次目录整理只核对代码版本，没有访问或升级实际数据库。

历史正式来源导入、补拉和验收记录见[历史实施记录](../history/implementation-notes.md)。NS 按页拉取并保存已接入；持久定时同步未实现，具体来源接口要求见[同步模块](../../backend/modules/sync/README.md)。

## 历史六表初始化设计

以下内容保留原初始化设计及当时的实施状态，包括“六表／114字段”“尚未执行”“发票保存待实现”等阶段表述，不代表当前全部代码能力。初始化 SQL、扩展 SQL 与后续 Alembic 增量须分别核对，不能只执行一份历史 SQL 就认为当前业务库完整。

完整业务目标见[母子采购、报关审核与发票匹配数据库设计](purchase-customs-invoice-schema-design.md)：包含2026-09-22只读核实的六表143个实际字段，以及母采购、审核、匹配、同步和审计的新增表设计。该文档明确区分现有结构与计划；下文“六表／114字段”及未接入说明描述原始初始化版本，当前发票导入实现以[发票模块说明](../../backend/modules/invoice/README.md)为准。

当前设计只保留六张业务表：采购订单和报关单来源 NS，发票来源外部平台或文件导入。每张单据只保存一个来源的当前完整快照，后期来源变化时再扩展。

本目录是独立建库建表 SQL，不包含迁移，不改变现有应用数据库和 NS 回写表。已从本草案移除 `document_sources`、`sync_jobs`、`sync_targets`，来源信息直接放入主表；未删除任何实际数据库中的表。

针对进项发票 Excel 的[两表扩展设计](invoice-excel-design.md)及[增量 SQL 草案](invoice-excel-design.sql)已单独提供，覆盖票种、红冲状态、税务及记账字段、特殊税率和八位小数数量。它们尚未执行，也未合入下述六表初始化脚本；下文114字段等描述仍指原始六表版本。

## 六张表

| 表 | 中文用途 | 来源 |
| --- | --- | --- |
| purchase_orders | 子采购订单主表：单号、PL、母采购单、供应商、公司及整单金额 | NS |
| purchase_order_lines | 采购货品行：品名、规格、数量、单位、报关数量及行金额 | NS |
| customs_declarations | 报关单主表：真实报关单号、申报日期及申报主体 | NS |
| customs_declaration_lines | 报关明细：Packing NO.、公司、销售单、货源地、规格及数量 | NS |
| invoices | 发票主表：发票号码、购销方、金额、税额及外部来源 | 外部 |
| invoice_lines | 发票商品明细：商品名称、规格、数量、单价及税额 | 外部 |

6 张表、114 个字段均带中文 `COMMENT`。不增加拼表大表，采购和报关分别保存，查询时按 PL 与公司归组。

## 来源身份和去重

- 六张表均使用本地自增 `id`。NS 内部 ID 只保存在 `ns_internal_id` 字段中，不作为业务主键。
- NS 两张主表按 `tenant_id + ns_account + ns_internal_id` 唯一；两类单据分表保存，相同内部 ID 不冲突。
- 发票主表保存 `external_system`、`external_account`、`external_record_id`。没有外部稳定记录 ID 时，必须提供稳定 `import_key`，重复导入复用此键。
- 发票的外部记录 ID 和导入键分别在“租户＋外部平台＋外部账户”范围内唯一。来源标识创建后不随意改动；两个唯一键命中不同本地发票时，后端应报冲突，不能任意覆盖一张。
- 文件导入键应由后端依据已确认的稳定业务标识或可重放导入标识生成，不在每次导入时生成随机新键。同一发票来自不同文件时是否属于同单仍需校验，不能仅靠文件摘要判断。
- 真实报关号、发票号码保留为业务字段，暂不设全局唯一。发票代码可能缺失，不能只凭号码自动覆盖。
- 明细按 `tenant_id + 本地父单ID + source_line_key` 唯一。稳定行键来自来源行身份；显示行号和数组位置不能随意作为稳定键。
- `tenant_id` 由后端身份确定，所有查询带租户条件；NS 账户同样来自服务器配置。采购到报关的外键还要求 NS 账户相同，避免同号或同内部 ID 串单。

不预建多来源映射和来源版本切换机制，也不通过修改来源字段把另一张单据覆盖进来。未来更换来源时，另行设计身份对应与历史保留规则。

## 保存和查询规则

三张主表直接保存 `source_data`（单头及全部明细原始 JSON）、`source_modified_at`、`synced_at`、`last_complete_sync_at` 和 `detail_sync_status`。采购和报关已接入按PL读取、事务保存及本地查询；字段映射必须来自实际样本，目前真实环境尚未配置。外部发票商品行不等同于NS收票关联行，发票保存仍待实现。

1. 在数据库事务外读取并校验完整单头及全部明细，确认来源身份、行键和数值精度。
2. 开启短事务，根据来源唯一键定位主表，按主表行锁串行保存同单数据；首次写入的唯一键竞争由后端处理。
3. 按父单及稳定行键保存明细。只有完整读取成功后，才能停用此次快照中已不存在的旧行。
4. 原始 JSON、单头、明细及成功时间在同一事务提交，`detail_sync_status` 设为 `complete`。
5. 读取失败保留旧快照；已有主表可记录 `failed`，不清空最后完整数据。首次失败不创建伪完整单据。

当前没有持久同步任务或占用表。按PL保存使用MySQL账户范围命名锁，覆盖完整读取到事务提交；同一身份／NS账户的另一个保存请求立即返回409，避免不同PL引用同一报关单时并发覆盖。源版本时间有映射时还拒绝旧版本。没有后台进度、断点续传或任务恢复，现有NS回写锁未复用。

本地查询关联各自父单，检查租户、主从有效状态和 `last_complete_sync_at`；刷新失败但存在旧完整快照时可继续显示并提示刷新失败。采购报关按同一 NS 账户内的 PL 和公司引用归组。PL／公司缺失或歧义需提示，不直接横向多对多连接两侧货品行。

## 数值与时间

- 金额、数量使用 DECIMAL(24,6)，单价 DECIMAL(24,8)，税率 DECIMAL(12,8)，例如 13% 保存为 `0.13`。后端 Decimal，接口传十进制字符串。
- 缺失保留 NULL，区别于零；保留红冲等负值，合法性由业务校验。超精度先校验，不依赖数据库静默舍入。
- 采购整单金额与行金额分开，不能把整单金额重复累加；采购数量／单位与报关数量／单位各自配套。不同币种不混算。
- `source_data` 使用原生 JSON，精确小数按约定编码为字符串，避免先转 float。
- 业务日期为 DATE，同步时间为 UTC DATETIME(6)。应用每个连接也需统一时区。

## 执行方式

执行文件：[business-schema.sql](business-schema.sql)。要求 MySQL 8.0.16+、InnoDB、utf8mb4；目标库为 `financial_invoice_business`。

```text
mysql --default-character-set=utf8mb4 -h 服务器地址 -u 数据库账号 -p
```

进入后执行：

```sql
SOURCE D:/ai/feiShu/Financial-Invoice-System/caiwufapiaoxitonghedui/docs/mysql/business-schema.sql;
SHOW TABLES FROM financial_invoice_business;
```

本脚本只用于新库一次建表。若此前已执行九表版，不直接重跑此脚本，本次未提供删表或迁移 SQL；需要修改真实库时再按实际数据处理。没有 DROP、TRUNCATE、授权或关闭外键检查。DDL 中断不会像普通事务一样整体回滚，不使用 `--force` 忽略错误。

执行脚本不会自动保存单据。独立业务库连接、采购报关保存及本地查询已接入，使用方式见 [PL保存说明](../pl-storage.md)。外部发票适配仍待实现；不替换现有 `DATABASE_URL`。

## 接入本地 MySQL

在项目根目录 `.env.local` 填写以下分项配置。该文件被 Git 忽略；不要把真实密码放入 `.env.example` 或前端配置。

```dotenv
BUSINESS_MYSQL_HOST=127.0.0.1
BUSINESS_MYSQL_PORT=3306
BUSINESS_MYSQL_DATABASE=financial_invoice_business
BUSINESS_MYSQL_USER=你的MySQL用户名
BUSINESS_MYSQL_PASSWORD='你的MySQL密码'
```

分项配置中的密码使用原文，不需要 URL 编码；特殊字符按 dotenv 引号规则填写。USER 为空时业务库不启用。也支持单独设置 `BUSINESS_DATABASE_URL=mysql+pymysql://...`，使用完整 URL 时密码需 URL 编码，且不能同时填写分项 `BUSINESS_MYSQL_*`。

执行只读检查：

```powershell
npm.cmd run db:business:check
```

退出码 0 表示连接成功且六张表可见；退出码 1 表示未配置、连接失败或缺少表。检查不会创建、删除或迁移表。需要先手动执行本文件前述六表 SQL；不要使用 `db:upgrade` 初始化这个独立业务库。

修改环境变量后重启后端。已登录用户可调用 `GET /api/business/database-status`，沿用现有 Cookie 或服务密钥身份验证；未登录返回 401。接口返回：

| 字段 | 含义 |
| --- | --- |
| configured | 是否已启用业务库配置 |
| connected | 是否连接并完成表清单读取 |
| ready | 六张基础表是否可见；不代表字段、写入权限或自动落库已验证 |
| state | not_configured未配置、connection_failed失败、schema_incomplete缺表、connected成功 |
| message | 中文检查结果，不含连接串或密码 |
| missingTables | 缺失的预期业务表名 |

连接池启用失效检测与回收，每个新连接设置 UTC 和 utf8mb4。业务库暂不可用时检查接口明确报告失败，原有应用库、NS实时读取及回写链路不因业务库未配置而被切换。启动不自动建表，也不执行单据同步。

## 验证范围

2026-09-14：在单独的临时 MySQL 8.4.9 实例执行当前 SQL，成功创建 6 张表，核实 114 个字段及全部表备注含中文。19 项约束拒绝检查通过，覆盖重复 NS 来源、重复外部发票来源／导入键、来源键缺失或空白、重复明细、跨租户和跨 NS 账户关联、非法 JSON 与同步状态。

另验证不同 NS 账户同内部 ID 可以分别保存、不同父单可使用相同行键、DECIMAL 大金额原值读写与 NULL 数量保留、主从更新事务整体回滚。临时实例已关闭，未连接现有业务数据库。以上是 SQL 存储约束验证，不代表应用同步、并发协调、外部发票接入或真实 NS 联调已完成。

独立连接接入验证：17项新增测试通过，覆盖配置隔离、特殊字符密码、错误脱敏、身份验证、缺表提示及连接池释放；全部后端测试79项通过、1项专用MySQL回写测试跳过，后端lint通过。另在隔离MySQL 8.4.9实例验证真实连接、两个连接的UTC／utf8mb4设置及受保护状态接口。正式本地MySQL已通过只读连接与六表可见性检查；尚未写入真实NS单据。

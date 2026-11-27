# task 模块：开票跟进

## 流转记录步骤与操作人（2026-11-27）

单任务和供应商合并详情新增 `history`，统一包含流程事件与已获取的子采购合同。`task_history_mapper` 以完整微秒时间排序，同刻的事件按原事件主键先后排列，同刻合同获取排在状态记录之前；从最早操作开始编号 `sequence=1..N`，响应按最新在前返回。因此生成任务是第 1 步，倒序展示时仍保留原步骤号。合并详情在完整成员范围内统一编号，并保留各 CD 的原因及每份原合同获取记录，不因合同展示去重而丢失历史。

每条记录返回稳定 `id`、`sequence`、`kind`、`at`、`label`，事件另含原始 `actor`、展示用 `actorName` 和 `reason`，合同另含 NS 与归档信息。操作人通过 `identity.public.actor_names` 在同一只读连接批量解析，人员已停用仍可显示已同步姓名；未知人员沿用原始标识，不臆造姓名。`contract_recovered` 明确显示“子采购合同补存成功”，不再套用当时的任务状态名称。原 `events`、`documents` 字段和审计数据保留，无表结构或写入行为变化。

验证：`backend/tests/test_task_history.py` 覆盖同刻事件、微秒差异、大主键、首步编号、合并范围、停用人员姓名、一次批量解析和原审计不变；查询次数仍由既有性能回归约束。

## 工作台与应收看板读取优化（2026-11-26）

`workbench_tasks(connection, now, task_ids=None)` 可按指定任务 ID 读取；不传时保留全部未被替代版本的原范围。只读取金额必需的任务行字段和来源名称，节点复用 `board_facts(node_only=True)`；不读取本入口不展示的来源阻断及通知范围。应收看板自 2026-11-27 改为读取全部当前任务，再通过 review 只读门面批量读取其财务审核通过时间；金额缺失与节点口径不变。

## 收票概况展示（2026-11-26）

任务摘要新增 `receivedAmount`，在 `followup_policy.fields` 从任务行已收金额以 Decimal 汇总；无任务行时为未知。供应商合并摘要沿用当前成员范围汇总，成员任务保留各自的金额、CD 和子采购单。应开或待收金额未知时继续返回 NULL，已收金额不由应开减待收或百分比推算，不改变差异结束、超收、取消分配和任务完成规则。前端“发票比对”节点只展示这些后端结果，无数据库迁移。

## 查询性能优化（2026-11-26）

供应商合并详情与原任务详情共用 `service/task_detail_reader.py` 批量装载，再复用 `TaskService` 原有展示与能力组装。合同、通知历史、最新联系、报关资料、回签、作业、事件、来源依据与供应商群均按本次范围读取；通知范围按供应商身份批量展开，保留历史任务及其固定通知成员。`scopeRevision` 复用同次读取的有序事实，写入时仍在原事务和锁内重新计算，不使用跨请求缓存。

任务台先读取任务头、去重的任务与子采购单关系及资料/通知状态，复用原步骤规则统计全部节点并定位分组和页码；分页后才读取当前页完整任务行、来源校验、名称和最近联系。供应商组始终包含全部成员，命中某张 CD 或子采购单时仍展开完整办理范围。进行中与已完成分开、节点筛选、等待顺序、金额和可执行能力均保持原口径。全范围节点统计仍需读取轻量事实，没有引入预计算状态或更改表结构。

本机同一 MySQL 数据（342 个进行中原任务、90 个供应商办理组），预热后计时三次取中位数；只调用查询 Service，连接强制只读，不启动后台任务或调用真实 NS/企微。该计时不含浏览器网络与渲染，也不含诊断分析器开销，与先前带分析器的计时不可直接比较。

| 查询 | 优化前 | 优化后 | SQL 次数（前 → 后） |
| --- | ---: | ---: | ---: |
| 42 个原任务的合并详情 | 1624.13 ms | 80.30 ms | 2239 → 27 |
| 27 个原任务的合并详情 | 799.10 ms | 55.38 ms | 1141 → 27 |
| 23 个原任务的合并详情 | 527.66 ms | 45.60 ms | 865 → 27 |
| 供应商列表第一页，20 组 | 180.27 ms | 110.24 ms | 26 → 28 |
| 报关单列表第一页，20 项 | 199.66 ms | 50.20 ms | 25 → 27 |

列表增加的固定查询用于轻量计数与分页后装载，完整明细及来源校验范围缩小到当前页。32 组优化前后完整响应快照一致，覆盖两种分组、六种节点、翻页、越界页、CD 筛选、空结果、不同大小的供应商详情与原任务详情。

验证入口新增 `backend/tests/test_task_query_performance.py`：任务成员增加时查询次数不增长、分页仅装载当前页完整数据、跨页节点总数一致、进行中与完成范围隔离、未知发送结果对重审核后继继续生效。相同断言由 `test_task_query_performance_mysql.py` 在随机专用 MySQL 库复用，5 项通过；原合并通知并发/回滚测试 `test_supplier_tasks_mysql.py` 在随机专用库运行，3 项通过。既有通知、合同、金额和状态测试继续使用原入口。

验证边界：后端 lint、架构检查和变更文件格式检查通过。全量 API 首轮为 2224 通过、215 跳过、3 失败；其中发票比对的旧步骤断言与原有 `skipped` 规则不符，核对 Git 原规则后修正测试，12 项发票比对测试复测通过。另两处历史迁移测试（`test_schema_comments.py`、`test_wecom_directory.py`）对 `review_customs_import_jobs` 的表范围预期未更新，单独复现仍失败；本次没有修改迁移、表结构或这两处测试。浏览器端到端耗时尚未测量。

## 供应商合并办理（2026-11-26）

合并详情新增 `notificationDocuments`：按本次通知的成员范围返回全部子采购合同，包含未登记下载、待保存、失败和已归档项，保留原 `taskId`、报关单与失败原因；单任务该字段为 `null`，沿用 `documents`。通知区不再按已归档文件名筛选，已通知成员的资料仍在全量 `documents` 中，但不混入本次通知清单。`notification.attachments` 继续仅包含已归档文件名；`scopeReason` 返回本次范围实际已归档/总份数，未齐时明确要求补齐，不再声称已附带全部合同。该清单只反映数据库归档状态，发送时仍复核文件可读性、摘要与全部范围，不改变原发送校验。

任务摘要 `TaskSummary` 返回 `recordNumber`（CD 编号）与 `declarationNumber`（真实报关单号，来源缺失时为空）。通过 source 的 `SourceDirectory.declarations` 只读门面批量读取，不从归档路径或合同名反推；供应商合并摘要汇总全部成员的真实报关单号，成员摘要各自保留原单号。

详情另返回 `reviewRows`（每个报关单及审核版本的任务生成时通过依据与子采购单张数）、`declarationRows`（每个报关单的报关单文件/销售合同/发票状态及原操作任务 ID）和 `preparation`（子采购合同已归档数/总数、是否已齐、待补回签数与说明）。`task_detail_mapper` 只转换既有冻结审核和归档事实，不查询或改变审批与完结状态；来源失效仍通过原 `sourceMessage/compare` 明确提示。子采购合同携带 `recordNumber/declarationNumber`，保留合并前的归属。无表结构变化。

`POST /api/task/board/query` 支持 `groupBy: supplier | declaration`，兼容旧客户端时默认 `declaration`；正式前端默认 `supplier`。按来源账户、供应商 ID、采购公司 ID、币种合并，身份不全时独立展示，不按名称猜测身份。查询命中某张 CD 或子采购单后返回该供应商完整办理范围，再按组分页与统计；进行中和已完成分开，不包含已被替代的任务。金额由后端 Decimal 汇总。

- `GET /api/task/supplier-tasks/{taskId}`：以原任务为锚点读取完整进行中范围，无进行中任务时回看完成范围；`?completed=true` 明确读取已完成范围。返回 `grouped/memberTasks/scopeRevision/notificationTaskId`，资料和应开行携带原 `taskId`，报关资料另带 `recordNumber`。原任务详情接口保持可用。
- `POST /api/task/supplier-tasks/{taskId}/notification/draft`：原草稿参数加 `scopeRevision` 与 UUID `requestId`。短事务锁定成员、复核版本，每个待通知原任务追加通知版本；`task_events` 的 `supplier_notice_scope` 事件固定成员任务与通知 ID、根执行任务、请求摘要。相同请求可核实重放，范围变化返回 409。已通知或进入收票的成员只展示，不再加入新通知。
- `POST /api/task/supplier-tasks/{taskId}/notification/record`：原登记参数加 `scopeRevision`，同一事务确认固定范围全部成员，失败整批回滚。保存过多成员合并草稿后，单任务保存、单任务登记与列表批量登记均提示进入合并详情，防止仅改部分成员。
- 企微继续使用现有预览、提交、回执与核实接口，`notificationTaskId` 指向根执行任务。快照固定全部通知成员、审核版本、依据、正文与合同；上传前后重新校验，附上全部范围内的子采购合同。合同同单不同源/不同摘要时阻止发送；超过现有 9 附件上限时明确拒绝，不截断。未决执行保护全部成员及重审核后继；仅确认目标群回执后登记各原通知。结果未知时继续禁止重发。

实现：`supplier_task_dao`、`supplier_task_policy`、`SupplierTaskService` 负责只读合并；`SupplierNotificationService` 与 `notification_scope` 复用原通知、归档及发送管道。没有任务/审核/收票台账物理合并，没有表结构迁移。页面授权沿用 `invoice-followup`，写入仍禁止服务身份。

验证入口：`test_supplier_tasks.py` 覆盖完整分组分页、身份隔离、原资料归属、草稿幂等、已通知成员排除、过期范围拒绝、整批回滚、企微全附件与未知结果、HTTP 会话；`test_supplier_tasks_mysql.py` 在随机专用 MySQL 库验证并发占用与整批回滚。未配置 MySQL 建库连接时明确跳过，不以 SQLite 代替并发验证。

## 组合搜索（2026-10-28）

正式节点查询为 `POST /api/task/board/query`，新增 `supplierName`（供应商名称）、`recordNo`（CD 号）、`purchaseOrderNo`（子采购单号）。均为可选字符串，去除首尾空白后最多 120 字符，空值不限；按包含文字匹配，多个条件取交集，`%`、`_` 按普通字符搜索。子采购单命中任一任务行即返回完整任务。节点计数、总数和分页共用过滤条件。

供应商和单号经 `SourceDirectory.search_task_filters` 只读门面获取完整匹配 ID，避免旧关键词的 500 条截断。旧 `keyword`、`supplierId` 继续兼容；`/api/tasks/board/query` 保留一版本，复用相同 DTO、身份校验与 Service，旧调用方升级后移除。下文旧路径描述保留兼容入口语义。

架构 v2 第 4c 步新建。海关与财务审核均通过后按 供应商 × 采购公司 × 币种 生成开票任务，跟进合同归档、供应商通知与收票进度。表结构见[数据库设计](../../../docs/architecture/database.md)第 4.3、6 节。

4d 补强已接入全局依据、任务后继与差异结束。包括已完成任务在内，依据变化时整体替代并按台账重算；兼容分配承接，口径不兼容保留待复核占用。

## 职责

- 订阅 `InvoiceReady`：在审核事务中生成任务与任务行（应开值从审核行复制），重新审核时替代旧任务。供应商档案关闭通知的供应商不生成任务（2026-10-23）。
- 任务生成及账本更新后，matching 的同事务订阅方自动重评相关已有发票并生成待审核整单建议（2026-10-30）；无需到发票页手动重新生成。仅生成建议，不自动收票；匹配规则与验证见 [matching 说明](../matching/README.md#任务生成后自动匹配已有发票2026-10-30)。
- 合同：审核事务中登记持久归档作业，事务提交后后台从 NS 下载子采购合同并保存到共享盘，数据库只记录路径与 SHA-256。
- 通知：保存通知版本、登记人工发送，以及企微群发预览、提交、回执和未知结果核实。
- 供应商默认企微群配置。
- 收票进度（第 4d 步接入）：订阅 matching 的 `AllocationChanged`，按已通过分配的合计更新任务行已收与任务状态（`service/progress_service.py`）。

## 拥有的表

`task_tasks`、`task_lines`、`task_documents`、`task_notifications`、`task_events`、`task_supplier_groups`、`task_external_groups`、`task_group_imports`。迁移 `0003` 增加 `task_tasks.review_revision`（审核版本）、`task_notifications.sender_name`（发送员工）与 `note`（登记说明）。

## 目录

| 层 | 文件 | 说明 |
| --- | --- | --- |
| controller | `task_controller.py` | `/api/tasks`：`POST /query`、`GET /{id}`、`POST /{id}/documents/{orderId}/prepare`、`POST /{id}/notification/draft`、`POST /{id}/notification/record`、`POST /notification/record-batch` |
| | `supplier_group_controller.py` | `/api/tasks/supplier-groups`：`/query`、`/suppliers/query`、`/wecom/query`、`/save` |
| service | `task_generation_service.py` | `on_review_approved`：生成、分组、跳过已有有效行、替代旧任务 |
| | `task_status_service.py` | `change_status`：任务状态唯一修改入口，检查转换表并写状态历史 |
| | `task_service.py` | 列表（分组分页、搜索、统计）与详情 |
| | `document_service.py` | 合同下载、登记、归档 |
| | `notification_service.py` | 通知版本与人工发送登记 |
| | `notification_batch_service.py` | 原任务登记规则与旧批量接口兼容 |
| | `notification_group_service.py` | 列表按组展开、范围复核、整组事务与逐组结果 |
| | `supplier_group_service.py` | 供应商群查询与保存 |
| dao | 每张表一个文件 | 只访问本模块的表 |
| policy | `task_policy.py` | 状态机、分组键、状态文案 |
| | `notification_policy.py` | 默认通知正文、可编辑 / 可登记判断 |
| mapper | `task_mapper.py`、`notification_mapper.py` | 行 → VO |

## 规则

**生成（数据库设计第 7 节第 3 步）**

- 分组键：供应商 + 采购公司 + 币种；任一身份缺失时按子采购单隔离，不凭名称合并。
- 同一子采购行只有一条有效任务行（生成列唯一约束）：同依据复用原任务行并追加报关证据事件；变化则建立后继任务，未变行不遗漏。
- 新审核替代旧审核：按受影响采购行定位旧任务（含已完成），写替代历史；新任务保存 predecessor_task_ids。
- 订阅方在审核事务中执行，失败时整个审核回滚；不调用外部系统。

**状态（数据库设计第 6.2 节）**

```text
documents_pending → notify_pending → awaiting_invoice → partially_received → completed
任何当前任务状态 → superseded
```

- 合同全部归档 → `notify_pending`；登记人工发送 → `awaiting_invoice`。
- `partially_received`、`completed` 只由已通过分配的汇总驱动，不提供手动修改；发票可能先于合同或通知到达，此时直接进入收票节点。
- 取消已通过的分配后按实际收票退回：仍有收票 → `partially_received`；没有收票 → 收票前节点（已登记通知 → `awaiting_invoice`；合同已全部归档 → `notify_pending`；否则 `documents_pending`）。
- 任务行（数据库设计第 6.1 节）：数量相等且金额相差不超过 0.01 元为已收齐；超开单独标记，不能自动结束；显式差异结束绑定当前依据和账本摘要。
- 重新审核时，被替代任务行的已收进度带到同一子采购行的新任务行，新任务按进度直接进入相应节点。
- 详情页六个节点各按自身事实显示（合同是否归档、通知是否登记、是否收票、是否完成），不因任务完成而标记未做的步骤；当前节点按已发生的业务事实推进（2026-11-17，见下文“节点按业务事实推进”）。
- 每次状态变化写 `task_events`。

**合同**：事务外下载 → 短事务登记首次获取记录（来源与 SHA-256）→ 事务外写共享盘（2026-10-26 起新归档使用 `YYYY年MM月/CD号_真实报关单号/子采购单号_供应商简称_真实报关单号.pdf`，月份取 NS 报关单创建时间的中国日期）→ 短事务标记已归档。再次获取到不同内容时拒绝覆盖；共享盘失败记为 `failed` 并可重试。

文件名简称规则见 `policy/contract_name_policy.py`：去除企业后缀、开头城市名后的“市”和一个常见末尾行业词（去行业词后至少保留四字），不截固定字数。例如“东莞市创远机械有限公司”变为“东莞创远”；无法可靠缩减时保留。只影响文件名，NS 查询、供应商匹配及业务记录仍用全称。已归档文件保留原文件名和路径。

**通知**：每次保存新增一个版本（需带当前版本号，不一致返回 409）；群名与启用的默认群一致时记录群 ID。登记发送要求合同已全部归档、已填写群名和发送员工、确认已发送并填写说明，发送时间带时区且介于任务生成与当前之间；同一登记的重试返回原结果。

**身份**：`service:` 身份只读，所有写操作返回 403。

**来源变化**：任务按审核时冻结的应开值跟进；来源关键变化时阻止继续推进合同、通知和新分配，保留待复核占用；财务重新审核后建立后继任务。

## 公开接口与依赖

- `public.py`：`open_lines(connection, purchase_line_ids=None, lock=False)`——有效任务行（应开、已收、单位）及所属任务（供应商、采购公司、币种、报关单）；`lock=True` 时按"任务 → 任务行"顺序加锁，供 matching 审核分配使用。
- 订阅：`InvoiceReady`（双审核后生成任务）、`AllocationChanged`（收票进度），均在 `app.py` 中登记。
- 读取：`source.public.SourceDirectory`（供应商、采购公司、子采购单号、行品名、供应商分页）。通过 `review.public.current_bases` 核对当前依据；任务生成仍只经审核事件取得冻结值。
- 外部适配：`SubpoContractSource`（NS 合同）、`integrations/contract_archive.py`、`integrations/wecom.py`。
- 订阅关系在 `app.py` 中登记：`events.subscribe(InvoiceReady, on_review_approved)`。

## 验证

`backend/tests/test_task.py`（SQLite，source 与 review 真实保存）：生成与冻结值、重新审核替代、已完成后换版、分组与隔离、订阅方失败回滚、列表搜索统计、详情、合同归档与拒绝覆盖、通知版本与登记、只读、供应商群、HTTP。合同/通知失败保护见 `test_task_evidence.py`，新链路与 MySQL 并发见 matching 测试。

## 差异结束

`POST /api/tasks/{taskId}/lines/{lineId}/close` 接收 `requestId`、`purchaseBasisId`、`ledgerSha256`、`reason`。后端核对当前版本和账本，禁止待复核时结束；追加结构化 `difference_closed` 事件。请求编号唯一，重复提交返回原结果；台账/依据变化后旧决定不再适用。

2026-10-30：另订阅 matching 的 `LinesClosedByDifference`（`closure_service.on_lines_closed_by_difference`，登记在 `app.py`）。整单关联确认时发票少于子采购单，在同一比对事务内对差额明细追加 `difference_closed` 事件并按差异结束，原因取审核说明；请求编号由整单组与子采购行派生，重复提交不重复结束；依据已变化或有待复核占用时整个确认回滚。人工结束与该订阅共用 `close_line`。

`closure_service.py` 管理该事务，`basis_guard.py` 在合同/通知推进前复核来源；`progress_service.py` 只消费 matching 发布的绝对合计。待复核占用按原分配口径展示，不作为当前有效收票。

## 单位名称展示（2026-10-16）

开票任务行的单位通过 source 只读门面解析为单位名称，仅影响展示，不修改原始编号、数量金额或审核／比对结论。字典缺失、停用及未知编号保留原值，规则与兼容表归属见 [source 单位说明](../source/README.md)；验证见 `backend/tests/test_unit_display.py`。

## 供应商档案（2026-10-16）

- 独立页面 `/suppliers`，供应商来自子采购同步产生的 source 主数据；不另建供应商副本。新增 `POST /api/tasks/supplier-groups/profiles/query`：供应商/群/群主关键词、NS 环境、全部/未绑定/启用/停用筛选和后端分页，返回供应商 NS ID 及当前群绑定。
- `SupplierProfileService` 经 `SourceDirectory.suppliers` 读取来源，task DAO 仅查询群绑定并提供 ID 条件；source DAO 不访问 task 表。绑定继续写入 `task_supplier_groups`，不新增表。
- 新增 `POST /api/tasks/supplier-groups/wecom/match`，请求 `supplierId/keyword/page/pageSize/refresh`。名称取自服务端：规范化同名、包含全称、去企业后缀后包含（至少 4 字）依次推荐；不猜测地域或品牌。手填关键词支持群名、群主姓名/ID、群 ID，返回匹配依据；同名多个群全部保留，由用户选定。
- 保存仍使用 `/save`，提交 `supplierId/chatId/revision/enabled`；群名和群主由企微重新查询，不接受前端伪造。仅停用原群可离线完成，已有乐观版本保护保留。此页不发送通知。
- `/query`、`/suppliers/query`、`/wecom/query` 暂留一版本兼容原维护客户端；新页面仅使用档案查询和名称匹配，下一版本确认外部调用方迁移后再删除旧接口。
- 新验证：`backend/tests/test_supplier_profiles.py` 覆盖候选排名/歧义、分页、权限、真实保存、绑定状态筛选、环境隔离与旧版本拒绝；渠道使用假实现，不代表真实企微已联调。

### 企微群目录持久化与后台同步（2026-10-29）

`WecomDirectoryService` 管理业务 MySQL 内的群目录和同步队列，`WecomDirectoryWorker` 在应用生命周期内每 2 秒检查一次；`WeComGroups` 只负责企微读取及进度回调。名称匹配复用 `supplier_group_policy`。目录独立于 Excel 导入表，不把文件资料当成企微实时核验结果。

- 搜索只读取本地数据库，无目录时创建队列并立即返回，不等待网络。首次查询启动该凭证范围的目录，此后每次成功 5 分钟后自动同步；进程重启复用目录，未完成作业重新全量读取。`refresh=true` 只排队，重复点击与并发查询复用正在运行的作业。
- 后台先分页列出群 ID（每页 100），再最多 6 路并发查询详情。进度包括 queued / listing / details / ready / failed；分页结束前不猜总数，完成顺序按真实请求完成回报，详情进度最多每 0.5 秒写入一次。全部详情完成且快照发布后才显示 100%。
- `task_wecom_directories` 保存范围摘要、同步状态、进度和上次成功时间；`task_wecom_directory_groups` 保存群 ID、群名、群主 ID/姓名、人数及创建时间。只存企业与 Secret 的 SHA256 摘要用于隔离，不存 Secret、令牌或完整成员名单。
- MySQL 命名锁保证同库同范围一个消费者，网络读取不持有数据库事务。成功后短事务批量发布完整目录，已消失或失权群标为不可用；失败回滚，不发布残缺数据。普通网络故障保留上次完整快照并标明时间、错误，60 秒后重试；明确授权失败停止提供该快照。与旧内存缓存不同，旧快照不因超过 24 小时而删除，始终标注过期，保存及发送前仍实时核验。
- 企业或凭证变化使用独立目录；同步前后检查范围，旧作业不能发布到新范围。进程关闭先等待目录工作线程结束，再关闭企微客户端与数据库。
- `/wecom/match` 与兼容 `/wecom/query` 保留分页、匹配规则和原有 `directoryUpdatedAt`、`directoryStale`、`directoryRefreshing`、`directoryRefreshError`；新增 `directoryHasSnapshot`、`directoryState`、`directoryDiscovered`、`directoryCompleted`、`directoryTotal`（未知时 null）、`directoryPercent`（未知时 null）。`items=[]` 且 `directoryHasSnapshot=false` 表示目录尚不可用，不能提示“没有匹配群”；成功同步空目录的 `directoryHasSnapshot=true`。

部署：新增迁移 `0039_task_wecom_directory`，执行 `npm.cmd run db:upgrade`、构建前端并重启后端后生效；不修改旧迁移和已有供应商绑定。验证见 `test_wecom_directory.py`（重启、进度、慢网络、失败、发布回滚与范围隔离）、`test_wecom_groups.py`（适配器）、`test_supplier_profiles.py`（本地匹配与实时保存）；`test_wecom_directory_mysql.py` 仅在专用 MySQL 上验证跨实例互斥，无连接时跳过。测试不访问真实企微。


## 外部群 Excel 导入与手动关联

新增 `/api/tasks/external-groups` 接口：

| POST 路径 | 请求 | 响应 / 行为 |
| --- | --- | --- |
| `/import/preview` | filename、content（原 XLSX base64）、account（可选，推荐匹配的 NS 环境） | importId 与有效/错误/有候选/无候选数量；只保存预览，不写群目录或绑定 |
| `/import/query` | importId、page、pageSize | 七列原值、行号、错误、匹配依据、最多 5 个候选、候选总数和无冲突预选建议；只有预览创建者可读 |
| `/import/confirm` | importId、selections[{rowNo,supplierId,revision,replaceExisting}] | 确认有效群及所选关联，返回真实 imported/bound/skipped；相同请求幂等 |
| `/query` | keyword、status（all/unbound/bound）、page、pageSize | 已导入目录与现有关联，后端搜索分页；停用的绑定仍属于“已关联” |
| `/associate` | chatId、catalogRevision、supplierId、revision、replaceExisting | 后续人工维护一个供应商默认群；只使用已确认目录中的群与群主字段 |

表头严格按七列顺序：群名、群人数、群主、群主所在部门、创建时间、外部群id、群主id。支持 ID 表头大小写和首尾空白；ID 内容区分大小写。单工作表、4MB、1000 数据行；创建时间可为空或任意格式，能识别的日期按时区转 UTC（无时区按北京时间），无法识别、公式或错误值保存为空，接口 createdAt 返回空字符串，页面显示“未提供”。群人数同样可空或任意格式：整数、数字文本及“8人”等可识别内容保存为人数；无法识别、负数、小数、公式、错误值或超出数据库整数存储范围的内容保存为 NULL，接口 memberCount 返回 null，不显示为 0。其余列的公式、错误值、非法字段、缺失 ID、重复 chat_id 都产生错误行；整表结构错误拒绝预览。错误行在确认时明确跳过，有效群全部导入，未选择供应商的群保留待维护。

候选仅复用后端保守名称匹配，不猜品牌或地域简称。仅一个候选且没有其他群争用该供应商、不会替换其他默认群时返回预选建议；所有写入仍需用户确认。跨 NS 环境同名必须核对身份。保存后启用默认群，可从原供应商档案停用；一个供应商一个默认群，一个群可以对应多个供应商。

`GroupImportPreview` 负责不可变预览；`GroupImportService` 负责同事务确认；`ExternalGroupService` 负责目录和后续关联。两种写入与原企微实时维护共用 `group_binding_writer`，只导入本模块 DAO，经 source 门面读取供应商。通用 XLSX 归档检查提取到 `core/xlsx_archive.py`，发票导入复用相同检查。

迁移与表结构见 [数据库设计](../../../docs/architecture/database.md)。新增 `test_external_groups.py` 覆盖格式、预选歧义、原子回滚、重放、身份、分页、过期与版本冲突；`test_external_groups_mysql.py` 仅在专用 MySQL 连接存在时验证并发。导入不调用企微网络或发送消息，不代表文件内群主仍是实时群主。

创建时间可选由新增迁移 `0019_task_optional_group_time` 调整，不修改旧迁移及已有日期。部署执行 `npm.cmd run db:upgrade` 并重启；旧预览保留原校验结果，需要重新上传文件。

群人数可选由新增迁移 `0020_task_optional_group_count` 调整，保留已有计数。升级并重启后重新上传文件，旧预览不自动重算。

## 审核后自动归档（2026-10-16）

迁移 `0021_task_contract_jobs` 新建本模块 `task_contract_jobs`，不修改历史迁移、旧任务及既有合同。`task_generation_service` 创建任务时同事务按子采购单去重登记作业和审核身份；审核回滚不留下下载作业，重复审核不重复入队。

`service/contract_worker.py` 由应用生命周期启动，每 2 秒检查一次已提交队列，逐一复用 `DocumentService.prepare`。下载不占审核事务，也不延迟审核响应。NS 仅被只读调用；全部合同归档才推进资料节点，收票已推进的任务不倒退。失败持久保留原因并由现有任务详情 `documents[].status/error` 展示，人工点击“保存到共享盘”复用相同服务重试。失败不无限自动重试、不自动通知供应商。

MySQL 命名锁保证多实例单消费者，并对同一任务的同一子采购合同互斥，人工与后台不会同时下载。进程意外中断的作业保留 pending，重启后继续；已取得的合同仍按首次来源、摘要和时间核对，不静默覆盖文件。正常退出等待当前合同完成后再关闭客户端和数据库。已失败作业保留 failed，不因重启重试；被替代或来源失效的任务由原有校验阻止归档。

升级前任务没有作业，不在启动时批量下载历史合同；原手动保存接口保持可用。配置文件仅使用根 `.env`，不加载 `.env.local`，进程环境变量仍优先；合同 RESTlet 配置与真实共享目录必须可用。

验证：`test_contract_jobs.py` 覆盖审核回滚、重复提交、提交后下载、失败展示、手动重试、重启恢复与任务换版；`test_contract_jobs_mysql.py` 验证多消费者与人工保存互斥，须配置专用 MySQL 测试连接。测试采用合成合同及临时目录，不代表真实 NS／NAS 联调。

## 企微通知接入（2026-10-19）

新增 `delivery_controller.py`、通知执行/群守卫 Entity 和 DAO、`delivery_submit_service.py`、`delivery_receipt_service.py`、`delivery_reconcile_service.py`。方案、接口、默认关闭的发送配置及恢复规则见[通知方案第 13 节](../../../docs/wecom-supplier-notification-plan.md#13-第一阶段实现与部署2026-10-19)。

迁移 `0022_task_notifications` 新增 `task_notification_deliveries` 和 `task_notification_group_guards`。准备、创建、待群主确认、成功、失败、未知结果分别持久记录；创建不重试，未决记录保留群占用且阻止人工登记绕过。历史与任务状态区分 manual / wecom；企微创建成功不会推进收票节点，只有目标群成功回执才补证据并按原任务状态推进。

新增预览/提交/本地历史/回执刷新/候选核实接口；DTO 只接受版本、摘要和记录 ID。记录及候选只读查询不创建群发。所有操作复用认证身份、来源依据保护（先锁任务行再复核）和 task 模块写锁，外部调用不占事务。

验证入口：`test_deliveries.py`、`test_delivery_recovery.py`、`test_wecom_messaging.py`、`test_deliveries_mysql.py`；真实渠道联调及专用 MySQL 并发未在本次执行。

## 跟进列表展示字段

`POST /api/tasks/query` 请求和分组分页不变，`groups[].tasks[]` 与详情 `task` 增加以下只读字段，无需迁移：

| 字段 | 口径 |
| --- | --- |
| `outstandingAmount` | 未结束任务行逐行 `max(应开金额 - 有效已收金额, 0)` 后汇总的十进制字符串；已结束（含差异结束）、被替代行不再待收。任一应开金额缺失或无明细为 null |
| `receiptPercent` | 有效已收金额合计 / 应开金额合计 × 100，Decimal 四舍五入至一位小数；超收保留超过 100 的实际值。应开金额缺失或合计非正为 null，不判断任务完成 |
| `receiptBarPercent` | 同一进度限制在 0–100 的展示条宽字符串；无法计算为 null |
| `lastContactAt` | 本任务已发送通知中最大的实际发送时间（UTC ISO）；无记录为 null。人工登记与企微确认均计入，草稿、失败、待确认不计入 |
| `followupEmployee` | 上述最近发送记录的员工姓名；不是采购负责人，缺失为空字符串 |
| `waitingLabel` | 自任务创建起经过的完整天数；完成与被替代任务只返回终态文案 |

`policy/followup_policy.py` 负责只读计算，`notification_dao.latest_sent_by_tasks` 一次批量查询本页任务的最近已发送记录。不读取 matching 私有表，不新增状态转换或写入。针对性验证见 `backend/tests/test_task_followup.py`。

## 供应商通知开关、归档目录与供应商筛选（2026-10-23）

- **是否开启供应商通知**：新表 `task_supplier_settings`（迁移 `0026_task_supplier_settings`），没有记录视为开启。供应商档案页人工维护：`POST /api/tasks/supplier-groups/profiles/notify`，请求 `{supplierId, enabled, revision}`，`revision` 为当前版本（从未设置为 0），不一致返回 409；服务身份 403；供应商不存在 404。档案列表每行返回 `notify: {enabled, revision, updatedBy, updatedAt}`。
- **关闭的效果**：之后的财务审核不为该供应商生成开票任务（`task_generation_service.on_review_approved` 跳过该供应商的任务组）；同一报关单的其他供应商照常生成。已有任务不变。连带结果：该供应商子采购合同不会自动归档，其发票在比对中没有可分配的任务行。开关与企微外部群绑定无关。
- **归档目录**：`integrations/contract_archive.py` 按 `月份/CD号_真实报关单号/` 建两级文件夹；子采购合同命名见上文，其他资料文件名以单据类型开头。报关单头经 source 门面 `SourceDirectory.declarations` 读取；缺 NS 创建时间、CD 编号或真实报关单号时归档失败并保留原因（409），不改用其他日期或编号，补齐同步后可重试。原有安全措施不变：临时文件、同名同内容复用、同名不同内容不覆盖、路径不越出根目录。已按旧规则归档的文件不移动，记录中的原路径不变。
- **开票跟进按供应商筛选**：`TaskListQuery.supplierId`（数字 ID）；列表返回 `suppliers` 选项（未被替代的任务涉及的供应商，名称经来源目录读取），计数与分页随筛选变化。
- 验证：`backend/tests/test_task_supplier_notify.py`、`test_contract_archive.py`。

## 资料归集与完结规则（2026-10-23）

**业务规则**：子采购合同、报关单、销售合同、发票、回签合同全部到齐，且发票收齐（或按差异结束），任务才完结；发票已收齐但资料未齐时停在新状态 `documents_incomplete`（资料待补齐），资料到齐后自动完结。报关资料下载失败或未完成**不影响通知供应商**（通知仍只等子采购合同）。2026-10-23 前已完成的任务不因新规则回退。NS 回写队列本期不做。

| 资料 | 来源 | 记录 | 说明 |
| --- | --- | --- | --- |
| 子采购合同 | NS 专用 RESTlet | `task_documents`（按任务×子采购单） | 原有流程不变；归档后进入待通知 |
| 报关单、销售合同、发票 | NS 报关资料 RESTlet（约定见 [NS 适配器](../../integrations/netsuite/README.md)） | `task_declaration_documents`（按报关单×类型，各供应商任务共用） | 审核通过生成任务时登记待下载，后台队列处理；每类可单独重试或重新下载 |
| 回签合同 | 人工批量上传 | `task_signed_contracts`（按子采购单） | 按文件名识别子采购单号；不阻塞通知与收票 |

- 全部文件保存到 `月份/CD号_真实报关单号/`，子采购合同命名见上文，其他资料文件名以类型开头（`报关单_CD号.pdf`、`回签合同_子采购单号.pdf` 等）；同名不同内容不覆盖。
- **单项重试**：`POST /api/tasks/{taskId}/declaration-documents/{type}/prepare`（type：customs_declaration / sales_contract / invoice），返回任务详情。失败、未配置、已归档都可再次执行；已归档的重新下载内容相同时无变化，内容不同返回 409 且保留原文件。后台只处理待下载记录，失败后不自动反复重试。本功能上线前生成的任务没有登记记录，首次人工重试时补登记。
- **回签合同上传**：`POST /api/tasks/signed-contracts/upload`，请求 `{files: [{filename, content(base64), orderNo?}]}`，每次 1–20 个；支持 PDF、JPG、PNG，单个不超过 10 MB。逐个返回 `saved`（含已上传过相同文件）/ `unmatched`（未识别单号或子采购单未关联报关单）/ `ambiguous`（匹配多个单号）/ `conflict`（已有不同文件，未覆盖）/ `failed`（格式、大小、共享盘问题）。识别规则：文件名包含的有效子采购单号，一个单号包含另一个时取较长者；`orderNo` 填写时按该单号精确匹配。
- **任务详情**新增 `declarationDocuments`（类型、状态、文件路径、失败原因、尝试次数、`retry` 能力）、`signedContracts`（每张子采购单是否已上传）与 `completion`（是否齐全、尚缺资料）。
- 资料到齐（报关资料归档、回签合同上传、子采购合同归档）时，在同一事务中重算相关任务状态。
- 2026-10-26：报关单、发票支持原 NS 打印的 Excel XML（`.xls`）及旧 PDF，路由和后台队列不变；按适配器校验格式命名。重新下载改变内容、格式或份数时在写文件前拒绝，保留旧记录，无需迁移。NS Excel RESTlet 已部署为 485/1，真实下载及共享盘保存已验证；运行中服务需重启加载配置，任务队列状态联动待验收，销售合同尚未接入。参见 [外部下载接入说明](../../../netsuite/declaration_print/README.md)。
- 验证：`backend/tests/test_task_documents_completion.py`、`test_task_documents.py`（NS 适配器）；收票类测试使用 `tests/documents_ready.py` 补齐资料。

## 开票跟进节点查询（原采购开票任务台）

`POST /api/tasks/board/query`（`controller/board_controller.py` → `service/task_board_service.py`，只读）：请求 `{keyword, supplierId, node, page, pageSize, stage?, createdFrom?, createdTo?}`，`node` 为空表示全部进行中，或 `documents / notification / invoices / comparison / completion / done`。上线只同步 NS 正式环境，不提供 NS 环境筛选（多传 `account` 返回 422）。

前端统一入口 `/tasks`。工作台下钻的 `stage` 与成对日期复用原查询的报关单最慢阶段、来源创建日期口径；指定阶段且未选节点时包含该范围内已完成的同单任务。原 `/api/tasks/query` 暂留一个版本供旧客户端及兼容性测试使用，新前端统一调用节点查询；旧客户端迁移后删除旧查询契约。

- 六个节点与详情页共用 `task_mapper.steps`（新增稳定 `key`），资料齐全用 `document_mapper.completion_of`，通知文案用 `notification_mapper.status_label`；任务按当前节点（最后一个已完成节点之后的第一个未完成节点）归入分区（`policy/board_policy.py` 负责分区文案与下一步提示）。
- 响应：`nodes`（各分区计数，覆盖全部筛选结果）、`openTotal`、`items[]`（`task` 摘要、`steps`、`currentNode/currentLabel`、`nextAction`、`blockedReason`、`missing`）、`suppliers` 与分页。进行中按等待最久在前；已完成分区按最新在前并在数据库分页。
- 来源或依据变化用 `basis_guard.changed_task_ids` 批量判断，只提示“暂不能推进”，不改变状态。批量读取新增 `document_dao.archived_orders`、`notification_dao.latest_by_tasks`、`task_dao.by_statuses`。
- 进行中任务全部参与节点判定（逐个按事实计算），数据量大时为 O(进行中任务数)；已完成任务只按状态计数。
- 验证：`backend/tests/test_task_board.py`。

## 业务状态与筛选（2026-10-23）

规则只在 `policy/stage_policy.py` 一处，经 `public.py` 暴露 `STAGES`、`STAGE_LABELS`、`task_stage`、`declaration_stage` 供工作台汇总：

| 业务状态 | 判定 |
| --- | --- |
| 待审批 | 报关单待财务审核，或来源变化需重新审核（review 判断，优先于任务状态） |
| 待通知开票 | 任务处于待保存子采购合同、待通知供应商 |
| 待核票 | 任务处于等待开票、部分收票 |
| 资料已回 | 任务发票已收齐、资料待补齐（documents_incomplete） |
| 开票完成 | 任务发票收齐且资料全部到齐（completed） |

报关单级别取其当前任务中**最慢**的阶段；审核通过但没有任何当前任务（供应商均关闭通知）为“无需开票”，不进分区与待办。

- 开票跟进列表新增条件：`stage`（notify / invoicing / documents / completed，按报关单所处阶段筛选，显示该报关单的全部当前任务）、`createdFrom` / `createdTo`（报关单 NS 创建时间的中国日期，须成对填写，经 source 门面换算）。每个任务返回 `stage` / `stageLabel`（本任务自身阶段）。
- 状态只读汇总，不提供人工修改业务状态的接口。
- 验证：`backend/tests/test_business_stages.py`。


## 回签合同后台上传队列（2026-10-26）

新界面使用 `SignedUploadService`、`SignedUploadWorker`：单文件最高 100 MiB，每批 20 个，更多文件自动分批。先提交清单，再按接口返回的 `chunkBytes`（4 MiB）逐片上传；每片最多 6 MiB JSON，避免整批 Base64 常驻内存。文件完整落盘并记录摘要后进入持久队列，返回 202；后台逐文件调用既有 `SignedContractService.process_content` 匹配、无覆盖归档并更新任务完结状态。单项失败保留原因，不阻止同批其他文件。

| 接口 | 请求 / 响应 |
| --- | --- |
| `POST /api/tasks/signed-contracts/upload-jobs` | `{requestId: UUID, files: [{filename, size, orderNo?}]}`；返回批次和服务端文件 ID。同身份同 requestId 同清单幂等，清单变化拒绝。空文件或超过 100 MiB 的文件逐项 failed。 |
| `POST /api/tasks/signed-contracts/upload-jobs/{batchId}/files/{fileId}/chunks` | `{offset, content: Base64}`；按偏移接收，重复片内容必须一致，不支持跳跃写入；响应带接收字节数和处理进度。 |
| `GET /api/tasks/signed-contracts/upload-jobs` | 当前登录身份最近 20 批；每批包含逐文件结果和进度。 |
| `GET /api/tasks/signed-contracts/upload-jobs/{batchId}` | 查询一个持久批次；跨身份返回 404，服务身份不可操作。 |
| `POST /api/tasks/signed-contracts/upload-jobs/{batchId}/files/{fileId}/retry` | `{orderNo?: string}`；已完整接收且未保存的文件可补单号并重新排队，无需重新传输。 |

原 `POST /api/tasks/signed-contracts/upload` 为一个版本的兼容入口，保留每批 20 个、单文件 10 MiB 的原同步契约，请求上限 280 MiB；正式前端已无调用方，旧客户端升级到分片协议后删除。普通 JSON 接口仍限 128 KiB，不全局放大。

新表 `task_signed_upload_jobs`（迁移 `0030`）只存清单、偏移、摘要、操作者、结果及路径。文件暂存在 `SIGNED_CONTRACT_UPLOAD_ROOT`（默认 `data/signed-contract-uploads`），不得放到临时清理目录；Docker 已有 `./data:/app/data` 挂载可持久保存。同库多进程需共用同一暂存目录。上传和消费者使用 MySQL 命名锁；重启接续 queued/running，原件先核对大小及摘要，归档复用同内容幂等与不覆盖保护。成功登记后清理该原件暂存；失败及未传完的原件保留用于人工重试，管理员清理前须核实任务状态。文件尚未传完时关闭页面不会继续传输，已经接收完整的文件会继续归档。

部署：执行 `npm.cmd run db:upgrade`，构建前端并重启后端。验证包括 100 MiB 分片边界、旧 128 KiB 故障回归、身份隔离、重复清单/分片、磁盘未提交尾部恢复、摘要损坏拒绝、单文件隔离和重启恢复；MySQL 并发测试单独标记，没有专用库时跳过，不能作为并发通过。

## 供应商开票时效（2026-10-27）

`GET /api/tasks/supplier-groups/profiles/invoicing-speed`：近 90 天发票收齐的任务，统计通知供应商到发票收齐的天数，按供应商取平均（一位小数），从慢到快返回前 8 家，超过 15 天标为偏慢。通知时间取任务首次进入 `awaiting_invoice` 的事件时间，收齐时间取首次进入 `documents_incomplete` 或 `completed` 的事件时间（`event_dao.first_reached`，不含被替代任务）；规则在 `policy/invoicing_speed_policy.py`。供应商档案接口另返回 `counts`（全部、已绑定开票群、未绑定、已关闭通知），不受关键字与状态筛选影响。测试：`backend/tests/test_invoicing_speed.py`、`test_supplier_profiles.py`。

## 工作台节点事实（2026-10-27）

- 判定当前节点所需的事实读取从 `TaskBoardService` 抽出为 `service/board_facts.py`（`board_facts`），任务台与工作台共用，节点计数一致。
- 2026-10-28 `public.py` 新增 `unbound_notify_suppliers(connection, tasks)`：入参为 `workbench_tasks` 结果（调用方可先按账套筛选），返回“待通知供应商”节点中供应商未绑定企微开票群的家数、任务数与前 5 家名称，供工作台提醒；“未绑定”与供应商档案筛选同一口径。
- `workbench_tasks` 每个任务新增 `node` / `node_label`（未完成任务按事实判定，已完成为 done）、`status_reason`、`waiting_days`（未完成任务自生成起的天数）；原拼接等待天数的 `reason` 移除。`public.py` 新增暴露 `NODES`、`NODE_LABELS`。
- 2026-11-18 `public.py` 新增 `archived_declaration_files(connection, declaration_ids, doc_type="customs_declaration")`：返回报关资料归档现状 `{报关单 ID: {status, files}}`，供 settlement 把已归档的报关单放入结汇资料包；只读，不触发下载。

## 节点按业务事实推进（2026-11-17）

- 原规则以“第一个未完成节点”为当前节点，已收票但没有通知记录的任务会停在“通知供应商”，落后于实际进度。现 `task_mapper.steps` 以最后一个已完成节点之后的第一个未完成节点为当前节点；被越过但事实未发生的节点 `state = "skipped"`：通知节点说明“未通知即收票”，资料准备节点说明“子采购合同未归档，完结前需补齐”（子采购合同仍是完结必需资料，见完成节点的“尚缺”）。
- 跳过只影响节点展示与任务台分区，不补写通知记录，也不改变任务状态机；`notification_mapper.status_label` 与通知历史仍按实际记录。
- 资料准备节点完成时说明改为“子采购合同已归档”，原“原件已备齐”易被误读为完结资料齐全；完结仍缺其他资料时追加“完结仍缺：报关单、回签合同…”（`steps` 新增 `missing` 参数，取 `completion.missing`）。
- 真实通知统计仍按发送记录：`workbench_tasks` 新增 `notified`（有发送记录），工作台漏斗“已通知供应商”扣除位置已越过通知、但有任务无发送记录的报关单，单列为 `notification_skipped`“未通知即收票”；下一步“已收到发票”的通过率仍相对按位置越过通知的报关单数计算。“待通知供应商”指标及节点分布按节点判定，未通知即收票的任务不再计入待通知。
- 测试：`test_task_board.py::test_receipt_without_notification_advances_by_facts`、`test_workbench.py::test_funnel_notified_counts_send_records_only`。

## 供应商档案分字段搜索（2026-10-28）

`POST /api/task/supplier-groups/profiles/query` 接收 `supplierName`、`groupName`、`owner`，分别搜索供应商名称、已绑定外部群名称、群主姓名或账号。支持部分匹配和批量输入：中英文逗号、分号、换行分隔，最多 50 条，每条最多 120 字符；框内 OR、框间 AND，空项忽略、重复项去重，通配符作为普通字符。绑定状态与群条件一并过滤；无匹配 ID 不能退化为不限制。source 门面按名称和 ID 范围过滤后分页。顶部供应商概况仍为全量，不随搜索变化。

旧 `/api/tasks/supplier-groups/profiles/query` 和 `keyword` 保留一个版本兼容旧前端；正式前端已切换新路径，旧调用方升级后删除该别名。其余群维护接口不变。

供应商档案 `profiles/query.status` 新增 `bound`（任意群绑定，含停用绑定）与 `notify_off`（供应商通知关闭，与群绑定是否启用无关），用于概况卡筛选；与名称、群名、群主条件取交集，先筛选再分页。原 all/enabled/disabled/unbound 保留，概况 counts 不随筛选变化。无需数据库迁移。

## 供应商人员关联与历史归属（2026-11-13）

入口 `/suppliers/owners`，复用供应商档案页面权限 `supplier-profiles`，不额外限定系统管理员。服务身份维持只读。主键为供应商本地 ID × 采购公司本地 ID；两个 ID 已包含 NS 来源身份，不能跨账套关联，也不按名称猜测身份。同一供应商不同抬头可以由不同人员负责，币种不影响这项分工。

| 接口（前缀 `/api/task/supplier-owners`） | 中文说明 |
| --- | --- |
| `GET /options` | source 有效供应商、已出现在子采购中的有效采购抬头、identity 已导入的当前成员及北京时间日期；选择负责人不要求对方已启用平台登录 |
| `POST /query` | `supplierName/companyId/memberId/status/groupStatus/page/pageSize`；status 为 all/assigned/unassigned/scheduled，groupStatus 为 all/bound/unbound。条件取交集并先筛选再分页，单页最多 50 条。行返回 `groupBound`，概况 `counts` 按供应商与采购抬头组合计数，不随筛选或分页变化。已停用的群绑定仍属于已绑定；仅有未来安排的关系归入待生效。 |
| `GET /{supplierId}/{companyId}/history` | 全部保存版本，含姓名快照、生效日期、操作者、原因和 UTC 保存时间 |
| `POST /preview` | `{items:[{supplierId,companyId,revision}],memberId,effectiveDate,reason,transferOpenTasks}`，一次最多 100 条，返回变更关系数、未完成任务数、交接能力及 `previewToken` |
| `POST /save` | 预览参数加 `previewToken`；同一账本短事务内重新校验版本、成员及任务状态，整批成功或整批回滚，返回实际 saved/transferredTasks |

仅新增 `task_supplier_owners` 一张九字段历史表：id、supplier_id、company_id、member_id、member_name、effective_date、reason、actor、created_at。每次变更只追加一行，不另建当前关系与版本表，不保存重复的 revision 和 updated_at；接口 revision 使用该组合最新记录 ID 进行并发校验。生效日期按北京时间解释，未来版本到期后新任务自动采用，无须定时修改历史。相同生效日以最新版本为准；补录旧日期只影响后续生成任务的选择，不倒填历史业务。列表分开显示当前人员与待生效安排。

任务归属复用既有 `task_events`：创建事件的 `details.owner` 保存生成时的人员快照，显式交接追加 `owner_transferred` 事件，同样保存人员 ID、姓名及分工记录 ID，occurred_at 为实际 UTC 生效时间。新任务无配置时也保存空归属，防止日后误用供应商当前人员归算。默认仅调整新业务；勾选交接才追加未完成任务的人员时间线与 `owner_transferred` 事件，已完成或已被替代的任务不交接。未来日期或早于当前有效版本日期的调整不能提前交接现有任务，预览返回原因；实际交接时再操作。旧任务首次交接前无人员事件时返回未知，不猜测交接前人员，也不额外补写未知记录。

只读门面 `owner_at_time(connection, task_id, occurred_at)` 返回业务发生时的人员快照，时间参数统一为 UTC 无时区时间；未归属时为空。后续 KPI 应按各指标约定的业务发生时点读取归属，并按采购单/依据等业务身份避免任务换版重复计数。本次仅建设人员归属事实，不实现 KPI 分数、权重或采购额统计。

部署先执行迁移 `0043_task_supplier_owners`，只新增上述历史表；手动脚本见 `backend/migrations/manual/0043_task_supplier_owners.sql`，不得与自动迁移重复执行。不自动更新既有人事或业务归属；已有归属数据时禁止直接降级删除。实现按 controller/dto/vo、关联 DAO、任务归属 DAO、reader/service 分层，跨模块只通过 source/identity 只读门面。

验证：`test_supplier_owners.py` 覆盖日期、历史、整批回滚、预览冲突、新任务快照与显式交接；`test_supplier_owners_mysql.py` 使用专用随机 MySQL 库验证同一预览并发保存。未提供 `BUSINESS_MIGRATION_TEST_SERVER_URL` 时跳过 MySQL 专项，不将 SQLite 结果视为 MySQL 并发验收。

## 批量登记线下已通知（2026-11-19）

采购在系统外（企微群、电话等）通知供应商后，在开票跟进列表勾选任务一次登记，不必逐个进入详情填写发送时间。只登记，不调用企微。

- 列表使用按组入口 `POST /api/tasks/notification/record-groups`：请求 `{groupBy: "supplier" | "declaration", groups: [{id, scopeRevision}], note?, notifiedOn?}`，每次至多 50 个列表组。`id` 是组锚点任务编号；后端按账户、供应商、采购公司、币种展开完整组，再选出当前可登记成员。单组或本次合计原任务超过 50 条仍可办理，不在前端展开、切分请求。
- 每组一个独立事务，组内原任务全部通过原登记校验后才提交；任一成员失败则整组回滚，其他组继续。列表返回 `notifyScopeRevision`，覆盖组成员、任务状态、最新通知、开票依据和可登记条件；提交时在任务锁内重新计算，不一致整组跳过，不能把新成员静默加入已确认范围。
- 按组响应 `{groups: [{id, status: "recorded" | "skipped" | "unknown", taskIds, reason}], recordedGroups, recordedTasks, skippedGroups, unknownGroups}`。数据库提交结果无法确认时保留“待核实”，不自动重试；已提交组的结果不冒充整批回滚。已保存的合并通知仍须从合并详情统一登记，不能改用报关单模式绕过完整成员保护。
- 旧 `record-batch` 的单任务请求与响应在一个版本内保留，供尚未升级的客户端使用；正式列表已改调 `record-groups`，待旧客户端升级完成后删除旧入口。旧接口的 50 条限制不适用于按组入口。
- 接口：`POST /api/tasks/notification/record-batch`，请求 `{taskIds: ["1", ...], note?, notifiedOn?: "YYYY-MM-DD"}`，一次 1–50 个不重复的任务；页面授权沿用 `invoice-followup`，服务身份返回 403。`notifiedOn` 为北京时间通知日期，不接受客户端时间戳；旧客户端不传日期时取登记当时。
- 响应 `{recorded: [{id}], skipped: [{id, reason}]}`。每个任务一个事务，逐个重新校验；不符合条件的跳过并附原因，不影响其他任务；数据库不可用时停止后续，已登记的不回滚。
- 可登记条件（`policy/notification_policy.batch_record_block`）：任务状态为 `notify_pending`（子采购合同已全部归档）、最新通知未发送、来源与开票依据未变化、没有未决的企微通知。不要求先保存群名称和通知正文。
- 登记内容（`service/notification_batch_service.py`）：通知日期默认今天，可选历史日期。后端拒绝未来日期；早于某任务生成日期的任务逐项跳过。今天取实际登记时刻；历史日期按北京零点折 UTC 保存，同任务生成日时不早于任务生成时刻。版本更新、状态历史等审计时间仍取实际登记时刻。最新版本是草稿时直接登记该草稿，保留其正文与群名称；没有草稿时新增一个版本，正文固定注明“系统未发送消息，未保存通知正文”，群名称取已启用的供应商默认群，发送员工取操作者姓名（飞书人员副本，找不到时为操作者标识）。说明为空时记为“批量登记：线下已通知供应商开票”。
- 登记后与单个登记一致：通知版本为 `sent`、渠道 `manual`，任务转为 `awaiting_invoice` 并写入状态历史。重复提交按“已登记”跳过，不产生第二条记录。
- 任务台 `BoardItem` 返回 `notifyRecord`（`allowed/reason`）、`notifyTargets`（`[{id, supplier, recordNumber, orderNumbers}]`）及 `notifyScopeRevision`。`taskIds` 仍是完整合并成员；`notifyTargets` 仅供确认清单展示，本次可登记范围排除已通知、合同未齐、来源失效或受合并通知保护的成员。合并组只要有可登记成员就允许勾选；请求提交组锚点与范围摘要，由后端重新展开。未决企微通知仍在提交时复核，列表不预先判断。
- 无表结构变化，无需迁移。验证：`tests/test_task_notification_batch.py` 覆盖兼容接口；`tests/test_notification_groups.py` 覆盖 51 成员整组提交、业务/数据库故障整组回滚且其他组继续、成员/草稿变化、重复提交、已通知排除、合并通知保护、DTO 和 HTTP。`test_notification_groups_mysql.py` 提供并发重复提交及回滚专项；未提供专用测试连接时明确跳过。

## 应收看板（2026-11-23）

只读审计页（页面代码 `invoice-recovery`，归“采购”），不改变任务、节点或通知；处理仍在开票跟进中进行。

- 接口：`POST /api/task/recovery/query` 返回概况卡、近 4 个月回收、按采购员回收率、未收回金额集中度与分组清单；
  `POST /api/task/recovery/export` 按同一条件导出全部任务（CSV，逐任务一行，单元格防公式）。
- 开票月份（2026-11-27 业务口径调整）：当前任务通过 `review_id` 关联的财务审核记录 `approved_at`，按北京时间日期所在月份归属。任务一经双审核放行生成即计入，合同未归档、尚未发送供应商通知也纳入；通知发送、重发与草稿不改变月份。财务审核与海关审核跨月时仍取财务审核日期，不用任务创建时间代替。
- 日期由 `review.public.review_approval_times(connection, review_ids)` 在同一连接批量读取。仅统计未被替代任务；重审核后的后继任务按自己的审核版本归属，旧任务不重复计算。审核记录缺失返回可恢复错误，不以任务创建日期猜测，也不静默漏计。
- 回收期限：开票月份的次月最后一天，当天仍算未逾期；默认月份仍为“本月到期”的上月审核，`month=all` 为全部月份。
- 请求 `month` 与接口路径保持兼容。任务及分组新增 `approvedOn`（财务审核通过日期）；旧响应字段 `notifiedOn` 保留一个版本作为同一日期的兼容别名，不表示供应商实际发送时间，旧看板客户端升级后移除。CSV 列名改为“开票月份”“财务审核通过日期”。不改通知记录、审核记录、任务状态或数据库结构。
- 已收回：发票全部收齐，即任务进入 `documents_incomplete` 或 `completed`；部分收票仍算未收回，金额取未收部分（与跟进列表同一口径）。
- 采购员：供应商 × 采购抬头当天已生效的最新负责人（`task_supplier_owners`），没有负责人为“未指定”（筛选值 `none`）。
- 逾期卡不受开票月份限制：所有已过期限、仍未收齐的任务。
- 金额：应开金额缺失的任务只计件数（`unknown`），不以 0 计入合计。
- 回收率按任务数计算；任务金额、节点、供应商与子采购单号沿用 `workbench_tasks`，与开票跟进一致。
- 口径集中在 `policy/recovery_policy.py`（纯函数），读取在 `service/recovery_service.py`。

验证：`test_task_recovery.py` 覆盖无通知任务直接纳入、实际通知跨月不改变归属、UTC 月底转换、任务延后生成、重新审核替代、回收期限、金额与 CSV；MySQL 的真实只读核对不替代隔离测试，也不触发真实通知。

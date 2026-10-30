# task 模块：开票跟进

## 组合搜索（2026-10-28）

正式节点查询为 `POST /api/task/board/query`，新增 `supplierName`（供应商名称）、`recordNo`（CD 号）、`purchaseOrderNo`（子采购单号）。均为可选字符串，去除首尾空白后最多 120 字符，空值不限；按包含文字匹配，多个条件取交集，`%`、`_` 按普通字符搜索。子采购单命中任一任务行即返回完整任务。节点计数、总数和分页共用过滤条件。

供应商和单号经 `SourceDirectory.search_task_filters` 只读门面获取完整匹配 ID，避免旧关键词的 500 条截断。旧 `keyword`、`supplierId` 继续兼容；`/api/tasks/board/query` 保留一版本，复用相同 DTO、身份校验与 Service，旧调用方升级后移除。下文旧路径描述保留兼容入口语义。

架构 v2 第 4c 步新建。财务审核通过后按 供应商 × 采购公司 × 币种 生成开票任务，跟进合同归档、供应商通知与收票进度。表结构见[数据库设计](../../../docs/architecture/database.md)第 4.3、6 节。

4d 补强已接入全局依据、任务后继与差异结束。包括已完成任务在内，依据变化时整体替代并按台账重算；兼容分配承接，口径不兼容保留待复核占用。

## 职责

- 订阅 `ReviewApproved`：在审核事务中生成任务与任务行（应开值从审核行复制），重新审核时替代旧任务。供应商档案关闭通知的供应商不生成任务（2026-10-23）。
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
| controller | `task_controller.py` | `/api/tasks`：`POST /query`、`GET /{id}`、`POST /{id}/documents/{orderId}/prepare`、`POST /{id}/notification/draft`、`POST /{id}/notification/record` |
| | `supplier_group_controller.py` | `/api/tasks/supplier-groups`：`/query`、`/suppliers/query`、`/wecom/query`、`/save` |
| service | `task_generation_service.py` | `on_review_approved`：生成、分组、跳过已有有效行、替代旧任务 |
| | `task_status_service.py` | `change_status`：任务状态唯一修改入口，检查转换表并写状态历史 |
| | `task_service.py` | 列表（分组分页、搜索、统计）与详情 |
| | `document_service.py` | 合同下载、登记、归档 |
| | `notification_service.py` | 通知版本与人工发送登记 |
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
- 详情页六个节点各按自身事实显示（合同是否归档、通知是否登记、是否收票、是否完成），不因任务完成而标记未做的步骤。
- 每次状态变化写 `task_events`。

**合同**：事务外下载 → 短事务登记首次获取记录（来源与 SHA-256）→ 事务外写共享盘（2026-10-26 起新归档使用 `YYYY年MM月/CD号_真实报关单号/子采购单号_供应商简称_真实报关单号.pdf`，月份取 NS 报关单创建时间的中国日期）→ 短事务标记已归档。再次获取到不同内容时拒绝覆盖；共享盘失败记为 `failed` 并可重试。

文件名简称规则见 `policy/contract_name_policy.py`：去除企业后缀、开头城市名后的“市”和一个常见末尾行业词（去行业词后至少保留四字），不截固定字数。例如“东莞市创远机械有限公司”变为“东莞创远”；无法可靠缩减时保留。只影响文件名，NS 查询、供应商匹配及业务记录仍用全称。已归档文件保留原文件名和路径。

**通知**：每次保存新增一个版本（需带当前版本号，不一致返回 409）；群名与启用的默认群一致时记录群 ID。登记发送要求合同已全部归档、已填写群名和发送员工、确认已发送并填写说明，发送时间带时区且介于任务生成与当前之间；同一登记的重试返回原结果。

**身份**：`service:` 身份只读，所有写操作返回 403。

**来源变化**：任务按审核时冻结的应开值跟进；来源关键变化时阻止继续推进合同、通知和新分配，保留待复核占用；财务重新审核后建立后继任务。

## 公开接口与依赖

- `public.py`：`open_lines(connection, purchase_line_ids=None, lock=False)`——有效任务行（应开、已收、单位）及所属任务（供应商、采购公司、币种、报关单）；`lock=True` 时按"任务 → 任务行"顺序加锁，供 matching 审核分配使用。
- 订阅：`ReviewApproved`（生成任务）、`AllocationChanged`（收票进度），均在 `app.py` 中登记。
- 读取：`source.public.SourceDirectory`（供应商、采购公司、子采购单号、行品名、供应商分页）。通过 `review.public.current_bases` 核对当前依据；任务生成仍只经审核事件取得冻结值。
- 外部适配：`SubpoContractSource`（NS 合同）、`integrations/contract_archive.py`、`integrations/wecom.py`。
- 订阅关系在 `app.py` 中登记：`events.subscribe(ReviewApproved, on_review_approved)`。

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

- 六个节点与详情页共用 `task_mapper.steps`（新增稳定 `key`），资料齐全用 `document_mapper.completion_of`，通知文案用 `notification_mapper.status_label`；任务按第一个未完成节点归入分区（`policy/board_policy.py` 负责分区文案与下一步提示）。
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

## 供应商档案分字段搜索（2026-10-28）

`POST /api/task/supplier-groups/profiles/query` 接收 `supplierName`、`groupName`、`owner`，分别搜索供应商名称、已绑定外部群名称、群主姓名或账号。支持部分匹配和批量输入：中英文逗号、分号、换行分隔，最多 50 条，每条最多 120 字符；框内 OR、框间 AND，空项忽略、重复项去重，通配符作为普通字符。绑定状态与群条件一并过滤；无匹配 ID 不能退化为不限制。source 门面按名称和 ID 范围过滤后分页。顶部供应商概况仍为全量，不随搜索变化。

旧 `/api/tasks/supplier-groups/profiles/query` 和 `keyword` 保留一个版本兼容旧前端；正式前端已切换新路径，旧调用方升级后删除该别名。其余群维护接口不变。

供应商档案 `profiles/query.status` 新增 `bound`（任意群绑定，含停用绑定）与 `notify_off`（供应商通知关闭，与群绑定是否启用无关），用于概况卡筛选；与名称、群名、群主条件取交集，先筛选再分页。原 all/enabled/disabled/unbound 保留，概况 counts 不随筛选变化。无需数据库迁移。

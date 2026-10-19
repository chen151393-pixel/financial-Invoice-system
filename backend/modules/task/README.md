# task 模块：开票跟进

架构 v2 第 4c 步新建。财务审核通过后按 供应商 × 采购公司 × 币种 生成开票任务，跟进合同归档、供应商通知与收票进度。表结构见[数据库设计](../../../docs/architecture/database.md)第 4.3、6 节。

4d 补强已接入全局依据、任务后继与差异结束。包括已完成任务在内，依据变化时整体替代并按台账重算；兼容分配承接，口径不兼容保留待复核占用。

## 职责

- 订阅 `ReviewApproved`：在审核事务中生成任务与任务行（应开值从审核行复制），重新审核时替代旧任务。
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

**合同**：事务外下载 → 短事务登记首次获取记录（来源与 SHA-256）→ 事务外写共享盘（按首次获取日期建文件夹，北京时间）→ 短事务标记已归档。再次获取到不同内容时拒绝覆盖；共享盘失败记为 `failed` 并可重试。

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

新增预览/提交/本地历史/回执刷新/候选核实接口；DTO 只接受版本、摘要和记录 ID。记录及候选只读查询不创建群发。所有操作复用认证身份、来源依据保护和账本写锁，外部调用不占事务。

验证入口：`test_deliveries.py`、`test_delivery_recovery.py`、`test_wecom_messaging.py`、`test_deliveries_mysql.py`；真实渠道联调及专用 MySQL 并发未在本次执行。

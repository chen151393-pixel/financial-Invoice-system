# 数据同步与连接模块

## 全账套后台任务与每日计划（2026-10-19）

已实现当前发现范围内全部授权账套/指定账套后台拉票、日期分片、持久任务历史及可配置每日计划。接口、文件职责、并发与未知结果保护、迁移 `0023_sync_background` 和部署步骤见[后台同步说明](../../../docs/lemon-background-sync.md)。后台与单账套入口复用 `LemonInvoiceService` 及原事件保存链路；NS 的分页拉取仍不属于持久后台队列。

## 进项发票列表定向补拉（2026-10-19）

- `POST /api/sync/lemon/invoices/detail-actions`：请求 `{invoiceIds: ["1"]}`，返回逐票 `{invoiceId, allowed, reason}` 和最近同步记录。只读校验绑定、当前账套、来源渠道及执行中请求。
- `POST /api/sync/lemon/invoices/refresh-details`：请求 `{invoiceIds: ["1", "2"], requestId: "UUID"}`。单次 1–100 张且 ID 不重复；仅支持专业版 API 原票。服务端读取日期、业务类型和原来源 ID，用户无需再填写日期。所选票日期跨度最多 366 天，范围内来源列表仍遵循 2000 张上限。
- 响应沿用 `LemonRun`；`GET /api/sync/lemon/runs/{request_id}` 查询原结果。请求编号和选中 ID 持久保存在原同步记录，同编号换范围返回 409。网络结果未知时只查原请求，不自动重发。

`service/lemon_detail_refresh_service.py` 通过 invoice 门面读取来源与版本，复用 `LemonInvoiceService` 的事务外拉取、持久请求、事件保存及匹配流程。只读取所选票的商品明细，不保存同日期范围的其他发票；任一票不存在、原账套不符、上游未返回所选票、拉取期间版本改变或明细校验失败，整批不保存。返回 `detailIssues/detailIssueCount` 解释未补齐原因。

测试：`tests/sync/test_lemon_detail_refresh.py` 验证单张/批量、身份、范围、幂等和失败；`test_lemon_refresh_mysql.py` 在随机隔离 MySQL 库验证同请求和不同请求竞争。没有执行真实 NS 写入。

柠檬云页 `/sync/lemon` 现由应用层装配发票模块的Excel导入组件，支持原文件预览和确认入库。导入使用独立 `/api/invoices/import/*` 契约，见[发票模块](../invoice/README.md)；本模块已提供已有账号授权绑定、账套选择和 API 手动拉票；接口与部署见[接入说明](../../../docs/lemon-invoice-sync-plan.md)。配置、前端操作与接口见[账号绑定说明](../../../docs/lemon-account-binding.md)。

展示服务器连接配置与最近M2M认证结果，支持三类单据只读分页拉取；子采购订单和报关单另支持补齐明细后按页保存到独立 MySQL 的 source 新表（架构 v2 第 4b 步起）。尚未执行定时全量或增量同步，不写回 NS。

## 文件职责

controller/ns_controller.py接收 NS 请求；service/connection_service.py生成连接状态并调用 NS 认证；dto/source_dto.py校验分页；pull_service.py负责读取单据及校验上游响应，通过应用工厂注入的 source 模块 `StorageService.sync_page` 完成保存。没有持久同步队列。

## 公开入口

`GET /api/ns/status；POST /api/ns/connect`。模块通过应用工厂注入依赖，不建立全局客户端或全局数据库连接。

- `GET /api/ns/sync/sources`：三类单据的 allowed/reason；柠檬云提示进入独立同步页操作。
- `POST /api/ns/sync/purchase-orders/pull`：标准采购订单 `purchaseOrder`。
- `POST /api/ns/sync/sub-purchase-orders/pull`：子采购单，使用 `NETSUITE_PL_LOOKUP.purchase.type`。
- `POST /api/ns/sync/customs-declarations/pull`：报关单，使用 `NETSUITE_PL_LOOKUP.customs.type`。

请求为 `{"offset":0,"limit":20}`，offset 为 0～99980，limit 为 1～20，必须是整数。拒绝多余字段；所有记录类型必须在 NETSUITE_RECORD_TYPES 白名单内并具有远端读取权限，不自动扩大权限。

可选 `startDate`、`endDate` 按记录创建日期筛选，格式 `YYYY-MM-DD`，必须同时填写或同时留空，年份 1900～2100，开始日不得晚于结束日。例如 `{"offset":0,"limit":20,"startDate":"2026-09-01","endDate":"2026-09-16"}`。旧请求省略日期时保持不限定日期。

后端向 NS 列表传入 `q`：标准采购订单使用 `createdDate`，两类自定义单据使用 `created`；条件为起始日 `ON_OR_AFTER` 且结束日次日 `BEFORE`，覆盖起止当天。按 NS 查询时区解释日期，不转换为浏览器时区。字段不可由客户端指定。筛选失败直接报错，不降级为无条件拉取。语法依据 [Oracle Record Collection Filtering](https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/section_1545222128.html)；各部署需验证字段可筛选权限及 NS 日期格式。

响应新增 `dateRange: {startDate, endDate, label}`，`label` 为“创建日期”；翻页必须携带相同日期条件。界面显示实际返回范围，修改日期后需重新开始时间段拉取。

2026-10-16：请求支持 `requireDateRange: boolean`（默认 false，兼容旧调用方）。当前页面固定提交 true，后端要求起止日期均填写并沿用格式、顺序和分页上限校验；校验失败前不读取 NS 或保存。前端依次调用相同接口直至 `hasMore=false`，中途停止／失败只结束后续请求，已提交批次不会整体回滚，不自动重试结果未知的保存。各批保存计数不代表整个时间段去重总量；关联补齐可能读取日期范围外的关联单据。旧调用方省略该字段仍可按页不限定日期拉取。

服务器配置 `NETSUITE_SYNC_DATE_FORMAT` 控制发送给 NS 的日期格式，默认 `YYYY-MM-DD`，也支持 `M/D/YYYY`、`D/M/YYYY`。必须与 NS 账户的查询格式一致，修改后重启后端。浏览器请求仍使用 `YYYY-MM-DD`；后端先计算结束日的次日，再按配置转换。非法配置在启动时拒绝，不自动切换格式或去掉筛选重试。

按 [Oracle 分页约束](https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/section_156414087576.html)，offset 必须是 limit 的整数倍，最多 1000 页；下一页按 limit 递增偏移。达到上限且仍有数据时明确报错，不宣称已全部拉取。

响应包含 rows（id、number、record 原始字段）、count、offset、hasMore、nextOffset、pulledAt、message。先读取列表 ID 再逐张读取详情；详情失败、重复 ID、分页异常时整页报错。金额小数返回十进制字符串，不跟随 NS 返回的链接。

## 关键约束

认证成功不等于拥有记录读写权限，状态不能虚构为同步完成。

仅拉取接口返回 REST 单头详情及内嵌资源，不额外联查独立明细。列表会随 NS 数据变化，不是不可变快照。NS 定时同步、增量游标尚未实施；柠檬云后台任务和每日计划见本文开头，原手动拉票使用下方独立接口。

## 按页拉取并保存

`POST /api/ns/sync/{kind}/pull-save` 使用与 `/pull` 相同的分页和日期请求，仅支持 `sub-purchase-orders`、`customs-declarations`。保留旧 `/pull` 的只读行为。前端不上传单据正文或操作者，保存使用后端读取结果及认证身份。

第 4b 步起，保存由 [source 模块](../source/README.md) 完成：在 NS 账户锁内读取本页、补齐明细、关联子采购、PL 名称与关联依据，再在一个短事务内写入 `source_*` 新表（主数据、单头与明细、报关—子采购关联、依据状态、内容摘要、原始数据）。保存规则见 source 模块文档。旧 business 六表保存已在 4e 删除。

存储位置为 `BUSINESS_MYSQL_*` 指定的独立库，需完成新迁移链（`schema_version`）。字段映射沿用 `NETSUITE_PL_LOOKUP.storage_fields`。标准采购订单尚无对应存储映射，保存返回422。

来源配置的 `storageAllowed/storageReason` 反映基础读取权限、新表是否可见和字段映射；原始报关行及 v3 追溯接口不再是基础保存的配置前提。点击保存时后端重新校验；数据库及字段转换失败不能视为成功。全部 NS 读取结束后在短事务内原子更新，重复来源按 NS 身份更新，本次未返回的旧明细置为无效。空页不清空原数据。

成功响应保留分页字段并增加 `storage`：`purchase/customs` 各含 `created/updated/linesCreated/linesUpdated`，另含 `savedAt/message/warnings`；这些计数仅在提交成功后返回。采购保存计数包含关联报关单。下一页需继续携带日期条件。数据库提交或连接结果不确定时返回503，先核实本地数据，不自动重试。同步页暂未增加本地历史浏览页面；已保存的报关单在财务核对页（`/review`）查看。

## 同步对应关系（2026-09-24）

“拉取并保存”和已有 PL 保存入口现在共享同一条关系读取链路：先读取报关单与汇总明细，再按子采购单的 NS 报关引用反查全部子采购及明细（包括当前分页之外的同单子采购），同时读取 Packing、销售→母采购行关系和母采购来源行身份。原始报关子行通过已准备的只读 RESTlet 读取，配置见 [来源接口说明](../../../docs/finance-source-reader.md)。只读 `/pull` 继续作为单头详情预览，不保存关系；使用 `/pull-save` 才完整补齐并入库。

关联依据保存在 `source_customs_purchase_links` 与 `source_raw_records`。同次调用NS v3整单查询，保存明确的报关行→子采购行引用及本次数量金额。读取完成后随报关、子采购及外键同一事务提交，重复拉取替换本次证据；完整反查后解除已移出的旧子采购外键，保留采购本身和其他身份/账套。2026-10-16 起，未配置原始行接口，或同账套、版本 1 响应明确返回原始子列表／字段不可见时，基础单据可保存，追溯标记待补齐并跳过依赖原始行的 v3 查询。原始行可读取但 v3 未配置时也保存待补齐状态。认证、连接、基础读取失败、截断、范围或账套不符，以及其他原始行错误或已调用的 v3 接口失败／旧版仍整页失败；不会将这些错误吞成空成功。

响应 `storage.relations` 包含 `declarations/collected/matched/partial/rawLines/packingLines/purchaseLinks`。`matched` 仅表示来源及逐行关联完整，不是审核通过，也不是人工审核的必需门槛；`partial` 的完整基础单据仍按 review 的子采购、币种及冻结依据规则审核。`collected` 保留原计数兼容，不能单独据此判断审批。财务核对页（review 模块）读取 source 保存结果，状态筛选和分页在后端完成。

固定 SuiteQL 仅接受服务端校验的内部 ID，最多300个ID/次、5000行/类及8MiB/类，不向浏览器开放SQL或任意URL。报关原始行接口每批最多20张。超过上限要求缩小同步范围，不截断保存。

## 验证

在项目根目录运行 `npm.cmd run test:api`、`npm.cmd run lint:api` 和 `npm.cmd run check:architecture`。接口验证使用FakeNS，不操作真实NS。

test_sync_pull.py 覆盖三类映射、身份、参数、金额精度、空结果和失败。真实 NS 读取权限与数据仍需联调。

新链路保存与 `/pull-save` 接口由 `test_source_storage.py`、`test_sync_pull.py` 覆盖；原始追溯缺失仍可保存、审核并生成任务，以及错误仍拒绝保存，由 `test_source_optional_trace.py`、`test_source_optional_sync.py` 覆盖；来源变更与确认竞争见 `test_matching_mysql.py`。旧 `test_sync_storage.py` 随 business 实现退役，历史验收记录不代表当前正式环境已部署。

## 柠檬云账号绑定

`controller/lemon_binding_controller.py` 提供状态、开始授权、固定回调、确认与核实接口；`service/lemon_binding_service.py` 处理身份和一次性授权上下文；`dao/lemon_binding_dao.py` 条件更新 `entity/lemon_binding.py` 定义的绑定表。外部调用通过 `integrations/lemon/existing_account.py`，不放在数据库事务内。配置与手机号校验在 policy/dto 中。迁移 `0016_sync_lemon_bindings` 不包含密码或令牌字段。

入口为 `/api/sync/lemon/binding`，固定回调保留用户已指定的 `/api/lemon/oauth/callback`。只有管理员可绑定，回调需同一浏览器临时 Cookie，真正提交还需原身份及账号密码。网络结果未知或进程中断后禁止直接再次绑定，先查询官方状态；单 API worker 约束与部署步骤见上方说明。测试见 `test_lemon_binding.py`、`test_lemon_binding_database.py`。


## 批内读取优化与阶段进度（2026-10-16）

2026-10-19 追加：已支持映射的报关/子采购明细改为按已发现 ID 分批读取必需字段（最多 300 ID/批），保留全部行级关联依据与原失败规则；部分保存模式在一页内复用 PL 名称，下一页重新读取。两种保存模式都使用同一读取实现。详见 [source 明细批量读取](../source/README.md#同步明细批量读取2026-10-19)。下述原详情 GET 优化与并发配置继续适用于单头和未支持的自定义映射；明细批量查询不受详情 GET 并发数控制。

- 关联明细按同一记录类型、父引用字段合并查询，每组最多 20 个父 ID；详情在单批缓存中按类型＋ID 复用。报关入口可合并报关明细、子采购发现、子采购明细三类列表。子采购入口保留逐报关的成员复核，避免缓存单头掩盖读取期间的改挂。
- `NETSUITE_SYNC_READ_WORKERS` 默认 `2`，允许 `1`～`4`；仅控制每组详情 GET 的并发数，账户配额紧张可设为 `1` 后重启后端。关联脚本仍按原规则读取。合并筛选不支持、限流、截断、重复 ID、范围不符均明确失败，不自动重试、拆散重发或省略数据。
- 缓存只在本批读取期间有效，下一批／重新同步重新读取 NS 最新值。已取消本地累计 300 条详情及单类关联记录上限；详情任务按固定并发逐步提交，保留完整关联补齐、母采购币种、可选追溯提示、账户锁和整批短事务；没有新增数据库表或改变审核、任务生成规则。
- `POST /api/sync/ns/progress`：认证后申请本批临时进度，返回 `{progressId}`。将其作为可选字段传给原 `/api/ns/sync/{kind}/pull-save`；省略时保留旧调用行为。同一编号只能发起一次保存，重复使用返回 409。
- `GET /api/sync/ns/progress/{progressId}`：仅原认证身份可查询，返回 `state`（pending/running/completed/failed）、中文 `label`、阶段 `completed/total`（未知时为 null）、`elapsedSeconds`。仅包含进度，不包含单据、密钥或保存结果；查询只读内存，不触发 NS 请求。
- 申请进度失败时尚未发起保存，前端以旧协议发起一次保存并提示进度不可用；已发起的保存失败绝不重试。前端每秒串行查询一次进度，显示真实阶段与当前阶段计数。进度失败不重发保存；只有保存响应成功才推进下一批。停止仍等待当前批次结束；进度显示完成但保存响应丢失时，必须核实本地结果，不能视作已确认成功。
- 进度在当前后端进程内存保存，未开始／结束后 10 分钟过期，总量上限 256，容量不足时优先移除已结束的旧进度；运行中的进度不清除。适用于当前单进程部署，重启或多 worker 不共享进度。它不是持久任务队列，不提供断点续跑。

验证：`test_sync_optimization.py` 用 20 张报关、20 张子采购、各 40 条明细的合成数据检查列表请求从原先 60 次降至 3 次、详情去重、母采购币种、重复保存、越界与失败不部分入库。`test_sync_progress.py` 检查身份隔离、单次使用、运行中进度及结果未知不重试。新增 `test_sync_large_batches.py` 验证超过 300 条报关／子采购明细完整入库、重复同步不新增相同记录、后续详情失败不部分保存；`test_sync_optimization.py` 同时验证 401 条关联 ID 分页和 601 条详情缓存及进度。真实 NS 耗时和账户并发额度需在部署环境确认。

## 柠檬云手动进项拉取（2026-10-16）

`lemon_account_service.py` 维护授权账套查询和选择，`lemon_invoice_service.py` 编排持久请求与事务外读取，`dao/lemon_run_dao.py` 管理本模块的 `sync_lemon_runs`。迁移 `0018_sync_lemon_runs` 新增同步记录与已选账套。`integrations/lemon/invoice_client.py` 负责正式用户 Token、Bearer/asid 及 page/rows 查询参数。

2026-10-19 真实联调修正：旧 `GetAllPermissions` 仅查到默认账套；即使携带真实服务 ID，旧 `GetAccountSets` 仍返回默认账套，不能用于专业版发现。`authorized_accounts()` 通过 `integrations/lemon/professional_accounts.py` 建立临时官方会话、取得财务服务入口的服务 ID，并调用专业版 `TopInfoV2`。已在真实账号验证返回 6 个专业版账套，编号与截图一致；无用户 Token/Cookie 落盘，不硬编码服务 ID。仅上游明确确认没有专业版服务才查询默认账套，专业版空列表或失败不回退。前端无需输入服务 ID，不改数据库和接口契约。

专业版发票已接入 `integrations/lemon/professional_invoices.py` 的 `PurchasePagingList` 分页读取。拉票使用所选账套的加密上下文，排除严格识别的合计行，并核对总数、重复编号和页数；成功完整读取后发布原有事件事务保存，默认版继续使用原接口。真实账号读取 78 张，隔离 SQLite 保存固定资产票 15 张，重复跨页读取仍为 78 张且无重复保存。协议来源、当前单服务范围和验证边界见[接入说明](../../../docs/lemon-invoice-sync-plan.md#专业版服务自动发现2026-10-19)。隔离测试：`tests/sync/test_lemon_account_services.py`、`test_lemon_professional_protocol.py`、`test_lemon_professional_save.py`。

新入口为 `/api/sync/lemon/invoices/configuration`、`/accounts/query`、`/account`、`/invoices/pull-save`、`/runs/{requestId}`（后四项同属 `/api/sync/lemon` 前缀）。请求、响应、限制见[完整协议](../../../docs/lemon-invoice-sync-plan.md)。API 按管理员身份隔离；日期必填且最多 366 天，所有分页完成才整批入库；同请求返回原结果，运行中拒绝切账套及新请求，重启不重置状态。

跨模块保存通过 `public.py` 的 `LemonInvoicesFetched` 事件，invoice 通过 `LemonInvoicesStored` 回执，同事务更新票据与已完成统计。事件只在 `app.py` 订阅；不通过 DAO 写其他模块。测试位于 `backend/tests/sync/test_lemon_{protocol,invoices,mysql}.py`；真实上游未联调。


## 部分成功保存协议（2026-10-16）

`/api/ns/sync/{kind}/pull-save` 新增可选 `partialSave: boolean`，当前同步页面固定发送 `true`。省略或 false 保留旧整页原子行为，兼容尚未更新的客户端；待旧客户端退出后再统一切换默认值。只读 `/pull` 不启用部分保存。

新模式将本页按完整报关关联组分别提交：同组内任一基础字段、明细或关系校验失败，该组不更新，其余组继续；单头读取失败也列出内部编号。整个过程中保留原锁顺序和账户互斥，各组外部读取在事务外。成功组写入后计入 `storage` 汇总；`storage.savedAt` 无成功组时为 null。不得把 HTTP 200 或进度 completed 当作全部单据保存成功。

响应新增 `batch`：`status` 为 completed / partial / interrupted；`canContinue` 控制是否可拉下一批；`counts` 按本批入口单据统计 saved / failed / unknown / not_processed；`items` 含 id、number、同名 status 和中文 reason。`count` 仍为本页列表单据数，`rows` 仅含成功读到的单头，失败的单头在 items 中。已补齐并提交的同组入口按实际提交结果标记，不重复计入组保存次数。

已知失败不阻止翻页，但时间段完成显示“存在失败单据”，可逐批查看清单。数据库提交未知或不可继续的错误返回 interrupted，先保留已返回的本批结果，再停止后续分页，不自动重发。保存响应丢失时仍须核实本地记录，单靠进度不能推断哪些组已写入。进度中的“处理结束”仅指请求结束，以逐单保存结果为准。

旧文档中的“整页失败／整页事务”适用于 `partialSave=false`；新模式对应完整关联组，不把失败组的部分明细保存为完整单据。本次不新增表、不调整数值精度、不写 NS，也不提供持久断点续跑。

API 拉票支持 `businessTypes` 文本多选，默认“采购固定资产、采购支出”；默认值及候选项由 invoice 门面提供。选中集合在创建请求时写入 `sync_lemon_runs.result.businessTypes`，失败仍保留，完成统计包含该快照，不新增数据库字段。响应把条件单独返回，只有 completed 返回统计。同一请求编号不得更改集合；旧记录按原固定资产范围解释。详见接入说明和 `tests/sync/test_lemon_business_types.py`。

## 专业版商品明细补全（2026-10-19）

分页完成后，sync 通过 invoice 公开规则 `lemon_detail_ids` 取得所选类型的发票 ID，在事务外调用 `professional_invoice_details.py` 读取详情。重新建立独立只读会话并复核所选账套上下文，单票最多一万行，明细阶段总读取限时 120 秒，超时或任一详情读取失败整批不保存。默认版继续保留票头 pending；不猜测未验证接口。

入库复用原 LemonInvoicesFetched → invoice 版本/匹配事件 → LemonInvoicesStored 事务。响应新增 `result.completeDetails`；`pendingDetails` 包含待补齐与身份待核实，统计来自保存后的状态。恢复规则不变，同一请求只查询原结果；用户重新补全须创建新请求，不能复用旧请求编号。详情失败阶段日志不输出票据、Token 或加密上下文。

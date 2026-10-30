# 数据同步页面

## NS 同步执行记录（2026-10-30）

总览 `/sync` 在近 14 天同步情况下展示“NS 同步执行记录”和“柠檬云同步执行记录”；NS 页复用相同的 `NsBatchRecords`。NS 列表包含当前登录身份的手动分页保存和当前账套的定时批次，支持后端状态筛选、分页、状态数量、每 5 秒刷新和执行详情入口。显示触发时间、方式、单据类型、创建日期范围、读取、新增/更新、失败数量与结果说明。手动记录以 `?recordType=manual` 进入已有详情路由，展示失败单号、原因及真实页序号；不会错误提示定时计划已暂停或将查询当作重试。未限定日期、空记录、初始加载、错误重试和保留旧数据时的提示均有对应状态。测试：`frontend/tests/ns-plan.test.mjs`。

## NS 定时同步计划（2026-10-29）

`/sync/ns` 与柠檬云页同一结构（`pages/NsSyncPanel.tsx`，2026-10-30）：状态条 `NsSyncStatus` →“手动补拉 / 定时计划”页签（两页共用 `components/SyncTabs.tsx`；手动补拉为 `NsManualPull.tsx`，切换页签只隐藏不卸载，不中断拉取）→ 计划执行记录。计划表单左栏“何时执行”（与柠檬云共用的 `components/SyncScheduleFields.tsx`，已保存状态在状态条显示），右栏同步范围（`components/NsPlanForm.tsx`，保存规则收在可展开区），自动暂停原因显示在保存按钮旁；可否启用、版本冲突和输入校验都以后端 `allowed/reason` 与保存响应为准，后端自动暂停时显示 `pausedReason`。`components/NsPlanBatches.tsx` 每 5 秒刷新后端分页的批次记录；`/sync/ns/batches/:requestId`（`pages/NsPlanBatchPage.tsx`，路由由应用层 `SyncNsBatchWorkspacePage.tsx` 装配）展示每页状态、执行中阶段进度和失败单据原因，执行中每 3 秒刷新。结果待核实只提示核对，不提供重试按钮。请求契约在 `api/ns-plan-api.ts`、类型与状态色映射在 `types/ns-plan.ts`、请求状态在 `hooks/useNsPlan*.ts`。新增区块使用统一组件库的 `Badge`、`Alert`、`DataTable`、`EmptyState`、`ErrorState`、`Skeleton`、`Pagination`，表单沿用本模块 `sync-background.css`。接口与执行规则见[后端同步模块](../../../../backend/modules/sync/README.md#ns-定时同步计划2026-10-29)。测试：`frontend/tests/ns-plan.test.mjs`。

同步结果支持展开 `detailIssues` 查看逐票未补齐原因（最多 100 张）；空商品行和缺少匹配字段分别说明。历史结果没有诊断字段时不编造原因。进项发票列表新增单张与当前页批量补拉，继续复用本模块原拉取及持久结果查询逻辑。

`/sync` 提供真实后台任务历史、状态筛选、分页及计划状态；`/sync/ns` 独立提供 NS 拉取；`/sync/lemon` 提供全部/指定授权账套后台拉票和每日计划，保留账号绑定、单账套手动拉票与 Excel 导入。专业版商品明细已接入，默认版明细与附件尚未接入。

`SyncOverview.tsx` 展示平台入口卡片（`SyncSourceCards`，NS 与柠檬云均显示计划启用状态和下次执行时间）并读取持久批次；`pages/LemonBackgroundPanel.tsx` 装配后台拉取/计划表单，`SyncBatchDetailPage.tsx` 展示 `/sync/batches/:requestId` 的账套及日期分片结果。类型/API/hooks/业务组件分目录，样式在 `components/sync-background.css`（面板、表单、表格）与 `components/sync-layout.css`（平台卡片、状态条、页签、状态标签）；批次状态标签统一用 `SyncPhaseTag`。柠檬云页面依次为同步状态条（`LemonSyncStatus`）、“手动补拉 / 定时计划”页签（计划表单 `SyncPlanForm` 左栏执行时间与业务类型、右栏账套范围；`SyncAccountScope` 查询后按后端返回列出各账套“专业版／免费版”及可拉取内容）、最近执行（`LemonRecentBatches`，取执行记录第一页前三条）和“更多操作”（账号授权、单账套即时拉取、Excel 导入，默认收起）；加载、失败、空记录和执行状态均来自真实接口。任务详情可刷新恢复，失败重试服从后端 allowed/reason。覆盖范围与部署见[后台同步说明](../../../../docs/lemon-background-sync.md)。

SyncPage.tsx 管理 UI 和请求状态，api.ts 提供请求契约，sync.css 限定模块样式。SyncWorkspacePage 装配公共 AppFrame。复用 identity 本机会话和 shared HTTP 客户端。

公共 HTTP 客户端对空响应、非 JSON 错误页和网络中断显示中文提示；有效的后端错误说明继续展示，不回显代理原始正文。错误不触发自动重试，可通过“重新加载配置”手动重试。`npm.cmd run test:web` 覆盖响应解析与网络失败，已纳入 `npm.cmd test`。

NS 日期拉取：填写开始与结束日期，点击“仅拉取查看”或“拉取并保存”，页面按后端 `nextCursor` 自动串行拉取全部范围，不限制总张数或累计批数。每次处理 20 张仅为内部请求粒度；超大集合由后端自动拆分 ID 范围，页面不自行计算范围、不要求用户缩小日期。后续游标缺失或未推进时保留当前批次并停止，不退回旧偏移分页。仅拉取不入库；保存复用 source 保存服务，按批提交，标准采购订单仍因缺少独立存储映射禁用保存。进度显示已完成批数；可翻看各批响应，保存计数只代表当前批次，不跨批汇总或冒充去重总量。

拉取并保存同时按NS报关引用补齐对应子采购，并保存可读取的原始报关行、装箱明细及采购行关联依据。页面展示后端 `storage.relations` 统计和 `warnings`：已读取、待补齐及来源行数；依据读取不代表匹配完成或审核通过。原始报关行接口未部署时明确显示待补齐，不用“完整同步”掩盖缺失。

页面保留各类型本次已完成批次的展示结果，刷新清除展示；保存成功的 MySQL 数据不会随刷新丢失。保存连接中断时提示先核实本地数据，不自动重试。当前没有本地历史浏览页面；已保存的报关单在财务核对页（`/review`）查看。柠檬云文件导入由应用层装配[发票组件](../invoice/README.md)，先预览再确认，结果来自真实数据库；不把文件导入称为API同步成功。

NS 子页面仅展示 NS 内容，返回数据同步中心经页头面包屑。使用原生单选控件选择单据类型，默认报关单；每次只显示当前类型的拉取面板。切换时保留各类型的请求及结果状态，不自动拉取，不混入其他平台入口。

NS 页面采用左侧单据选择、右侧结果工作区，窄屏改为上下布局。结果区集中展示拉取操作、只读标识、加载反馈与空状态；不可拉取时展示后端原因，失败后保留已有结果。保存规则与结果保留范围收在“保存规则”展开区域。

创建日期范围包含起止当天，按 NS 查询时区筛选；当前页面日期必填，校验由后端执行。“清空日期”只修改条件，不自动请求。运行中禁用条件和类型切换。“停止后续拉取”等待当前响应后停止，不中断保存请求；失败不自动重试，已完成批次与已提交数据保留。离开页面不继续发起新批次；正在处理的批次在后台继续，返回页面按请求编号恢复查看结果。只有收到 hasMore=false 才显示整个时间段完成。查询期间 NS 数据仍可能变化，不承诺不可变快照。

接口及配置见 [后端同步模块](../../../../backend/modules/sync/README.md)。验证使用 build、lint、typecheck 和浏览器页面检查；后端模拟测试覆盖成功及空结果，真实 NS 联调单独验收。

柠檬云页由应用层的 `SessionProvider` 共享会话，`RequireSession` 在未登录时跳转至 `/login`，登录后显示 `LemonBindingPanel`、`LemonInvoicePanel` 与发票导入组件。绑定面板仅展示后端 allowed/reason；输入手机号后跳转官方授权页，返回后核对手机号并提交账号密码确认。`lemon-api.ts` 维护请求契约；失败先读取实际状态，不自动重复提交。刷新状态、核实已有绑定和配置缺失提示均使用真实后端结果。操作说明见[账号绑定](../../../../docs/lemon-account-binding.md)。

实现：`PullPanel.tsx` 收集条件并展示状态，`useRangePull.ts` 管理请求与批次，`range-pull.ts` 串行调用，`PullResults.tsx` 展示单批结果。`tests/sync-range.test.mjs` 覆盖跨批、失败、停止、空结果与日期保持。

柠檬云绑定工作区按“当前状态与操作 / 官方授权步骤”分栏展示，窄屏按阅读顺序上下排列。配置不满足后端条件时只显示原因与管理员配置说明，不展示无法提交的手机号表单；已有绑定可核实，结果未知不提供重新提交入口。底部说明已支持后台及定时 API 拉票，默认版商品明细待接入，并保留 Excel 入口。`useLemonBinding.ts` 管理请求与刷新时的过期响应，`LemonBindingView.tsx` 只展示状态、收集输入；密码在提交及刷新时清空。

保存（2026-10-19 起）：每批生成 UUID 请求编号，`startRun` 提交到后台批次接口后立即返回，`run-wait.ts` 每秒串行按原编号查询，直到后端返回结束状态；提交连接中断或代理超时只继续查询、不重新提交，后端明确拒绝（4xx）才直接显示原因，连续 3 次查不到才判定本批未发起。`PullProgress.tsx` 展示当前阶段、阶段计数、本批耗时与请求编号；查询暂不可用单独提示。completed/partial/interrupted 才作为批次结果，failed 与 unknown（待核实）显示后端原因并停止后续批次。未结束批次的编号存于本标签页 `sessionStorage`，刷新后自动恢复查看该批结果（不继续后续批次）。旧 `progress-poll.ts` 已删除；后端说明见[同步模块](../../../../backend/modules/sync/README.md#后台保存批次与耗时日志2026-10-19)。

## API 手动拉票（2026-10-16）

`LemonInvoicePanel.tsx` 装配，`LemonInvoiceView.tsx` 展示授权账套、日期、真实统计和状态，`useLemonInvoices.ts` 管理单次请求与刷新，`lemon-invoice-api.ts` 维护接口类型。查询账套 POST 发送 JSON `{}`；选择/拉取均服从后端 allowed/reason，所有日期和业务校验由后端执行。

拉取使用 UUID 请求编号；响应丢失后只读状态，不自动重发。最近结果与账套保存在后端，刷新可恢复；日期输入只属于当前页面。加载、无账套、失败、执行中/待核实和完成均有真实反馈。按后端显示明细完整、待补齐或待核实，提供审核匹配建议入口，不把入库表述成匹配完成。局部样式在 `lemon-invoices.css`，窄屏按顺序堆叠，不改变其他同步面板。测试见 `frontend/tests/lemon-invoices.test.mjs`。

## 逐单保存结果（2026-10-16）

“拉取并保存”固定提交 `partialSave: true`。`PartialSaveResults` 展示后端返回的入口单据状态、失败原因及计数；不在前端判断可保存条件。部分失败的页面继续拉下一批，整个时间段结束显示“存在失败单据”；`batch.canContinue=false` 时先保留本批清单再停止。结果未知和连接中断均不自动重试。

保存时间只有后端确认至少一组提交时才显示。每组是同一报关单及关联子采购，组内仍全部成功后提交，未保存组保留原本地数据。后端更新并重启后再使用新页面；旧客户端省略新参数仍走原整页保存协议。`sync-range.test.mjs` 验证部分失败继续、未知结果停止；`sync-progress.test.mjs` 验证新参数和结果展示。

# 系统架构设计 v2

状态：**已确认（2026-10-09），按第 7 节分步实施中**。依据 `develop` 分支 `3537372`（已统一运行时数据库、新增供应商企微群配置）编写。各步骤完成后在第 7 节标注。

**2026-10-15 修订**：以 `test` 的 `e7422b7` 为实现基线。第 4d 补强 A—D 和 4e 代码切换已实现：币种证据、全局开票依据、任务后继、数量换算、发票版本及冲正闭环。结构与验收契约见[数据库设计第 10 节](database.md)；open2、定时同步和业务库部署仍待后续实施。

配套规则：

- [后端规则](backend-rules.md)
- [前端规则](frontend-rules.md)
- [数据库设计](database.md)：基线 24 张表及新增的两张版本表、比对规则、状态规则、建表与验收

## 0. 已确认的决定

| 问题 | 决定 |
| --- | --- |
| 应开票口径 | 财务审核**不调整**。报关单通过自动关联找到子采购单，**按子采购单开票**；一张发票可以对应多张子采购单，一张子采购单也可以由多张发票开完 |
| 登录、角色 | 2026-10-16 接入单管理员账号密码登录，所有浏览器访问统一认证；多账号与角色暂不设计 |
| 前端路由 | 引入 `react-router` |
| NS 回写 `writeback` | 整体移到单独分支 `archive/writeback`，主线删除 |
| 模块设计 | 参照 Java 微服务分层：模块对外只暴露门面接口和事件，模块内部按层分目录，一个文件只管一个业务对象；改一个模块不影响其他模块 |
| 新增规则 | 写在所属模块自己的代码中，不放进公共目录、入口文件或前端 |
| 公共能力 | 优先复用现有代码（清单见[后端规则](backend-rules.md)第 3 节、[前端规则](frontend-rules.md)第 3 节），不另建一套 |
| 同一子采购单出现在多张报关单 | 同一子采购行只有一版当前开票依据、一条有效任务行；相同依据复用，依据变化后生成后继版本，不能因为历史任务已完成而跳过增量 |
| 采购币种 | 有母单时经 `custrecord_swc_subpo_mainpo` 读取同一 NS 账套母采购单的 `currency`；无母单或确实缺币种时待核实；独立结算与跨币种换算不在本期 |
| 发票币种 | 本期柠檬云 `GetInvoice` 进项票及现有柠檬云 Excel 通道限定为人民币；适配时明确赋值 `CNY`，保留来源规则版本，不要求逐票人工补币种 |
| 超开 | **允许确认并标记超开**：发票累计数量或金额超过子采购行应开值时可以人工通过，须填写说明，任务行带超开标记 |
| 发票单位 | 同单位直接分配；不同单位须有本商品、本规格的有效换算依据，分别保存发票数量和采购数量；仅写不一致说明不能替代换算 |
| 比对与完成 | 建议全部人工确认；有效收票达到数量和金额条件，或明确按差异结束，才结束任务行；超开单独标记；取消、作废或红冲后按事实重新计算 |
| 数据库 | 复用 v2 新表并追加版本迁移；旧模块测试数据不迁移，已进入 v2 的业务记录须保留并准确回填；合同 PDF 只存共享盘路径 |
| 供应商比对 | 子采购单上没有纳税人识别号，先按规范化名称比对 |
| 第 4 步实施方式 | **新旧并行，最后统一切换**（2026-10-10）：source、review、task 建在新目录、用新表和新接口前缀，页面逐个切换；invoice、matching 最后原地重建；旧模块在 4e 统一删除。过渡期新旧两套代码短暂并存，不写新旧表之间的适配代码 |

## 1. 目标业务主线（定时与 open2 待接入）

```text
[定时] NS 报关单 + 子采购（自动关联） ──→ source
                                          │
                     财务：review 核对并审核通过（不调整金额）
                                          │  发布事件「审核通过」
                                          ▼
              task 生成开票任务：每条子采购行 = 一条任务行（应开数量、应开金额）
                   采购：备合同 → 按供应商企微群通知开票 → 等待开票
                                          │
[定时] 柠檬云进项发票 ──→ invoice
                                          │
              matching：发票行 ↔ 子采购行 按数量分配（多单一票、一单多票）
                        人工确认后发布事件「分配变化」
                                          ▼
              task 更新任务行已收数量和金额，任务状态自动变化 → 已收齐 → 完成
```

## 2. 仓库目录

```text
项目根目录/
├── backend/                  Python 后端（依赖、迁移、测试都在此目录内）
├── frontend/                 React 前端（独立 package.json）
├── netsuite/                 上传到 NS 的 RESTlet 脚本及其 Node 测试
├── scripts/dev.mjs           本地同时启动前后端
├── package.json              命令入口（不含依赖）
├── docs/                     当前有效文档；历史方案放 docs/history/
└── Dockerfile、compose.yaml、.env.example、README.md、AGENTS.md
```

根目录不再有前端配置文件（`vite.config.ts`、`tsconfig.json`、`eslint.config.mjs` 等）、前端依赖和原型目录（`app/`、`worker/`）。根目录 `package.json` 只作命令入口，不含任何依赖；前端命令转到 `frontend/` 执行。

## 3. 模块划分

前后端使用同一套模块名，审查时按模块对照：

| 模块 | 职责 | 现在的代码位置 |
| --- | --- | --- |
| `identity` | 单管理员账号密码登录与会话 | identity |
| `source` | NS 报关单、子采购、母采购来源和自动关联；采购报关联查；供应商目录 | `source` |
| `sync` | 定时与手动同步 NS、柠檬云；同步记录 | sync |
| `review` | 财务核对、审核快照、审核历史 | `review` |
| `task` | 开票任务、任务行、合同归档、供应商企微群、通知 | `task` |
| `invoice` | 发票导入（Excel、柠檬云）、查询 | invoice |
| `matching` | 发票行与子采购行的数量分配、确认 | matching |

删除：`writeback`（移到分支）、`audit`（审核审计归 `review`，回写审计随 `writeback` 移走）。不预建 `dashboard`、`exception`。

### 3.1 模块之间如何连接

参照微服务：模块之间只有两种连接方式。

1. **调用门面**：导入对方的 `public.py`，相当于对方的对外 API。只用于**读取**对方数据。
2. **发布/订阅事件**：一个模块完成操作后发布事件，其他模块订阅并在**同一个数据库事务**里更新自己的数据。发布方不知道谁在订阅。

```text
读取依赖（箭头指向被调用方）：
  sync     → source（invoice 接入待第 5 步）
  review   → source
  task     → source、review（仅核对依据）
  matching → source、review、invoice、task

事件：
  review   发布「审核通过 ReviewApproved」        → task 订阅：生成任务和任务行
  matching 发布「分配变化 AllocationChanged」     → task 订阅：更新已收数量金额和任务状态
  source   发布「来源变化 SourceChanged」         → review 订阅：标记需重新审核
  invoice  发布「发票变化 InvoiceChanged」        → matching 订阅：过期建议失效、已确认分配复核
  review   发布「依据失效 PurchaseBasisInvalidated」→ matching 订阅并发布分配变化：限制新分配、通知 task 待复核
```

- 禁止循环读取依赖。`task` 不读取 `matching`，收票进度只通过事件更新。
- 事件契约（数据类）定义在发布方的 `public.py` 中；订阅关系只在 `app.py` 中登记。
- 事件在发布方的事务中同步执行；任何订阅方失败，整个事务回滚。订阅方不能调用外部系统。
- 已接入 `InvoiceChanging` 的写前锁定和全部失效/承接事件。`ReviewApproved` 先生成任务后由 matching 重算，订阅顺序固定在 `create_events()`；契约和锁规范见数据库设计第 10.7 节。

## 4. 数据模型

完整表结构见[数据库设计](database.md)。要点：

- **开票单元是子采购行**。审核通过时把子采购行的采购口径数量、单位、含税金额冻结为审核行，任务行从审核行复制应开值。
- **依据版本唯一**：已新增 `review_purchase_bases`，统一同一子采购行跨报关单的有效审核依据；审核行保留各次报关审核与该依据版本的引用。
- **只保留一条有效任务行**：相同依据复用；应开值变化时，旧任务版本只读保留，新版本按可兼容的有效分配重算，不能直接复制旧进度缓存。
- **分配双向绑定版本**：分配保留子采购行身份，同时绑定开票依据版本和不可变发票版本；发票额度占用与有效收票分别判断，待复核分配不能被再次使用。
- **数据按组织共享**，只按 NS 账套区分；时间、主键、金额类型全库统一。

任务状态由任务行汇总得出，不提供手动修改：

```text
documents_pending → notify_pending → awaiting_invoice → partially_received → completed
completed / partially_received → 按剩余有效收票回退到对应节点
依据变化：包括 completed 在内的旧任务 → superseded；后继任务重新计算
```

资料归档、通知登记与收票进度分别按事实展示。已完成不代表合同或通知已执行；同一依据下的撤销走原任务回退，不创建重复应开量。

## 5. 数据库

- 一个数据库（业务 MySQL）、一个引擎、一条迁移链。新迁移链从 `0001_baseline` 开始，一次创建[数据库设计](database.md)第 4 节的 24 张表，版本表 `schema_version`。
- 初次 v2 切换不迁移旧模块测试数据，旧表由管理员按既有流程处理；本次补强保留已进入 v2 新表的审核、发票和分配，准确回填版本或标记待复核，不能清空台账后重建。
- 第 3 步已完成：新迁移链 `backend/migrations`；旧迁移链当时移到 `backend/legacy_migrations/`（已在 4e 删除）；`core/business_database.py` 并入 `core/database.py`；旧应用库数据导入工具（`core/application_database.py` 的复制部分与 `import-application` 命令）已删除。
- 第 4e 步已删除：旧迁移链与旧表定义、旧 bootstrap、`backend/database.py`、`DATABASE_URL` 变量和 `create_app` 过渡参数。应用代码和迁移不自动删除旧数据库表；2026-10-15 经管理员确认后，已备份并手工清理本机库的 21 张旧业务及旧版本表，范围与保留项见[数据库设计第 9.1 节](database.md#91-4e-退役表核对清单)。其他环境未在本次清理或验证。连接配置保留 `BUSINESS_DATABASE_URL` / `BUSINESS_MYSQL_*`。
- 回写的 `ns_previews`、`ns_target_locks`、`ns_audit` 不进入新结构；旧表留在旧库中，代码不再引用。

### 5.1 表归属

| 模块 | 表 |
| --- | --- |
| source | `source_suppliers`、`source_companies`、`source_raw_records`、`source_parent_orders`、`source_parent_order_lines`、`source_purchase_orders`、`source_purchase_order_lines`、`source_customs_declarations`、`source_customs_lines`、`source_customs_purchase_links` |
| review | `review_records`、`review_lines`、`review_purchase_bases` |
| task | `task_supplier_groups`、`task_tasks`、`task_lines`、`task_documents`、`task_notifications`、`task_events` |
| invoice | `invoice_raw_records`、`invoice_headers`、`invoice_items`、`invoice_versions` |
| matching | `matching_allocations` |
| sync | `sync_runs`、`sync_cursors`、`sync_lemon_bindings`、`sync_lemon_runs` |

每张表只属于一个模块，只有该模块的 DAO 可以读写；跨模块只保存对方 ID，不建外键。

## 6. 删除清单

依据：正式前端的全部接口调用、`app.py` 装配、构建和部署配置。实施时每一项再检查测试、文档、脚本的引用，并在提交说明中列出依据。

### 6.1 后端

| 删除项 | 依据 |
| --- | --- |
| `writeback` 模块、`/api/ns/preview`、`/preview-text`、`/execute`、`/jobs*`，`backend/workflow.py` | 已决定移到 `archive/writeback` 分支 |
| `/api/ns/pl-comparison` 及 `pl_comparison_*.py` | 前端无调用 |
| `/api/ns/pl-lookup/config`、`/api/ns/pl-lookup` 及仅被其使用的文件 | 前端无调用 |
| `/api/ns/records/*`、`/api/ns/query` | NS 通用调试查询，前端无调用 |
| `/api/ns/related-purchase` 及 `related_purchase_*.py` | 前端只定义未调用；同步保存若依赖其中规则，先移入 source |
| `/api/business/pl-sync`、`/pl-storage/config`、`/pl-documents/query`、`/database-status` | 前端无调用；保存由 `/api/ns/sync/{kind}/pull-save` 承担；数据库状态改用已有命令 `db:business:check` |
| `/api/reconciliation/query`（实时 NS 审核）及 `task_policy.split_scope` 中处理 NS 展示数据的分支 | 前端函数无调用方；审核只基于已同步数据。**移到第 4 步**：审批幂等、审计回滚、过期预览、MySQL 并发等核心测试走这条路径，须随 review 模块重组改为本地路径后再删 |
| `backend/config.py`、`database.py`、`netsuite.py`、`auth.py` | 旧导入兼容入口，调用方改为新路径后删除。`database.py` 是旧迁移链的元数据登记入口，**随第 3 步新迁移链删除** |
| `audit` 模块 | 审核审计并入 review；回写审计随 writeback 移走。**移到第 4 步**；第 1 步先把回写两张表的定义移入 `audit/entity.py`，保证历史数据导入仍原样复制 |
| `StorageService.sync(pl)`、`query(pl, page)` | 接口已删，方法暂留：承载 `_save` 去重、关联、回滚规则的主要测试。**第 4 步**把测试改为经 `sync_page` 后删除 |

### 6.2 前端与原型

| 删除项 | 依据 |
| --- | --- |
| `app/`、`worker/`、`.openai/`、根 `vite.config.ts`、`next.config.ts`、`next-env.d.ts`、根 `tsconfig.json`、`postcss.config.mjs`、`scripts/vinext.mjs` | Vinext / Cloudflare 原型，不参与正式部署 |
| `frontend/src/app/DemoPage.tsx`、`/demo` 路由；导航中"发票工作台、异常处理、系统对账、回写 NetSuite" | 指向演示数据 |
| `frontend/src/app/FinanceWorkbenchExamplePage.tsx`、`frontend/src/modules/reconciliation/example/` | 示例页 |
| `frontend/src/modules/business/`、`frontend/src/modules/writeback/` | 只有 README |
| 无调用的前端接口函数（`queryFinanceComparison`、`relatedPurchase` 等） | 无调用方 |
| `tests/rendered-html.test.mjs` 及只测试演示数据的 Node 测试 | 随原型删除 |
| 依赖 `vinext`、`wrangler`、`@cloudflare/vite-plugin`、`@openai/sites-vite-plugin`、`@vitejs/plugin-rsc`、`react-server-dom-webpack`、`@next/eslint-plugin-next`、`tailwindcss`、`@tailwindcss/postcss` | 只被原型使用 |

### 6.3 文档

阶段性方案（`architecture-plan.md`、`reference-project-review.md`、`pl-join-design-review.md`、`ns-suitelet-realtime-plan.md`、`document-storage-execution-plan.md` 等）移入 `docs/history/`；`system-chain.md`、`project-structure.md` 在实施完成后由本目录文档替代。

## 7. 实施顺序

每个可独立验收的步骤一个 PR。第 1、2 步以清理和结构调整为主；第 3、4 步包含新表、审核和分配行为变化，按对应业务出口验收。表内完成标记描述当前分支，不表示已经部署或合入 `develop`。

| 步骤 | 内容 | 验收 |
| --- | --- | --- |
| 1 清理 ✅ | 从当前 `develop` 建立 `archive/writeback` 分支；执行第 6 节删除清单（标注"移到第 3/4 步"的除外） | 全部现有测试、lint、类型检查、构建通过 |
| 2 目录分离 ✅ | `web/` → `frontend/`（独立 `package.json`，引入 `react-router`）；`netsuite/` 独立；更新 Dockerfile、启动脚本。根目录保留一个**不含依赖**的 `package.json` 作为命令入口，原有 `npm.cmd run …` 命令不变 | 本地联动启动、Docker 构建、全部检查通过 |
| 3 数据库基线 ✅ | 新迁移链 `0001_baseline` 建 24 张表（版本表 `schema_version`）；数据库连接收为一个引擎、一个 `core/database.py`；引入 `core/events.py`。`create_app` 当时保留的 `business_engine` 过渡参数已在 4e 删除 | 隔离 MySQL 空库执行基线迁移，表结构与[数据库设计](database.md)一致 |
| 4a source ✅ | 新建 source 模块：NS 读取逻辑由 business 移入；同步保存写入 `source_*` 新表（主数据、明细、关联、依据状态、内容摘要）；采购报关联查改为 `POST /api/source/pl-comparison`；迁移 `0002` 增加 `parent_order_no` | 新表保存与读取测试通过；旧链路不受影响 |
| 4b review ✅ | 新建 review 模块（审核记录、审核行、`ReviewApproved` 事件）；财务核对页改为 `/review`（旧地址跳转）并使用 `/api/review/*`；同步页保存改走 source 新表 | 新页面审核走新表；task 接入前审核通过暂不生成开票任务 |
| 4c task ✅ | 新建 task 模块（任务、任务行、合同、通知、供应商群），订阅 `ReviewApproved` 生成任务；开票跟进页改为 `/tasks`（旧地址跳转）并使用 `/api/tasks/*`；source 增加只读门面 `SourceDirectory`；迁移 `0003` 增加任务审核版本与通知发送员工、登记说明 | 审核通过自动生成任务行；收票进度在 4d 接入 |
| 4d invoice + matching ✅ | 原地重建发票与比对（置信度建议、人工通过、`AllocationChanged`）；发票、比对页切换（`/matching`、`/matching/:invoiceId`）；source 同步读取母采购单头，子采购单币种取自母采购单（迁移 `0004`）；锁与名称规范化移入 `core/` | 一张报关单从审核走到任务完成，无需手工改状态（SQLite 测试与浏览器已验证）；MySQL 并发由补强步骤统一验收 |
| 4d 补强 A—D ✅ | 按数据库第 10 节依次补币种证据、全局开票依据、任务后继、发票版本、双数量换算及冲正 | 固定 CNY 与母单继承、重复报关、完成后增量、撤销重开、版本复核与额度守恒；MySQL 迁移、并发和回滚验收通过 |
| 4e 切换收尾 ✅ | 删除 business、reconciliation、audit、旧迁移链、`create_app` 过渡参数、`source.public` 过渡期导出及第 6 节标注"移到第 4 步"的删除项 | 只剩一套实现，全部测试通过 |
| 5 定时同步 | sync 模块切换新表；NS 报关和子采购定时拉取；柠檬云 open2 定时拉票并生成比对建议 | 无人操作时新报关单、新发票自动进入工作台 |
| 以后 | 多账号与角色、企微自动发送、NS 回写（从分支恢复） | 另行设计 |

### 本次本地验收（2026-10-15）

- 后端完整回归：321 通过、2 跳过（SQLite 不执行 MySQL 版本字段宽度校验，同项 MySQL 已通过）。隔离 MySQL 8.4.9 完成迁移、版本表扩宽与 7 项并发/事务回滚测试。
- 前端 HTTP 14 项、组件 19 项、NS 来源脚本 3 项通过；构建、lint、类型与架构检查通过。后端受版本管理的源码及本次新增文件通过 Ruff 检查与格式检查。
- 浏览器使用隔离数据走通币种补证、审核换版、分配复核、替换失败回滚与成功、差异结束；1280 与 390 宽度页面没有横向溢出。
- `npm.cmd run check` 在格式阶段被 35 个既有、未修改文件阻断；没有放宽质量规则。以上各项已分别执行，不将统一命令描述为全绿。
- 本机业务库 `127.0.0.1:3306/financial_invoice_business` 已升级至 `0009_matching_ledger_versions`，并在整库备份、管理员确认后手工清理 21 张旧表、2,487 条记录；保留的 31 张表记录数未变化，详见[数据库设计第 9.1 节](database.md#91-4e-退役表核对清单)。本次未触发真实 NS 写入，未在其他环境执行旧表清理或验证部署；其他目标库仍须备份、在线 `db:upgrade` 并核对待复核数据。上述验收时 open2、定时同步不属于已完成项；2026-10-16 已新增 open2 手动票头拉取，正式联调、商品明细与定时同步仍未完成，见[接入说明](../lemon-invoice-sync-plan.md)。

## 8. 超开处理

- `matching` 人工通过时不因超开而拒绝，必须填写说明，记录超开标记。
- `task` 收到「分配变化」事件后重新汇总：超开单独标记，仍按数量、金额的完成条件或显式差异结束判断，不能因为一项超开而掩盖另一项欠开。此项已随 4d 补强实现。
- 详细规则见[数据库设计](database.md)第 5、6 节。

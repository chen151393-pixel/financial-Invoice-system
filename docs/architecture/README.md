# 系统架构设计 v2（草案）

状态：**已确认（2026-10-09），按第 7 节分步实施中**。依据 `develop` 分支 `3537372`（已统一运行时数据库、新增供应商企微群配置）编写。各步骤完成后在第 7 节标注。

配套规则：

- [后端规则](backend-rules.md)
- [前端规则](frontend-rules.md)
- [数据库设计](database.md)：按整条链路重新设计的 24 张表、比对规则、状态规则、建表与上线

## 0. 已确认的决定

| 问题 | 决定 |
| --- | --- |
| 应开票口径 | 财务审核**不调整**。报关单通过自动关联找到子采购单，**按子采购单开票**；一张发票可以对应多张子采购单，一张子采购单也可以由多张发票开完 |
| 登录、角色 | 暂不设计。沿用现有单账号与本机会话，先把业务链路做完整 |
| 前端路由 | 引入 `react-router` |
| NS 回写 `writeback` | 整体移到单独分支 `archive/writeback`，主线删除 |
| 模块设计 | 参照 Java 微服务分层：模块对外只暴露门面接口和事件，模块内部按层分目录，一个文件只管一个业务对象；改一个模块不影响其他模块 |
| 新增规则 | 写在所属模块自己的代码中，不放进公共目录、入口文件或前端 |
| 公共能力 | 优先复用现有代码（清单见[后端规则](backend-rules.md)第 3 节、[前端规则](frontend-rules.md)第 3 节），不另建一套 |
| 同一子采购单出现在多张报关单 | **只生成一次**任务行：第一次审核通过时生成，之后的报关单不重复生成，任务详情显示关联的全部报关单 |
| 超开 | **允许确认并标记超开**：发票累计数量或金额超过子采购行应开值时可以人工通过，须填写说明，任务行带超开标记 |
| 发票单位 | 与子采购单单位一致；不一致时降低置信度，交人工审核 |
| 比对与完成 | 系统生成带置信度的比对建议，全部由人工审核；人工比对通过（可按差异结束）后该子采购行即结束，全部结束后任务自动完成，无另外的关闭步骤 |
| 数据库 | 按整条链路重新设计（[数据库设计](database.md)），不在旧表上修改；旧数据为测试数据，不迁移；合同 PDF 只存共享盘路径 |
| 供应商比对 | 子采购单上没有纳税人识别号，先按规范化名称比对 |

## 1. 业务主线

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
| `identity` | 本机会话（暂不扩展） | identity |
| `source` | NS 报关单、子采购、母采购来源和自动关联；采购报关联查；供应商目录 | `business` |
| `sync` | 定时与手动同步 NS、柠檬云；同步记录 | sync |
| `review` | 财务核对、审核快照、审核历史 | `reconciliation` 的审核部分、`audit` 的审核审计 |
| `task` | 开票任务、任务行、合同归档、供应商企微群、通知 | `reconciliation` 的任务、合同、通知、供应商群部分 |
| `invoice` | 发票导入（Excel、柠檬云）、查询 | invoice |
| `matching` | 发票行与子采购行的数量分配、确认 | matching |

删除：`writeback`（移到分支）、`audit`（审核审计归 `review`，回写审计随 `writeback` 移走）。不预建 `dashboard`、`exception`。

### 3.1 模块之间如何连接

参照微服务：模块之间只有两种连接方式。

1. **调用门面**：导入对方的 `public.py`，相当于对方的对外 API。只用于**读取**对方数据。
2. **发布/订阅事件**：一个模块完成操作后发布事件，其他模块订阅并在**同一个数据库事务**里更新自己的数据。发布方不知道谁在订阅。

```text
读取依赖（箭头指向被调用方）：
  sync     → source、invoice
  review   → source
  task     → source
  matching → source、invoice、task

事件：
  review   发布「审核通过 ReviewApproved」        → task 订阅：生成任务和任务行
  matching 发布「分配变化 AllocationChanged」     → task 订阅：更新已收数量金额和任务状态
  source   发布「来源变化 SourceChanged」         → review 订阅：标记需重新审核（后续）
```

- 禁止循环读取依赖。`task` 不读取 `matching`，收票进度只通过事件更新。
- 事件契约（数据类）定义在发布方的 `public.py` 中；订阅关系只在 `app.py` 中登记。
- 事件在发布方的事务中同步执行；任何订阅方失败，整个事务回滚。订阅方不能调用外部系统。

## 4. 数据模型

完整表结构见[数据库设计](database.md)。要点：

- **开票单元是子采购行**。审核通过时把子采购行的采购口径数量、单位、含税金额冻结为审核行，任务行从审核行复制应开值。
- **只生成一次**：任务行对有效的子采购行加唯一约束；同一子采购行关联的全部报关单从审核行查询得出。
- **分配挂在子采购行上**：比对记录先是系统建议（带置信度），人工通过后才计入收票；任务行的已收值由已通过的分配汇总，重新审核后进度自动延续。
- **数据按组织共享**，只按 NS 账套区分；时间、主键、金额类型全库统一。

任务状态由任务行汇总得出，不提供手动修改：

```text
documents_pending → notify_pending → awaiting_invoice → partially_received → completed
任何未完成状态 → superseded（被新审核版本替代，只读保留）
```

## 5. 数据库

- 一个数据库（业务 MySQL）、一个引擎、一条迁移链。新迁移链从 `0001_baseline` 开始，一次创建[数据库设计](database.md)第 4 节的 24 张表，版本表 `schema_version`。
- 旧数据为测试数据，**不迁移**；旧表不再被新代码读写，代码不删除库中的旧表，全部模块切换后由管理员确认删除，或直接使用新建的空库。
- 旧迁移链（`backend/migrations`、`backend/business_migrations`）、旧表定义、`core/business_database.py`、`core/application_database.py`、`backend/database.py`、`DATABASE_URL` 变量，随第 3、4 步删除。连接配置保留 `BUSINESS_DATABASE_URL` / `BUSINESS_MYSQL_*`。
- 回写的 `ns_previews`、`ns_target_locks`、`ns_audit` 不进入新结构；旧表留在旧库中，代码不再引用。

### 5.1 表归属

| 模块 | 表 |
| --- | --- |
| source | `source_suppliers`、`source_companies`、`source_raw_records`、`source_parent_orders`、`source_parent_order_lines`、`source_purchase_orders`、`source_purchase_order_lines`、`source_customs_declarations`、`source_customs_lines`、`source_customs_purchase_links` |
| review | `review_records`、`review_lines` |
| task | `task_supplier_groups`、`task_tasks`、`task_lines`、`task_documents`、`task_notifications`、`task_events` |
| invoice | `invoice_raw_records`、`invoice_headers`、`invoice_lines` |
| matching | `matching_allocations` |
| sync | `sync_runs`、`sync_cursors` |

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

每一步一个 PR，合入 `develop` 后再开始下一步。前四步只调整结构，业务功能保持不变。

| 步骤 | 内容 | 验收 |
| --- | --- | --- |
| 1 清理 ✅ | 从当前 `develop` 建立 `archive/writeback` 分支；执行第 6 节删除清单（标注"移到第 3/4 步"的除外） | 全部现有测试、lint、类型检查、构建通过 |
| 2 目录分离 ✅ | `web/` → `frontend/`（独立 `package.json`，引入 `react-router`）；`netsuite/` 独立；更新 Dockerfile、启动脚本。根目录保留一个**不含依赖**的 `package.json` 作为命令入口，原有 `npm.cmd run …` 命令不变 | 本地联动启动、Docker 构建、全部检查通过 |
| 3 数据库基线 | 新迁移链 `0001_baseline` 建 24 张表（版本表 `schema_version`）；数据库连接收为一个引擎、一个 `core/database.py`；引入 `core/events.py` | 隔离 MySQL 空库执行基线迁移，表结构与[数据库设计](database.md)一致 |
| 4 模块重建 | 按 source → review → task → invoice → matching 顺序，每个模块一个 PR：改为分层目录、改读写新表、实现该模块在链路中的职责（审核行、任务行、比对建议、事件）；完成第 6 节标注"移到第 4 步"的删除；删除该模块的旧表定义和旧迁移 | 每个 PR 全部测试通过；最后一个 PR 合入后，一张报关单从审核走到任务完成，无需手工改状态；MySQL 并发测试通过 |
| 5 定时同步 | sync 模块切换新表；NS 报关和子采购定时拉取；柠檬云 open2 定时拉票并生成比对建议 | 无人操作时新报关单、新发票自动进入工作台 |
| 以后 | 登录与角色、企微自动发送、NS 回写（从分支恢复） | 另行设计 |

## 8. 超开处理

- `matching` 人工通过时不因超开而拒绝，必须填写说明，记录超开标记。
- `task` 收到「分配变化」事件后重新汇总：超开的任务行带超开标记并视为已结束，任务列表可按"含超开"筛选。
- 详细规则见[数据库设计](database.md)第 5、6 节。

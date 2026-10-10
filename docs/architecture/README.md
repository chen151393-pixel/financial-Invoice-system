# 系统架构设计 v2（草案）

状态：**已确认（2026-10-09），按第 7 节分步实施中**。依据 `develop` 分支 `3537372`（已统一运行时数据库、新增供应商企微群配置）编写。各步骤完成后在第 7 节标注。

配套规则：

- [后端规则](backend-rules.md)
- [前端规则](frontend-rules.md)

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
| 超开 | **允许确认并标记超开**：发票累计数量或金额超过子采购行应开值时可以确认，任务行状态为 `over`（超开待处理） |

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
├── docs/                     当前有效文档；历史方案放 docs/history/
└── Dockerfile、compose.yaml、.env.example、README.md、AGENTS.md
```

根目录不再有前端配置文件（`package.json`、`vite.config.ts`、`tsconfig.json` 等）和原型目录（`app/`、`worker/`）。

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

## 4. 数据模型调整

### 4.1 任务行（新增，task 模块）

```text
task_invoice_lines
  id, task_id, purchase_order_id, purchase_line_id,
  item_name, unit, currency,
  expected_quantity, expected_amount,     -- 来自子采购行：报关数量、含税金额；不调整
  received_quantity, received_amount,     -- 只由「分配变化」事件更新
  status: open / partial / received / over
  唯一约束：同一条子采购行只能有一条有效任务行
```

- 应开数量和单位沿用当前匹配使用的口径（子采购行 `declaration_quantity` / `declaration_unit`），应开金额为子采购行含税金额 `amount`。
- **同一张子采购单出现在多张报关单中**时，只在第一次审核通过时生成任务行；之后的报关单审核通过时不重复生成，任务详情显示关联的全部报关单。

### 4.2 统一分配台账（matching 模块）

- 现有两套台账：`invoice_purchase_allocations`（按数量分配，支持一单多票）和 `invoice_purchase_link_batches/pairs`（整票关联，一条子采购行只能关联一张发票，不支持一单多票）。
- 统一为按数量分配：保留 `invoice_purchase_allocations`；"整票关联"改为一次性批量写入分配记录；现有 `link_pairs` 中的记录（截图中为 2 条）用迁移转为分配记录，旧表停止写入。
- `invoice_purchase_allocations` 中预留但从未写入的 `review_*`、`customs_line_id` 列保留不动，不再使用。

### 4.3 任务状态

由任务行汇总得出，不提供手动修改：

```text
documents_pending → notify_pending → awaiting_invoice → partially_received → received → closed
                                                      ↘ over_invoiced（任一任务行超开，待处理）
任何未完成状态 → superseded（被新审核版本替代，只读保留）
```

## 5. 数据库收口

`develop` 已完成：运行时只连业务 MySQL；应用表进入同一个库；提供 `import_application_database` 复制旧应用库数据。

剩余工作：

| 问题 | 处理 |
| --- | --- |
| 两条迁移链、两张版本表（`alembic_version` 管应用表，`business_alembic_version` 管业务表） | 业务链冻结在 `0007_invoice_purchase_links`，之后**所有**新迁移只写入 `backend/migrations`；`manage upgrade` 先确认业务链在 0007，再升级主链。历史迁移文件不修改、不删除 |
| `create_app(engine, business_engine)` 两个参数、`core/database.py` 与 `core/business_database.py`、`core/application_database.py` 三个文件 | 合并为一个 `engine` 参数和一个 `core/database.py`；`application_database.py` 的导入工具移入 `manage.py` 所在的运维命令 |
| `DATABASE_URL` 与 `BUSINESS_*` 两套变量 | 只保留 `BUSINESS_DATABASE_URL` / `BUSINESS_MYSQL_*`（现有部署已在用），删除 `DATABASE_URL` |
| writeback 的 `ns_previews`、`ns_target_locks`、`ns_audit` 表 | 代码移走后表和数据保留在库中，不删除；删除前必须人工确认没有 `executing/unknown` 记录 |
| `unit_dictionary`（飞书 SKU 申报单位，163 行） | 当前代码不使用，归 `source` 模块，保留不动 |

### 5.1 表归属

| 模块 | 表 |
| --- | --- |
| source | `parent_purchase_orders`、`parent_purchase_order_lines`、`purchase_orders`、`purchase_order_lines`、`customs_declarations`、`customs_declaration_lines`、`customs_reconciliation_results`、`unit_dictionary` |
| invoice | `invoices`、`invoice_lines` |
| matching | `invoice_purchase_allocations`；停用 `invoice_purchase_link_batches`、`invoice_purchase_link_pairs` |
| review | `finance_review_snapshots`、`finance_reviews`、`finance_review_audit` |
| task | `finance_invoice_tasks`、`finance_task_documents`、`finance_task_notifications`、`finance_supplier_groups`；新增 `task_invoice_lines` |
| sync | 新增 `sync_runs`、`sync_cursors` |
| （已移出） | `ns_previews`、`ns_target_locks`、`ns_audit` |

每张表只属于一个模块，只有该模块的 DAO 可以读写。

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
| `backend/config.py`、`database.py`、`netsuite.py`、`auth.py` | 旧导入兼容入口，调用方改为新路径后删除。`database.py` 同时是 Alembic 元数据登记入口，**移到第 3 步**并入 `core` |
| `audit` 模块 | 审核审计并入 review；回写审计随 writeback 移走。**移到第 4 步**；第 1 步先把回写两张表的定义移入 `audit/entity.py`，保证历史数据导入仍原样复制 |
| `StorageService.sync(pl)`、`query(pl, page)` | 接口已删，方法暂留：承载 `_save` 去重、关联、回滚规则的主要测试。**第 4 步**把测试改为经 `sync_page` 后删除 |

### 6.2 前端与原型

| 删除项 | 依据 |
| --- | --- |
| `app/`、`worker/`、`.openai/`、根 `vite.config.ts`、`next.config.ts`、`next-env.d.ts`、根 `tsconfig.json`、`postcss.config.mjs`、`scripts/vinext.mjs` | Vinext / Cloudflare 原型，不参与正式部署 |
| `web/app/DemoPage.tsx`、`/demo` 路由；导航中"发票工作台、异常处理、系统对账、回写 NetSuite" | 指向演示数据 |
| `web/app/FinanceWorkbenchExamplePage.tsx`、`web/modules/reconciliation/example/` | 示例页 |
| `web/modules/business/`、`web/modules/writeback/` | 只有 README |
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
| 2 目录分离 | `web/` → `frontend/`（独立 `package.json`，引入 `react-router`）；`netsuite/` 独立；更新 Dockerfile、启动脚本 | 本地联动启动、Docker 构建、全部检查通过 |
| 3 数据库收口 | 第 5 节剩余工作 | 隔离 MySQL 上从空库初始化和从现有库升级都通过 |
| 4 模块重组 | `business` → `source`；`reconciliation` 拆为 `review` + `task`；各模块改为分层目录；引入事件；前端同步改名；完成第 6 节标注"移到第 4 步"的删除 | 架构检查覆盖新依赖方向，全部测试通过 |
| 5 打通链路 | 任务行、统一分配台账、匹配按任务行取候选、事件驱动任务状态 | 一张报关单从审核走到"已收齐"，无需手工改状态；MySQL 并发测试通过 |
| 6 定时同步 | NS 报关和子采购定时拉取；柠檬云 open2 定时拉票 | 无人操作时新报关单、新发票自动进入工作台 |
| 以后 | 登录与角色、企微自动发送、NS 回写（从分支恢复） | 另行设计 |

## 8. 超开处理

- `matching` 确认分配时不因超开而拒绝，确认结果中返回超开提示，由用户确认后提交。
- `task` 收到「分配变化」事件后重新汇总：已收数量或金额大于应开值时，任务行状态为 `over`，任务显示"超开待处理"，不自动进入"已收齐"。
- 超开的后续处理（红冲、调整分配、人工关闭）在第 5 步实现时细化，处理规则写在 `task` 模块的 `policy/` 中。

# 柠檬云后台拉票与每日计划

2026-10-19 代码已实现，归属 `sync` 模块。生产迁移、真实账套批量拉取和计划启用须在目标环境部署后验证；本次验收使用隔离数据库和上游替身。

## 页面与操作

- `/sync`：真实后台批次、状态筛选、分页、计划状态及下次执行时间。NS 仍使用独立手动入口，不把 NS 临时进度混入柠檬云历史。
- `/sync/lemon`：默认后台拉取；可切换每日同步计划。绑定、原单账套操作与 Excel 导入保留为辅助入口。
- `/sync/batches/:requestId`：可刷新恢复的批次详情；按账套展示读取、新增、换版、重复、业务类型排除、明细完整/待补齐计数，展开日期分片及失败原因。

全部账套指**当前绑定及已发现财务服务下的全部授权账套**。每批执行时重新发现账套，新增授权会自动纳入，支持排除项；也可固定选择账套。跨多个专业版服务和默认版混合账户的完整枚举尚未验证，页面明确展示此覆盖边界。固定选择的已撤权账套保留失败记录，不静默跳过。

业务类型沿用现有筛选；未选类型跳过，不删除已入库票据。提交只写入队列，HTTP 202 后页面关闭不影响后台执行。任务条件、账套和日期分片持久化，页面当前选中账套不影响已提交后台任务。

## 调度与恢复规则

每日计划支持 1—8 个 `HH:mm` 时间、最近 1—366 天（包含今天）的开票日期回扫，固定 Asia/Shanghai。启用、保存、暂停由管理员操作；配置版本冲突返回 409。暂停不取消已提交批次。初始计划为关闭状态。

计划存入数据库，由 FastAPI 生命周期启动消费者，每 2 秒检查一次。MySQL 命名锁跨消费者互斥，绑定及任务行锁防止重复提交和过期领取；外部读取在数据库事务之外。停机错过多个时点时合并为一次当前窗口回扫，不逐个补发历史时点。同一计划已有执行中批次时不叠加创建。

历史拉取按最多 31 天分片，每次提交最多 12000 个账套日期分片，待执行批次上限 20。上游明确返回票量超限且未保存时二分日期，单日仍超限则明确失败，不截断保存。串行执行分片，一个账套失败不阻塞其他账套。

发票仍使用原读取、版本去重、保存及事件服务，票据与原子请求 completed 结果在同一事务提交。后台汇总仅统计已提交结果；无新增可以正常完成，明细待补齐另行展示。入库不等于人工比对通过。

分片就是 `sync_lemon_runs` 中带 `run_id` 的拉票记录：`queued` 待执行，领取时转为 `running`，提交结果直接写在同一行，超量拆分的父片记为 `split`。进程中断后：未领取分片继续；已领取分片只核实本行提交事实。`running` 却不在本进程执行中的分片显示“结果待核实”（不落库，沿用单 API worker 约束），禁止直接重试和自动清锁，其他账套仍可执行。明确失败可生成新批次，仅包含失败日期分片；原记录保留。未知结果的管理端恢复入口尚未实现，须由管理员核实请求编号、原执行器与数据库提交事实后处理。

当前是开票日期回扫，不是修改时间增量游标：超过回扫窗口的迟到发票、历史修改需手动补拉；不推进 `sync_cursors`，不承诺上游分页快照完整。

## 接口契约

接口均要求当前系统管理员会话，前缀 `/api/sync/lemon`。

| 方法与路径 | 请求 / 响应 |
| --- | --- |
| GET `/background/configuration` | `plan`、业务类型选项、覆盖说明、`submit/pause` 的 allowed/reason；提交与启用共用绑定条件 |
| PUT `/plan` | `revision, enabled, accountMode, accountIds, excludedIds, businessTypes, times, lookbackDays`；返回最新配置和 `nextRunAt` |
| POST `/batches` | `requestId` UUID、`startDate/endDate` ISO 日期及账套/业务类型范围；202 返回已持久化任务 |
| GET `/batches?page=1&pageSize=20&phase=failed` | 后端分页/筛选，`items,total,page,pageSize,pages,counts,plan` |
| GET `/batches/{requestId}?page=1` | 批次、每页 20 个账套结果、日期分片、`retry` allowed/reason、`poll` |
| POST `/batches/{requestId}/retry` | 新 `requestId`；202 返回仅重试明确失败分片的新批次 |

`accountMode` 为 `all/selected`；全部模式使用 `excludedIds`，指定模式使用 `accountIds`。同一请求编号与相同参数返回原任务，改变参数拒绝；返回值不含令牌、密码或绑定摘要。统计由后端计算，界面不推断权限或提交成功。

## 代码与存储

Controller：`backend/modules/sync/controller/lemon_batch_controller.py`。Service：`lemon_batch_service.py` 提交/读取、`lemon_plan_service.py` 计划、`lemon_job_service.py` 分片执行与批次汇总、`lemon_worker.py` 消费。DTO/policy 校验与汇总，DAO 只操作本模块表。`app.py` 仅装配及启停。

迁移 `0023_sync_background` 追加 `sync_lemon_plans`、`sync_lemon_jobs`，扩展 `sync_runs` 的范围、请求编号、计划、细分阶段和配置快照，以及 `sync_lemon_runs.background`。`0025_sync_merge_lemon_jobs` 把分片并入 `sync_lemon_runs`（新增 `run_id`，删除 `background`），并删除 `sync_runs` 中与 `phase`/`scope_key`/`configuration` 重复的 `status`、`account`、`window_start`、`window_end`；`sync_lemon_jobs` 表与数据保留在库中待管理员处理，详见[数据库设计](architecture/database.md)“柠檬云分片并表与批次精简”。计划和批次时间以 UTC 存储/返回，页面按上海时间展示；开票窗口是包含起止当天的业务日期。

前端 `types/background.ts`、`api/background-api.ts`、`hooks/useBackground*.ts` / `useSyncBatch*.ts`、`components/Sync*Form.tsx` 与 `pages/` 负责契约、请求状态、表单及详情。路由集中在 `app/paths.ts`。移除同步中心未接入的管道卡片与虚构历史占位；NS 和单账套功能继续使用原实现。

## 部署与验证

先按 [部署文档](docker-deploy.md)备份目标数据库，执行 `npm.cmd run db:upgrade` 升至最新迁移（含 `0025_sync_merge_lemon_jobs`），构建前端并重启后端。Docker 使用既有部署流程重新构建/重建容器。保留单 API worker 的现有会话约束；数据库消费者互斥不代表登录会话已支持多进程。

迁移和重启不会自动启用新计划。管理员登录后检查绑定及覆盖范围，先提交小日期范围检查真实结果，再保存并启用每日计划。后台依赖服务进程持续运行；附件、默认版商品明细、NS 定时任务不在本次实现内。

验证入口：`npm.cmd run test:api`、`npm.cmd run lint:api`、前端 build/lint/typecheck/test:web、`npm.cmd run check:architecture`。新增 `test_lemon_background*.py` 覆盖持久队列、隔离、去重、分片、失败重试、未知保护和调度；MySQL 专项通过 `BUSINESS_MIGRATION_TEST_SERVER_URL` 指向专用测试实例，禁止使用生产建库连接。前端 `sync-background.test.mjs` 覆盖表单、计划、禁用原因与幂等请求。

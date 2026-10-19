# 系统整体链路与实现关系

2026-10-15：当前分支使用 source → review → task → invoice/matching 新链路；4d A—D 已实现，4e 删除了旧实现。代码完成不代表目标环境已部署迁移、配置 NS 或完成真实数据验收。

| 页面 | 接口 | 归属与持久化 |
| --- | --- | --- |
| `/sync/ns` | `/api/ns/sync/{kind}/pull-save` | sync 编排 source；`source_*` 保存来源与原始证据 |
| `/pl-reconciliation` | `/api/source/pl-comparison` | source 实时只读查询，不自动保存或审批 |
| `/review` | `/api/review/declarations/query`、`/{id}/approve` | review 保存报关审核和全局开票依据 |
| `/tasks`、`/tasks/:id` | `/api/tasks/*` | task 保存任务、合同、通知与状态历史 |
| `/sync/lemon`、`/invoices` | `/api/sync/lemon/*`、`/api/invoices/import/*`、`/api/invoices` | 绑定、选账套手动拉票、Excel 导入、原始数据、不可变版本 |
| `/matching`、`/matching/:invoiceId` | `/api/matching/*` | matching 建议、确认、取消、复核、原子替换 |

旧前端 `/finance-reconciliation` 和 `/invoice-followup` 保留跳转；旧 `/api/reconciliation/*` 已删除。没有正式 dashboard/exception 模块或演示成功入口。

```mermaid
flowchart LR
  NS[NS 来源] --> S[source 保存]
  S -->|SourceChanged| R[review 标记依据失效]
  R -->|ReviewApproved| T[task 生成后继]
  R -->|ReviewApproved / PurchaseBasisInvalidated| M[matching 台账]
  E[Excel 文件] --> I[invoice 版本]
  L[柠檬云专业版票头及商品明细] --> SY[sync 事务外读取]
  SY -->|LemonInvoicesFetched| I
  I -->|InvoiceChanged / InvoicesImported| M
  M -->|AllocationChanged 绝对合计| T
```

订阅顺序显式登记在 `backend/app.py:create_events`，审核先生成任务再重算；所有订阅复用发布方事务，任一步失败整体回滚。跨模块读经 `public.py`，不读写对方私有 DAO。

采购依据冻结主体、币种、数量、单位、金额和原始引用。多张报关单引用同一采购行时复用依据与任务额度；来源关键内容变化则待复核，重审后生成后继任务，包括已经完成的任务。兼容旧分配可以承接，收票数额来自台账，不复制旧任务缓存。

发票当前字段是版本投影。相同内容重复导入不增加版本；同来源变更追加版本，原确认保留并进入复核。明细重排不改变逻辑身份；身份歧义或缺少明细时保留旧行并禁止确认。作废/红冲立即撤销有效收票资格，原占用保留到取消或替换。

分配保留发票口径和采购口径数量，不同单位由后端按证据换算；发票自身数量金额不可超用。超开只提示，不能自动结束任务。按差异结束是 task 的独立决定，绑定依据和账本摘要，后续取消/失效/换版后撤销适用性。

资料准备、通知草稿和人工发送登记继续使用真实合同文件与持久记录。外部下载在事务外完成，登记与推进前复核来源；失败重试沿用首次文件身份，不能覆盖历史。企微群发已接入不可变预览、上传合同、创建群发、目标群回执与未知结果核实；提交不代表已发送，需群主在企微确认。部署与启用条件见[企微通知方案第 13 节](wecom-supplier-notification-plan.md#13-第一阶段实现与部署2026-10-19)。

所有关联写先取得数据库级账本命名锁，随后取得账户锁及行锁。当前写操作串行化，保证一致性优先；长来源读取期间可能令其他写操作等待或返回 409。正常启动不执行同步、迁移或缓存修复。必要时管理员运行 `python -m backend.manage rebuild-ledger`，从持久分配重新计算缓存；该命令不会核实待复核记录。

唯一迁移链为 `backend/migrations`。`0005`—`0009` 保留既有 v2 数据并回填证据；无法还原的历史标记待复核。旧业务表、旧版本表及 NS 回写锁留在数据库，清理须管理员另行处理。部署与验证见[Python 后端](python-backend.md)。

下一阶段是第 5 步持久调度和 open2 真实明细接入；自动通知、权限角色、NS 回写另行设计。本次不触发真实 NS 写入。

2026-10-16 补充：柠檬云已支持管理员选账套按开票日期手动拉取进项票头，通过 sync→invoice→sync 事件链原子保存票头、不可变版本和同步结果。API 明细仍待补齐，不生成逐行匹配建议；完整 Excel 通道继续运行。定时同步仍未实施，部署与边界见[柠檬云接入说明](lemon-invoice-sync-plan.md)。

2026-10-19 商品明细补充：专业版已接入只读详情并沿用 invoice/matching 版本与事件链；完整明细生成待审核建议，人工通过后更新任务。默认版 open2 仍只读票头。重新按原账套日期拉取可补全既有票头，不重复创建发票。此次无表迁移，真实明细接口和远端部署仍需在已绑定环境验收。


## 2026-10-19：柠檬云后台同步已接入

`/sync` 读取持久批次，`/sync/lemon` 提交全授权账套任务/每日计划，`/sync/batches/:requestId` 展示账套分片结果。sync 后台通过原 invoice 事件链保存及生成待审核建议，新增计划和分片表；没有引入第二套发票校验。旧段落所述定时未接入状态已被本节更新，NS 定时与修改时间增量游标仍待实现。生产迁移与启用步骤见[后台同步](lemon-background-sync.md)。

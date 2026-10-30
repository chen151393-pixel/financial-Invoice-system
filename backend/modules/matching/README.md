# matching 模块：发票比对

## 整单匹配与一单一票（2026-10-30）

本节替代下文“部分开票”“分次收票”“剩余应开逐张扣减”的规则，完整说明见[整单匹配规则](../../../docs/matching-whole-order-rules.md)。

- 一次匹配是整张发票对一张或多张完整子采购单；一张子采购单只由一张发票开具（`order_group_policy.taken`／`ONE_INVOICE`）。已有收票、待复核占用或已结束的子采购单不参与建议、不出现在人工候选里，整组通过时也会拒绝。
- 自动建议：覆盖整票、合计恰好相等的唯一组合（可一票多单），以及单张子采购单覆盖整票但有差异的候选，按置信度取最高分；不再按单行拆组合。
- 记账：`fit` 按明细顺序记到发票为止，`checks.orderShare` 保存整单应开；比对按整单应开计算。人工关联 `POST /manual-orders` 不再接收 `lines`，记账数由后端生成。
- 发票少：要求审核说明；确认时发布 `LinesClosedByDifference`，task 在同一事务内按差异结束这些明细。发票多：明细记满应开，要求说明。
- 旧逐行接口（`/candidates/query`、`/allocations`、`/allocations/{id}/replace`）前端不再调用、暂留给既有测试，不执行一单一票规则；确认无外部调用方后删除。
- 验证：`test_matching_manual_order.py`、`test_matching_whole_order_rules.py`，以及 `test_matching.py`、`test_matching_order_priority.py`、`test_ledger_versions.py` 的回归。

## 手动整单关联（2026-10-29）

人工关联的最小单位改为整张子采购单；可部分开票。

- `POST /api/matching/manual-orders/candidates/query`（`invoiceId`、`invoiceItemId`、`keyword`，沿用 `CandidateQuery`）：有效任务行按子采购单号、母单号、供应商、品名、报关单号筛选后按子采购单归并，读取整单全部有效来源行及其任务行（含已开完的行）。返回每张单的合计剩余应开（单位或币种不同时为空）、发票行对全部可分配明细剩余应开的整单比对与置信度、`block`、`lines`（未开完的明细）。按置信度、备注命中、单号排序。`keyword` 为空时 `rows` 只含置信度最高、可选且置信度大于 0 的一张（没有则为空），`total` 为全部候选张数，供页面默认展示；`keyword` 非空时至少 3 个字符（否则 400），最多返回 20 张。整单资格与自动建议共用 `order_group_policy.order_shares`：任一明细不在有效应开范围、依据变化、已按差异结束或进度不一致时整单不可选；已开完的明细不列出。
- `POST /api/matching/manual-orders`（`requestId`、`invoiceId`、`invoiceItemId`、`purchaseOrderId`、`invoiceVersionId`、`lines[{purchaseLineId, quantity, amount}]`、`note`、可选 `replaceAllocationId` + `replaceReason`）：`lines` 必须恰好覆盖该单当前全部可分配明细，数量与金额可为 0（本票不开）但须成对，至少一行大于 0。服务在账本锁内重新读取，取消被替换的原关联（须为本票已确认记录），写入整组分配（`checks.group.manual`，置信度为空，页面显示“人工关联”），随即按整单审核规则逐条通过（`group_view_service.approve_rows`）。存在不一致项或超出剩余应开时须填写说明；超出发票行容量、同行已有待审核建议、明细不一致等返回 409；任一失败整体回滚。重复提交按派生请求编号与请求指纹返回原结果，不同内容复用编号返回 409。
- 旧逐行接口 `POST /candidates/query`、`POST /allocations`、`POST /allocations/{id}/replace` 详情页已不再调用，保留给既有测试与可能的外部调用方；确认无调用方后删除。无数据库迁移，不触发 NS 写入。
- 验证：`backend/tests/test_matching_manual_order.py`（整单候选与明细、部分开票整组保存并通过及幂等、须覆盖全部明细、发票行容量与超开说明回滚、待审核建议阻止）。

## 置信度优先建议（2026-10-29 补充）

本节替代下文整单规则中的品名准入、单号排他召回和数量金额完全一致才建议的限制。

- 单号命中和供应商相近的已审核子采购一起参与候选评分。商品名称与报关品名均可作为品名证据，取更匹配的一项展示。
- 符合条件加分，部分符合按已有权重的一半计分，不符或缺失不加分；品名不一致不再直接淘汰。采购行按综合得分唯一定位发票行，最高分并列时不猜配。
- 完全对应的整单组合，以及能覆盖发票各行、数量和金额不超过发票可分配范围的整单候选，都参与最终评分。按方案内最低行置信度比较，默认生成最高分方案的待审核建议；最高分方案并列时留给人工选择。逐行人工候选也按置信度降序显示。
- 金额、数量或单位不一致可以生成待审建议，差异仍展示并要求核实。缺少有效财务审核、币种依据或任务行仍阻断；不生成超出发票可分配范围的占用，不改已确认记录，不自动通过或触发 NS 写入。
- 验证：`test_matching_confidence_suggestions.py`、整单及审核回归测试。历史未生成建议的发票须重新生成建议。

## 整单匹配规则（2026-10-29，替代逐行建议）

一个发票行对应一张或多张**完整**子采购单，不拆分子采购明细行；审核整组通过或驳回。

1. **召回**：备注命中子单或母单时，只在命中的子采购单（母单取其全部子单）中组合；都未命中才按供应商模糊匹配召回。
2. **整单资格**：子采购单全部有效明细都有当前开票任务与审核依据、币种明确、未按差异结束，且每行品名唯一对应一条发票行、单位相同（按单位字典名称）。
3. **组合**（`policy/order_group_policy.py`）：所选子采购单的剩余应开数量与含税合计须与发票行**完全相等**；先求覆盖整张发票的唯一组合，不成立时逐行求只涉及该行的唯一组合。没有组合、组合不唯一（如两张单金额相同可互换）、部分开票、超开或单位不同时**不自动建议**，由人工在详情页手动关联中处理（详情页的“整张子采购单匹配”表单已于 2026-10-29 移除，后端接口保留）。
4. **比对项**（`policy/group_comparison_policy.py`，权重 `GROUP_WEIGHTS` 在 `comparison_policy.py`）：子采购单号 15、销售方与供应商 15、购买方 5、品名 15、单位 10、数量合计 15、合计金额（含税）15、税额 10。
   - **供应商模糊匹配**（`supplier_result`）：去掉括号内容、“股份有限公司/有限责任公司/有限公司/公司”后缀和开头地名（省级简称、常见城市及“省/市/区/县”结尾的行政区名）后，相同或互相包含为一致；否则相似度 ≥ 0.6 为部分一致（须填写说明），更低为不一致。逐行比对与召回使用同一规则。
   - **税额**：子采购税额 = 各税率的含税合计 × 税率 ÷（1 + 税率），按税率四舍五入到分，与票面税额相差不超过 0.05 元为一致。税率来自 NS 子采购明细税码（source `tax_rate`），未同步时显示“未校验”、不要求说明。
   - **合计金额**：发票行价税合计对该行对应子采购明细的含税合计，容差 0.01 元；多行发票按各行对应范围汇总，不在每行重复整张采购单总额。原申报价项已移除，不再重复展示金额核对。
5. **存储与审核**：组内每条子采购明细仍单独记一条分配（任务按行计算收票进度），`checks.group` 保存组 ID 与子采购单 ID。`POST /api/matching/groups/{groupId}/confirm`（`invoiceId`、可选 `invoiceVersionId`、`note`）在同一账本事务内逐条通过，任一条失败全部回滚；需说明时说明作用于全组；同一操作重复提交返回原结果。`POST /api/matching/groups/{groupId}/reject` 整组驳回。组内记录不能单独通过或驳回（409）；批量通过按组处理，组内任一条不满足条件时整组跳过。
6. **视图**：`GET /api/matching/invoices/{id}` 新增 `groups`（`orders`、各发票行 `checks/confidence/quantity/amount/lines`、`noteReasons`、`confirm/reject` 能力、`allocationIds`），按当前来源实时重算。
7. **换算**：页面不再填写换算分子、分母与换算证据，默认 1 / 1；单位不同时以审核说明作为数量口径依据（单位不一致本身要求说明）。接口仍接受换算参数供既有调用方使用。
8. **迁移影响**：已有的逐行或拆分建议保留，点“重新生成建议”时由整单建议替代；已逐条通过的分配不动，如需改为整单，请先删除这些关联再重新生成。无需 matching 表结构迁移；source 新增迁移 `0038`（子采购明细税率）。

验证：`test_matching.py`、`test_matching_order_priority.py`（召回范围、供应商模糊规则、组合唯一性）、`test_matching_whole_order.py`。

## 整张子采购单匹配（2026-10-28）

- 详情页主入口以整张子采购单为候选，按备注中的子单或母单优先排列；显示供应商、采购公司、账套、完整明细数与剩余应开合计。不同单位或币种不强行相加。原逐行分配保留在“逐行分配与历史记录”，用于部分开票及差异处理。
- `POST /api/matching/order-candidates/query`：`invoiceId`、`keyword`、`page/pageSize`、`conversionNumerator/Denominator`；返回分页候选、`fingerprint`、`confirm.allowed/reason`、风险提示及逐行 `allocations` 预览。`source.public.purchase_order_lines` 校验整单全部有效来源行均有当前审核依据，不能将部分任务行当作整单。
- `POST /api/matching/orders/confirm`：`requestId`、`invoiceId`、`purchaseOrderId`、`fingerprint`、可选 `invoiceVersionId`、换算因子与证据、审核说明 `note`。服务在账本锁内重新生成预览并校验摘要，复用原分配审批逻辑，全部明细在同一事务提交；任一失败全部回滚。重复请求须操作者、参数和证据完全一致，不重复占用。已有确认分配的发票不能再整单分配。
- 保留票面原始行：单行汇总票按采购各行剩余数量和金额生成多条分配；每个发票行的数量、金额均须精确守恒。多行票只接受品名唯一对应，同名发票行存在歧义、混合未识别品名或合计不符时阻止整单确认，转逐行核实。不同单位仍需真实换算证据，不用金额相等代替单位校验。
- （已由 2026-10-29 整单匹配规则替代）单行汇总票存在唯一可完整分配整单时，自动建议拆到该单实际明细；重新生成替换旧待审建议并保留历史。无法形成完整整单方案时保留原逐行建议供核实，不自动确认。整单确认会在同一事务驳回该票原待审建议，并追加确认分配。
- 关键实现：`order_matching_policy.py`、`order_candidate_service.py`、`order_confirmation_service.py`、`order_proposal_service.py`；验证：`test_matching_whole_order.py`。无需数据库迁移，不执行 NS 写入。旧逐行接口仍由折叠区及已有调用方使用，待部分分配入口迁移后再删除，当前不移除。

## 整票审核队列（2026-10-28）

新增 `POST /api/matching/invoice-queue/query`，请求沿用 `QueueQuery`：`tier`、`anomaly`、`supplierId`、成对日期 `invoiceFrom/invoiceTo`、`page/pageSize`。响应 `rows` 每张发票一项，包含 `invoice` 票头、`proposalCount`、`purchaseOrders`、最低 `confidence/tier`、`anomalies`、`batch.allowed/reason` 和 `batchIds`；`total/counts/page/pages` 均以发票计数。超出末页回到最后一页，空结果为第 1 页。

供应商与日期先召回发票，再核对该票全部待审核建议；最低置信度分档和异常分类不隐藏同票其他建议。普通查询从 DAO 读取整票分组摘要，Service 筛选、分页后读取本页详细视图；异常筛选因依赖当前来源与审核能力，按每批 100 张完整核对后再分页，不截断单票或返回近似总数，大范围异常查询耗时可能较长。

旧 `/queue` 保留逐建议契约用于兼容与现有验证；正式审核队列页面改用整票接口。单票详情、逐条审核及批量确认接口与事务语义不变，批量仍逐建议事务，不表示整票原子通过。无需数据库迁移，不触发 NS 写入。

架构 v2 第 4d 步在原地重建：读写新表 `matching_allocations`（[数据库设计](../../../docs/architecture/database.md)第 4.5、5 节）。旧表 `invoice_purchase_allocations`、`invoice_purchase_link_*` 不再读写，旧的整票关联与数量分配不迁移。

4d 补强已实现：确认绑定发票版本与开票依据，双数量和换算证据随核实历史保存；待复核仍占用额度，不计入有效收票。过期建议自动驳回，原确认保留，通过 `reverify` 核实或 `replace` 原子替换。差异结束由 task 单独记录。

## 职责

- 生成比对建议：发票导入后（订阅 `InvoicesImported`）或页面"重新生成建议"时，按上文整单匹配规则生成整单建议（2026-10-29 起不再逐行选候选）。
- 人工审核：通过（必要时填写说明及换算证据）、驳回、取消已通过的分配、人工新建分配、批量通过高置信度建议。
- 通过或取消后在同一事务中发布 `AllocationChanged`，task 订阅后重算任务行已收与任务状态。

## 目录

| 层 | 文件 | 说明 |
| --- | --- | --- |
| controller | `matching_controller.py` | `/api/matching`：`GET /invoices/{id}`、`POST /queue`、`POST /summaries`、`POST /candidates/query`、`POST /allocations/{id}/confirm`、`/reject`、`/cancel`、`POST /allocations`（人工新建）、`POST /allocations/confirm-batch`、`POST /proposals/generate` |
| service | `proposal_service.py` | 生成建议；`on_invoices_imported` 订阅函数 |
| | `allocation_service.py` | 审核动作、加锁、发布事件 |
| | `matching_query_service.py` | 发票比对视图、审核队列、列表摘要、人工分配候选 |
| policy | `comparison_policy.py` | 比对项、权重、置信度分档、容差、子单 / 母单号匹配（只在这里定义） |
| | `allocation_policy.py` | 不能通过的情况、发票行容量、超开、需填写说明的情况 |
| dao | `allocation_dao.py` | 分配记录读写、汇总（锁定读）、队列 |
| mapper / dto / vo | `allocation_mapper.py`、`matching_dto.py`、`matching_vo.py` | 转换、请求、响应 |

## 规则

**候选与建议**

- 候选只来自有效任务行（已审核的应开范围，task 门面 `open_lines`）。
- 先按发票备注定位完整子采购单号或母采购单号。命中子单时召回该单明细；命中母单时召回来源中关联该母单的子采购明细；多单号取并集。只在命中范围内组合整单，其他订单不能凭供应商等字段抢占建议。单号全半角、大小写统一，`PO100` 不匹配 `PO1001`，`PO-100` 不匹配 `PO-100-2`。
- 有效任务范围内没有单号命中时，才回退到供应商规范化名称相同 / 一方包含另一方的候选。备注中的未知单号无法定位时仍按此回退，订单比对项明确显示未命中，不视为订单匹配成功。
- 发票“供应商名称”导入为 `seller_name`，与 NS 子采购的供应商名称比较。单号已命中时名称差异不阻止召回，但仍标明不一致、降低置信度并要求人工说明；没有自动建立供应商别名关系。
- 人工候选保留其他可选订单，但同样将备注命中项排在前面；关键字支持母采购单号。审核详情的订单项展示子单、母单及命中说明。
- 自动建议只有整单（见文首规则）；其他情况不自动建议，由人工处理。导入事件不覆盖已有待审核建议；手工“重新生成建议”会重新评估，候选、版本或比对结果变化时，将旧待审建议记为驳回并追加新建议，保留操作者、时间和替代原因。相同结果不重复追加；没有新候选时保留旧建议；已有确认分配的发票行不调整。作废、红冲、状态未知的发票不生成。
- NS 单号引用中的已知展示前缀“采购订单 #”或“Purchase Order #”在比对时清理，原始来源不改写；仍校验完整单号边界，不能将子单后缀或更长单号当作母单命中。前缀处理同时用于自动建议和人工候选排序。

**逐行比对项与置信度**（人工候选与逐条分配使用；整单建议见文首。权重：采购订单号 15、供应商名称 15、购买方 10、品名 15、单位 15、数量 15、含税金额 15；备注命中子单或母单均计订单满分）

- 一致得满分，一方包含另一方得一半；置信度 80 以上高、50–79 中、50 以下低。
- 品名比对前去掉发票品名开头的税收分类（如 `*化学品*`），对应子采购行的品名（`declaration_name`，为空时使用 `item_name`）；本次分配数量、金额不超过剩余应开时支持分次收票，不因未收齐而降分；收齐金额容差 0.01 元。
- 子采购单位为空记为不一致（注明"子采购单位缺失"）。

**不能通过**（返回 409）

- 发票作废或红冲；子采购行已停用或没有有效任务行。
- 子采购币种待核实（没有母采购单、母采购币种缺失等，见 source 模块币种规则），或发票币种与子采购币种不一致。
- 建议生成后子采购行内容变化（比较生成时保存的子采购行摘要）。
- 同一发票行已通过的分配加本次会超过发票行本身的数量或金额。

**需要填写说明**（未填返回 400）：存在不一致项、超开（超过剩余应开，记 `exceeds_expected`）。发票未提供购买方（柠檬云 Excel 不含该列）只降低置信度，不要求说明。柠檬云 API 票的购买方取自账套名称（比对说明显示“购买方取自柠檬云账套名称”），与采购公司不一致时同样要求说明。

**比对项展示文字**（`policy/check_label_policy.py`，2026-10-30）：响应中的 `resultLabel`、`differenceLabel` 由已保存的结果与差额推导，不入库、不改判定和分数，历史建议同样适用。逐行比对中数量/金额不超过剩余应开（金额差超过 0.01 元容差）时显示“分次收票”和“收票后剩余应开 X”，不再显示“一致”加负数差额；不一致时显示“发票多/少 X”。

**批量通过**：只处理高置信度、无需说明且满足全部条件的建议；整单建议按组在一个事务内通过，其他逐条独立事务，返回通过与跳过原因，仍记录操作人。

**并发与加锁**：先取得数据库级账本命名锁，再按 来源 → 开票依据 → 任务 → 任务行（task 门面）→ 发票（invoice 门面）→ 分配；发票行已用量与子采购行已通过合计使用锁定读，避免 MySQL 可重复读快照导致超用或丢失更新。

**身份**：`service:` 身份只读。人工新建带 `requestId`，重复提交只生效一次。

## 公开接口（`public.py`）

- 事件 `AllocationChanged(receipts, actor, reason)`；`LineReceipt` 含当前依据 ID、有效采购数量/金额、待复核数量/金额、复核标记与账本摘要；合计只来自持久分配。

## 依赖

读取：`invoice.public`（`read_invoices`、`lock_invoice`）、`source.public`（`purchase_lines` 子采购行比对上下文）、`task.public`（`open_lines`）。订阅关系在 `app.py` 中登记。

## 验证

- `backend/tests/test_matching_order_priority.py`：订单范围优先于总分、母单下按商品选子单、多单号、供应商差异、完整单号边界与真实导入后查询 / 母单搜索。规则调整不覆盖已有待审核或已确认分配；旧建议可驳回后重新生成。
- `backend/tests/test_matching.py`（SQLite，source、review、task、invoice 均为真实服务）：审核 → 任务 → 导入 → 建议 → 通过 → 任务完成；取消回退；驳回后重新生成；说明与超开；币种待核实与红冲；容量与来源变化；人工新建幂等；重新审核延续进度；队列与批量；HTTP。
- `backend/tests/test_matching_mysql.py`：并发分配不超用发票行、并发通过不丢失子采购行已收合计。需 `BUSINESS_MIGRATION_TEST_SERVER_URL`，未提供时跳过；本次使用隔离 MySQL 实例执行，具体结果见交付记录。

## 新增接口与恢复

- `POST /api/matching/allocations/{id}/reverify`：使用 `ConfirmBody`，前端提交当前 `invoiceVersionId`、`purchaseBasisId`、换算因子/证据和说明。后端重验当前两端版本、有效性及占用；保留原确认人和时间，追加核实历史。
- `POST /api/matching/allocations/{id}/replace`：`ManualBody` 加非空 `reason`；原取消与新确认同事务，失败时原占用不变。人工分配表单可选择替换的原记录。
- `approval_service.py` 负责版本/容量校验，`ledger_service.py` 负责失效、承接和绝对合计，`replacement_service.py` 负责原子替换。
- `python -m backend.manage rebuild-ledger` 用持久台账修复任务缓存，不自动核实历史。
- 回归增加 `test_ledger_versions.py`、`test_ledger_migration.py`，覆盖版本、换算、复核、差异结束、原子替换和恢复。旧 business/reconciliation 测试已随退休实现移除；新链路承担业务验收。

## 发票列表金额统计（2026-10-19）

`GET /api/matching/invoice-totals` 接收 `q`、`status`、`date_from`、`date_to`，与发票列表同筛选，不接收页码。`service/invoice_totals_service.py` 通过 invoice 只读门面读取全范围票面汇总及分批票头，只通过本模块 DAO 读取确认分配，通过 review 门面核实当前依据；MySQL 查询期间使用 REPEATABLE READ 快照，返回连接池后恢复原隔离级别。

响应 `amounts[]` 按币种包含 `currency/count/gross/tax/pendingAmount/pendingCount/reviewAmount/reviewCount`；金额均为十进制字符串，计数为对应发票去重数量。价税合计和票面税额包含筛选范围内的红字金额，不表示抵扣认定。

`policy/invoice_totals_policy.py` 定义口径：正常发票的待匹配金额为含税金额减有效确认金额，逐票取不小于零；有效确认须为 valid、明细完整，且核实历史中的发票版本、开票依据与当前允许的依据一致。建议、驳回、取消不抵减；作废、红冲、未知状态的票不计待匹配。已确认但不满足有效条件的分配全部计入待复核金额，不因票面失效隐去历史占用。待复核与待匹配可重叠，不能相加，也不等同所有业务异常的金额。

无结果返回空分组；读取失败返回 503，不冒充零。原列表与单票匹配接口保留。测试见 `backend/tests/test_invoice_totals.py`、`backend/tests/test_invoice_totals_mysql.py` 和 `frontend/tests/invoice-totals.test.mjs`，无需数据库迁移。

## 单位名称展示（2026-10-16）

发票比对采购侧与单位比对项通过 source 只读门面解析为单位名称，仅影响展示，不修改原始编号、数量金额或审核／比对结论。字典缺失、停用及未知编号保留原值，规则与兼容表归属见 [source 单位说明](../source/README.md)；验证见 `backend/tests/test_unit_display.py`。

## 比对详情页布局与票面（2026-10-28）

- 页面自上而下：整张发票票面（票种与状态、购买方／销售方及纳税人识别号、商品明细表含单位／数量／单价／金额／税率／税额、合计金额与税额、价税合计、备注）→ 左右分栏核对（左侧发票商品明细，右侧所选行与子采购行逐项比对）。逐行核对不再收在折叠区内。2026-10-29 移除详情页顶部回写准备提示和底部整单匹配表单；后端接口与规则保留。
- 同一发票行有多条待处理比对（如整单拆分）时，右侧先列出各条子采购行供切换，一次只展开一条逐项比对，避免几十张相同卡片堆叠；左侧导航只汇总涉及的子采购单号。
- `GET /api/matching/invoices/{id}` 响应新增 `paper`（`invoiceType`、`buyerTaxNo`、`sellerTaxNo`、`net`、`tax`、`gross`），`items[]` 新增 `unitPrice`、`net`、`taxRate`（如“13%”）、`tax`。票面金额按两位小数并带千分位的文本返回，前端只展示不计算；原 `invoice`、`items[].amount` 等字段不变。数据经 invoice 门面 `read_invoice_paper` 读取，不进入比对与回写快照。
- 组件：`components/InvoicePaper.tsx`（票面）、`InvoiceLineNav.tsx`、`InvoiceLinePanel.tsx`；样式在 `components/matching-detail.css`。验证：`test_matching_whole_order.py::test_detail_view_returns_invoice_paper`，本地隔离 SQLite 合成数据预览（1440px 与 375px）。

## 单位按字典名称比对（2026-10-28）

NS 子采购单位保存的是单位编号（如 `20`），票面是单位名称（如“卷”）。此前比对直接用编号与票面名称比较，同一单位也判为不一致，连带数量不一致、置信度下降，并要求填写说明和换算证据。现在 `comparison_policy.same_unit` 统一按 source 单位字典名称判断是否同单位，覆盖逐行比对、整单候选警告与规划（`order_matching_policy`）、确认换算（`conversion_policy`）和回写就绪（`writeback_readiness`）。

- `source.public.purchase_lines` 上下文新增 `unit_name`（字典名称，未知编号保留原值），不进入行摘要，字典调整不会使已有建议过期；原 `unit_display` 由它替代。
- 分配记录与开票依据仍保存单位原值；同单位仍须 1 / 1 换算，不同单位仍须换算证据。
- 已生成的待审建议保存了旧置信度：详情页比对项实时重算，排序与分档需在详情页点“重新生成建议”后更新。
- 验证：`test_matching_whole_order.py::test_unit_code_resolved_before_comparison`。不需要数据库迁移，不触发 NS 写入。

2026-10-19：专业版 API 商品明细补全后沿用 InvoicesImported 订阅生成建议，不新增匹配算法或自动确认入口。明细不完整时禁止确认；发票先拉取、采购后审核时仍通过“重新生成建议”进入队列。完整拉票到收齐、重排去重、换版待复核、作废红冲、撤销和事务回滚见 `backend/tests/sync/test_lemon_detail_matching.py`，MySQL 复用验证见 `test_lemon_detail_mysql.py`。

## 发票工作台只读汇总

工作台查询与导出由本模块编排，通过各模块 public.py 门面在同一只读快照内读取，不改变审核、分配或任务状态。新增接口、统计口径和验证见[发票工作台](../../../docs/invoice-workbench.md)。

## 发票金额统计的账套条件

`GET /api/matching/invoice-totals` 接收可选 `account`（最长 100 字符，空值表示全部），通过 invoice 门面复用列表精确筛选；价税合计、票面税额、待匹配金额和待复核金额均覆盖所选账套的全部符合条件发票，不受页码影响。

## 队列分档计数类型（2026-10-20）

MySQL 的 `SUM(CASE ...)` 返回 Decimal，待审核建议非空时曾导致队列严格响应模型的整数校验失败。`allocation_dao.proposal_counts` 现在统一返回整数计数，保持空队列、高中低分档与分页口径不变。回归用例 `test_queue_counts_with_all_confidence_tiers` 在 SQLite 与独立 MySQL 测试库中共用，覆盖空队列、三档非空及分页；不改金额精度或比对规则。

## 工作台业务状态分区与筛选、比对队列筛选（2026-10-23）

- 工作台查询新增 `supplierId`、`createdFrom` / `createdTo`（报关单创建日期，中国日期）；作用于分区计数与核对、开票待办，比对待办只按账套与供应商筛选。响应新增 `stages`（五个分区：key、label、按报关单计数）、`noTaskCount`（无需开票张数）、`supplierOptions`；每条待办新增 `stage` / `stageLabel`，CSV 增加“业务状态”列。范围与分区规则在 `policy/workbench_scope.py`，业务状态归类复用 task 门面：

| 业务状态 | 判定 |
| --- | --- |
| 待审批 | 报关单待财务审核，或来源变化需重新审核（review 判断，优先于任务状态） |
| 待通知开票 | 任务处于待保存子采购合同、待通知供应商 |
| 待核票 | 任务处于等待开票、部分收票 |
| 资料已回 | 任务发票已收齐、资料待补齐（documents_incomplete） |
| 开票完成 | 任务发票收齐且资料全部到齐（completed） |

报关单级别取其当前任务中**最慢**的阶段；审核通过但没有任何当前任务（供应商均关闭通知）为“无需开票”，不进分区与待办。

- 比对队列 `QueueQuery` 新增 `supplierId`（子采购单的供应商，经 source 门面 `supplier_line_ids` 取子采购行）与 `invoiceFrom` / `invoiceTo`（开票日期，经 invoice 门面 `invoice_ids_between` 取发票），三档计数同样按筛选条件统计；响应新增 `suppliers` 选项（待审核建议涉及的供应商）。
- 验证：`backend/tests/test_business_stages.py`。

## 含税合计与“只看异常”（2026-10-29）

- 发票比对统一显示“合计金额”（接口 key 仍为 `amount`），使用发票价税合计与对应子采购明细含税金额。原 `price` 申报价项移除；报关金额、销售汇率与发票不含税金额不再参与发票匹配校验，财务核对的申报幅度规则仍保留。逐行部分开票沿用剩余额度判定；整单建议按所选明细合计核对。
- 备注按完整单号依次匹配子采购单、母采购单、**子采购单明确关联的销售订单**。销售单号来自 source 同账套关联；识别“销售订单 #”显示前缀及全角字符，不把长单号、其他子单或金额相同视为命中。说明展示命中的订单类型与单号。
- 本例备注 `VIE260529-01` 命中子采购的关联销售订单；`7,523.89 + 978.11 = 8,502.00` 与采购含税金额一致。单号没有已同步关联时仍提示不一致，需补同步或人工核实。
- 比对队列 `anomaly`：all / abnormal（需要说明或当前不能通过）/ normal。按异常筛选时逐条计算比对项，单次最多核对 3000 条（超过时返回 `notice` 提示缩小范围），分档计数按筛选结果统计。金额差异仍须说明；历史建议快照的 `price` 项在工作台异常统计中忽略。
- 详情实时重算；部署后已有建议的保存置信度、分档需点“重新生成建议”更新。无需数据库迁移，不自动确认、不写 NS。
- 验证：`test_matching_sales_reference.py`、`test_declared_price.py`、`test_matching_order_priority.py`、`test_matching_whole_order.py`。

## 发票文件批量上传（2026-10-26）

- 接口 `POST /api/matching/invoice-files/upload`（`invoice_file_controller.py` → `invoice_file_service.py`）：请求为原文件 base64 与可选人工指定的 `invoiceNo`，单次最多 20 个、单个 10 MB，仅 PDF、JPG、PNG（按文件头识别）。
- 识别：文件名中独立的 8–20 位数字串作为候选发票号码（税务平台下载的 `dzfp_<发票号码>_...` 可直接识别）；命中多个号码或同号多张已通过发票时返回 `ambiguous`，不猜测。
- 归属：只认 `confirmed` 且 `verification_status = valid` 的分配；经 `source.public.line_declarations` 找到子采购单所属报关单，按 `月份/CD号_真实报关单号/发票_<发票号码>` 归档（复用 `integrations/contract_archive.py`）。发票跨多张报关单时每个文件夹各存一份；作废、红冲、未通过或待复核返回 `not_ready`。
- 记录：`matching_invoice_files`（`invoice_file_dao.py`），发票 × 报关单唯一；同内容视为已上传，不同内容返回 `conflict` 且不覆盖。顺序为事务外读取并写共享盘 → 短事务登记。
- 只归档文件，不发布事件、不改变比对、收票进度与任务状态；报关资料中的“发票”（NS 下载）仍由 task 管理，两者互不替代。
- 新增读取：`invoice.public.invoices_by_number`、`source.public.line_declarations`。
- 验证：`backend/tests/test_matching_invoice_files.py`（未通过不归档、文件名识别与人工指定、同内容幂等与不同内容不覆盖、多号码歧义、服务身份只读、HTTP 登录校验）。

## 工作台漏斗、应开与已收、比对队列分档（2026-10-27）

`POST /api/matching/workbench/query` 新增：`funnel`（由五个业务状态累加的“至少走到这一步”报关单数及相对上一步的通过率，不含无需开票的报关单）、`monthly`（最近 6 个月人民币应开按关联报关单的 NS 创建月（北京时间），缺失日期不回退、由 unknownExpectedDates 提示，收票按全部正常入库进项票的开票月（含未匹配）；invoiceCount 为正常票张数，percent 为收票／应开比，可超过 100%；应开缺失只影响应开统计并另计数）、`queue`（待审核比对建议按置信度高 / 中 / 低分档计数）。规则在 `policy/workbench_reports.py`，任务应开合计由 task 门面 `workbench_tasks` 的 `expected` 字段提供（任一行缺失为空）。

## 进项发票按匹配状态筛选（2026-10-27）

`POST /api/matching/invoices/query`（`service/invoice_list_service.py`，方案见 [设计文档](../../../docs/invoice-match-status-filter.md)）：请求为发票列表筛选条件加 `matchStatus`（all / confirmed / partial / proposed / needs_review / none / excluded）与分页；在同一只读快照中经 invoice 门面 `read_invoice_status_scope` 从新到旧分批读取范围内发票，按 `policy/invoice_match_policy.py` 判定状态并计数，再由 `read_invoice_page` 在选中发票内按原排序分页。返回 `list`（与发票列表同结构）、`counts`（不受所选匹配状态影响）、本页 `summaries` 与 `notice`（范围超过 20,000 张时只覆盖最新的 20,000 张并提示，也是升级为投影表的信号）。`POST /api/matching/summaries` 改用同一策略，文字统一为 已匹配 / 部分匹配 / 待审核 / 待复核 / 未匹配 / 不参与比对。测试：`backend/tests/test_invoice_match_filter.py`。

## 总体工作台对齐设计稿（2026-10-27）

`POST /api/matching/workbench/query` 调整（口径见[总体工作台](../../../docs/invoice-workbench.md)）：

- 新增 `kpis`（`policy/workbench_kpis.py`：本月应开、已收票、待收、待财务审核、待通知供应商，含对比说明与近 6 个月序列）、`nodes`（进行中任务按开票跟进节点分布）。
- `funnel` 改为 `{steps, completionRate}`（`policy/workbench_flow.py`）：六步按报关单所处位置累加——待审核，或其当前任务中最慢的开票跟进节点（task 门面 `workbench_tasks` 的 `node`，与任务台同一判定），每步附卡点分项 `stuck`。
- `queue` 新增 `anomalies`：待审核建议按不一致比对项分类计数与条长，分类规则 `anomaly_policy.check_categories` 与比对队列共用。
- `suppliers` 每币种前 6 名、人民币在前，新增 `longestDays` / `overdue`（> 15 天）；待办新增 `role`（finance / purchase）与 `waitingDays`，CSV 增加“等待天数”列，任务原因不再拼接等待天数。
- 移除 `stages`、`month`、`trend`、`trendStart`、`trendEnd`、`latestInvoiceDate` 与请求参数 `trendStart` / `trendEnd`；`stage_counts`、`month_report`、`invoice_trend` 一并删除，invoice 门面的 `invoice_daily_amounts`、`latest_invoice_date` 及其读取器、DAO 已无调用方，同时删除。
- 验证：`backend/tests/test_workbench.py`。

## 整票回写准备（2026-10-28）

确认、人工分配、重新核实、取消及原子替换在完整用例最后发布 `InvoiceMatchingChanged`，writeback 在同一事务内调用公开 `read_writeback_snapshot` 判定整票就绪并入队。原 `AllocationChanged` 继续只负责开票任务进度；不从收齐标签反推完整审核。发票及采购依据变化会使旧任务失效。详见[准备模块](../writeback/README.md)。

## 发票比对搜索（2026-10-28）

`POST /api/matching/invoice-queue/query` 与兼容的 `/queue` 新增 `invoiceNo`、`supplierName` 字符串。发票号码按票面号码、供应商按关联子采购单供应商名称部分匹配；中英文逗号、分号、换行可分隔多条，同框 OR、跨框 AND，最多 50 条且每条 120 字符，通配符按字面匹配。日期、建议类型、置信度继续与搜索条件取交集；旧 `supplierId` 仍兼容。

`queue_scope.py` 经 invoice/source 公共门面读取完整 ID 范围，空结果保持空集合；整票队列先筛选命中发票，再读取该票全部待审核建议，计数与分页保持整票口径，不隐藏同票其他异常。不改审核规则，不需要数据库迁移。

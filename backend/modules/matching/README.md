# matching 模块：发票比对

架构 v2 第 4d 步在原地重建：读写新表 `matching_allocations`（[数据库设计](../../../docs/architecture/database.md)第 4.5、5 节）。旧表 `invoice_purchase_allocations`、`invoice_purchase_link_*` 不再读写，旧的整票关联与数量分配不迁移。

4d 补强已实现：确认绑定发票版本与开票依据，双数量和换算证据随核实历史保存；待复核仍占用额度，不计入有效收票。过期建议自动驳回，原确认保留，通过 `reverify` 核实或 `replace` 原子替换。差异结束由 task 单独记录。

## 职责

- 生成比对建议：发票导入后（订阅 `InvoicesImported`）或页面"重新生成建议"时，为每条发票行选出置信度最高的子采购行候选。
- 人工审核：通过（必要时填写说明及换算证据）、驳回、取消已通过的分配、人工新建分配、批量通过高置信度建议。
- 通过或取消后在同一事务中发布 `AllocationChanged`，task 订阅后重算任务行已收与任务状态。

## 目录

| 层 | 文件 | 说明 |
| --- | --- | --- |
| controller | `matching_controller.py` | `/api/matching`：`GET /invoices/{id}`、`POST /queue`、`POST /summaries`、`POST /candidates/query`、`POST /allocations/{id}/confirm`、`/reject`、`/cancel`、`POST /allocations`（人工新建）、`POST /allocations/confirm-batch`、`POST /proposals/generate` |
| service | `proposal_service.py` | 生成建议；`on_invoices_imported` 订阅函数 |
| | `allocation_service.py` | 审核动作、加锁、发布事件 |
| | `matching_query_service.py` | 发票比对视图、审核队列、列表摘要、人工分配候选 |
| policy | `comparison_policy.py` | 比对项、权重、置信度分档、容差、子采购单号匹配（只在这里定义） |
| | `allocation_policy.py` | 不能通过的情况、发票行容量、超开、需填写说明的情况 |
| dao | `allocation_dao.py` | 分配记录读写、汇总（锁定读）、队列 |
| mapper / dto / vo | `allocation_mapper.py`、`matching_dto.py`、`matching_vo.py` | 转换、请求、响应 |

## 规则

**候选与建议**

- 候选只来自有效任务行（已审核的应开范围，task 门面 `open_lines`）。
- 召回条件：发票备注含完整子采购单号（`PO100` 不匹配 `PO1001`），或销售方与供应商规范化名称相同 / 一方包含另一方。
- 每条发票行一个建议，数量与金额取整条发票行。已有待审核建议或已通过分配的发票行不再生成；作废、红冲、状态未知的发票不生成。

**比对项与置信度**（权重：子采购单号 15、销售方 15、购买方 10、品名 15、单位 15、数量 15、含税金额 15）

- 一致得满分，一方包含另一方得一半；置信度 80 以上高、50–79 中、50 以下低。
- 品名比对前去掉发票品名开头的税收分类（如 `*化学品*`）；本次分配数量、金额不超过剩余应开时支持分次收票，不因未收齐而降分；收齐金额容差 0.01 元。
- 子采购单位为空记为不一致（注明"子采购单位缺失"）。

**不能通过**（返回 409）

- 发票作废或红冲；子采购行已停用或没有有效任务行。
- 子采购币种待核实（没有母采购单、母采购币种缺失等，见 source 模块币种规则），或发票币种与子采购币种不一致。
- 建议生成后子采购行内容变化（比较生成时保存的子采购行摘要）。
- 同一发票行已通过的分配加本次会超过发票行本身的数量或金额。

**需要填写说明**（未填返回 400）：存在不一致项、超开（超过剩余应开，记 `exceeds_expected`）。发票未提供购买方（柠檬云 Excel 不含该列）只降低置信度，不要求说明。

**批量通过**：只处理高置信度、无需说明且满足全部条件的建议；逐条独立事务，返回通过与跳过原因，仍记录操作人。

**并发与加锁**：先取得数据库级账本命名锁，再按 来源 → 开票依据 → 任务 → 任务行（task 门面）→ 发票（invoice 门面）→ 分配；发票行已用量与子采购行已通过合计使用锁定读，避免 MySQL 可重复读快照导致超用或丢失更新。

**身份**：`service:` 身份只读。人工新建带 `requestId`，重复提交只生效一次。

## 公开接口（`public.py`）

- 事件 `AllocationChanged(receipts, actor, reason)`；`LineReceipt` 含当前依据 ID、有效采购数量/金额、待复核数量/金额、复核标记与账本摘要；合计只来自持久分配。

## 依赖

读取：`invoice.public`（`read_invoices`、`lock_invoice`）、`source.public`（`purchase_lines` 子采购行比对上下文）、`task.public`（`open_lines`）。订阅关系在 `app.py` 中登记。

## 验证

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

## 申报价校验与“只看异常”（2026-10-23）

- 比对项新增“申报价”（权重 0，不影响置信度）：发票不含税总价高于对应报关行人民币申报价，或单位一致时不含税单价高于申报单价（容差 0.01 元），结果为不一致——通过须填写说明（“发票不含税价格高于申报价”），因此不能批量通过。部分分配时按含税比例折算不含税金额。无法换算申报价（无行级报关关联、汇率缺失等）时为“未校验”并写明原因，不算异常、不要求说明。
- 比对队列 `anomaly`：all / abnormal（需要说明或当前不能通过）/ normal。按异常筛选时逐条计算比对项，单次最多核对 3000 条（超过时返回 `notice` 提示缩小范围），分档计数按筛选结果统计。每行返回 `anomalies`（价格、数量、单位、金额、品名、供应商、子采购单号、超开、不能通过）。
- 验证：`backend/tests/test_declared_price.py`。

## 发票文件批量上传（2026-10-26）

- 接口 `POST /api/matching/invoice-files/upload`（`invoice_file_controller.py` → `invoice_file_service.py`）：请求为原文件 base64 与可选人工指定的 `invoiceNo`，单次最多 20 个、单个 10 MB，仅 PDF、JPG、PNG（按文件头识别）。
- 识别：文件名中独立的 8–20 位数字串作为候选发票号码（税务平台下载的 `dzfp_<发票号码>_...` 可直接识别）；命中多个号码或同号多张已通过发票时返回 `ambiguous`，不猜测。
- 归属：只认 `confirmed` 且 `verification_status = valid` 的分配；经 `source.public.line_declarations` 找到子采购单所属报关单，按 `月份/CD号_真实报关单号/发票_<发票号码>` 归档（复用 `integrations/contract_archive.py`）。发票跨多张报关单时每个文件夹各存一份；作废、红冲、未通过或待复核返回 `not_ready`。
- 记录：`matching_invoice_files`（`invoice_file_dao.py`），发票 × 报关单唯一；同内容视为已上传，不同内容返回 `conflict` 且不覆盖。顺序为事务外读取并写共享盘 → 短事务登记。
- 只归档文件，不发布事件、不改变比对、收票进度与任务状态；报关资料中的“发票”（NS 下载）仍由 task 管理，两者互不替代。
- 新增读取：`invoice.public.invoices_by_number`、`source.public.line_declarations`。
- 验证：`backend/tests/test_matching_invoice_files.py`（未通过不归档、文件名识别与人工指定、同内容幂等与不同内容不覆盖、多号码歧义、服务身份只读、HTTP 登录校验）。

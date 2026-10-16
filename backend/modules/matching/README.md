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

## 单位名称展示（2026-10-16）

发票比对采购侧与单位比对项通过 source 只读门面解析为单位名称，仅影响展示，不修改原始编号、数量金额或审核／比对结论。字典缺失、停用及未知编号保留原值，规则与兼容表归属见 [source 单位说明](../source/README.md)；验证见 `backend/tests/test_unit_display.py`。

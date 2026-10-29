# 回写准备模块

2026-10-28 实现阶段 A/B：整票审核后持久入队、只读账单查询和不可变分配方案。**不包含 NS 写入、恢复或结果核实接口**。旧 `archive/writeback` 分支的通用预览执行器未恢复，旧库三张 NS 审计/锁表不修改。

## 职责与文件

- `service/queue_service.py`：订阅 matching 最终用例事件，同一事务判断整票就绪、入队和失效；不调用外部系统。
- `service/task_service.py`：列表、详情、历史检查、带版本与幂等编号的方案确认。
- `service/query_service.py`：领取五分钟只读租约，事务外调用已部署的查询 RESTlet，保存前重新核实审核快照及租约。
- `service/prepare_worker.py`：可配置的后台历史补扫（每批 25 张）及候选查询（每轮最多 4 个任务）；等待账单十分钟后再查。查询错误为 blocked，由用户核实后重查。
- `policy/plan_policy.py`：供应商、母单、子公司、币种、精确子采购归属、逐分配金额守恒和同账单本次合计校验。
- `entity/`、`dao/`：任务、发票当前任务指针、只追加方案、审计四张新表。迁移为 `0036_writeback_prepare`。

## 依赖与规则

通过 matching 的 `public.py` 读取整票审核快照；matching 经 invoice、review、source 的公开门面读取依据与身份。事件订阅仅在 `app.py` 装配，外部查询服务由入口注入。

整票须正常、正金额、税额已知且不为负（零税额照常登记）、人民币、明细完整，各行金额及数量完整确认，无待审建议，有效发票和采购依据版本一致。单位换算证据与结果必须匹配。来源须有效、同账套/供应商/采购公司，销售方与购买方名称规范化核对通过，NS 供应商、母单、币种内部 ID 完整。不满足这些条件时，发票详情显示具体未就绪原因，不创建可确认任务。

任务与审核快照按 `(invoice_id, fingerprint)` 去重。确认、人工分配、批量确认、原子替换的最后一步发出整票事件；取消、发票换版、采购依据变化使旧任务失效。写库失败会回滚整笔审核。使用现有数据库账本锁和唯一约束串行化本地变更。

唯一候选不等于归属明确：仅非历史任务、精确子采购关联唯一、真实 `subsidiary:*` 公司映射且全部校验通过时自动冻结方案。`classification:*`、空子采购关联、多候选、历史扫描均需人工确认实际子公司与账单归属，并保存证据。明确关联其他子采购的账单不能人工覆盖。查询结果不预留额度；即使 ready，也不能写入 NS。

确认需当前 `revision`、UUID `requestId`、`confirmScope: true`、5–1000 字依据和完整 `allocations`。金额必须是两位小数字符串。相同请求与身份重复提交返回原处理后的当前状态，正文或身份不同返回 409。重新查询清除当前方案指针并增加版本；旧方案与审计仍保留。结果未知保护属于后续写入阶段，本阶段不存在执行中的 NS 请求。

## 接口

全部需要现有认证身份；服务身份不能人工确认或重新入队。任务详情与动作按配置的 NS 账套隔离。

| 接口 | 作用 |
| --- | --- |
| `GET /api/writeback/tasks?keyword=&state=&page=1&pageSize=20` | 后端筛选分页，返回 items/total/pages |
| `GET /api/writeback/tasks/{id}` | 任务、审核分配、完整候选、当前方案、最近 100 条审计、允许动作 |
| `POST /api/writeback/tasks/{id}/refresh` | `{ "revision": 1 }`，只读重查候选；旧方案版本失效 |
| `POST /api/writeback/tasks/{id}/confirm` | 确认并持久保存不可变方案，不执行写入 |
| `GET /api/writeback/invoices/{id}` | 整票 ready/reason 及当前任务摘要 |
| `POST /api/writeback/invoices/{id}/recheck` | 同一规则重新检查，补入历史任务 |

部署与验收见 [操作说明](../../../docs/ns-writeback-prepare.md)。测试：`test_writeback_prepare.py`、`test_writeback_mysql.py`；后者仅在专用 MySQL 隔离库验证并发，缺少配置会明确跳过。

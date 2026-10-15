# task 模块：开票跟进

架构 v2 第 4c 步新建。财务审核通过后按 供应商 × 采购公司 × 币种 生成开票任务，跟进合同归档、供应商通知与收票进度。表结构见[数据库设计](../../../docs/architecture/database.md)第 4.3、6 节。

## 职责

- 订阅 `ReviewApproved`：在审核事务中生成任务与任务行（应开值从审核行复制），重新审核时替代旧任务。
- 合同：从 NS 下载子采购合同并保存到共享盘，数据库只记录路径与 SHA-256。
- 通知：保存通知版本、登记人工发送（企微自动发送未接入）。
- 供应商默认企微群配置。
- 收票进度（第 4d 步接入）：订阅 matching 的 `AllocationChanged`，按已通过分配的合计更新任务行已收与任务状态（`service/progress_service.py`）。

## 拥有的表

`task_tasks`、`task_lines`、`task_documents`、`task_notifications`、`task_events`、`task_supplier_groups`。迁移 `0003` 增加 `task_tasks.review_revision`（审核版本）、`task_notifications.sender_name`（发送员工）与 `note`（登记说明）。

## 目录

| 层 | 文件 | 说明 |
| --- | --- | --- |
| controller | `task_controller.py` | `/api/tasks`：`POST /query`、`GET /{id}`、`POST /{id}/documents/{orderId}/prepare`、`POST /{id}/notification/draft`、`POST /{id}/notification/record` |
| | `supplier_group_controller.py` | `/api/tasks/supplier-groups`：`/query`、`/suppliers/query`、`/wecom/query`、`/save` |
| service | `task_generation_service.py` | `on_review_approved`：生成、分组、跳过已有有效行、替代旧任务 |
| | `task_status_service.py` | `change_status`：任务状态唯一修改入口，检查转换表并写状态历史 |
| | `task_service.py` | 列表（分组分页、搜索、统计）与详情 |
| | `document_service.py` | 合同下载、登记、归档 |
| | `notification_service.py` | 通知版本与人工发送登记 |
| | `supplier_group_service.py` | 供应商群查询与保存 |
| dao | 每张表一个文件 | 只访问本模块的表 |
| policy | `task_policy.py` | 状态机、分组键、状态文案 |
| | `notification_policy.py` | 默认通知正文、可编辑 / 可登记判断 |
| mapper | `task_mapper.py`、`notification_mapper.py` | 行 → VO |

## 规则

**生成（数据库设计第 7 节第 3 步）**

- 分组键：供应商 + 采购公司 + 币种；任一身份缺失时按子采购单隔离，不凭名称合并。
- 同一子采购行只有一条有效任务行（生成列唯一约束）：已在其他报关单任务或已完成任务中的行跳过；整组都跳过时不建任务。
- 新审核替代旧审核：旧审核的未完成任务及其任务行置为 `superseded`，写状态历史；已完成的任务保留。
- 订阅方在审核事务中执行，失败时整个审核回滚；不调用外部系统。

**状态（数据库设计第 6.2 节）**

```text
documents_pending → notify_pending → awaiting_invoice → partially_received → completed
任何未完成状态 → superseded
```

- 合同全部归档 → `notify_pending`；登记人工发送 → `awaiting_invoice`。
- `partially_received`、`completed` 只由已通过分配的汇总驱动，不提供手动修改；发票可能先于合同或通知到达，此时直接进入收票节点。
- 取消已通过的分配后按实际收票退回：仍有收票 → `partially_received`；没有收票 → 收票前节点（已登记通知 → `awaiting_invoice`；合同已全部归档 → `notify_pending`；否则 `documents_pending`）。
- 任务行（数据库设计第 6.1 节）：数量相等且金额相差不超过 0.01 元为已收齐；超过应开为超开；人工勾选"已开完"为按差异结束；三者都视为结束（`received`）。
- 重新审核时，被替代任务行的已收进度带到同一子采购行的新任务行，新任务按进度直接进入相应节点。
- 详情页六个节点各按自身事实显示（合同是否归档、通知是否登记、是否收票、是否完成），不因任务完成而标记未做的步骤。
- 每次状态变化写 `task_events`。

**合同**：事务外下载 → 短事务登记首次获取记录（来源与 SHA-256）→ 事务外写共享盘（按首次获取日期建文件夹，北京时间）→ 短事务标记已归档。再次获取到不同内容时拒绝覆盖；共享盘失败记为 `failed` 并可重试。

**通知**：每次保存新增一个版本（需带当前版本号，不一致返回 409）；群名与启用的默认群一致时记录群 ID。登记发送要求合同已全部归档、已填写群名和发送员工、确认已发送并填写说明，发送时间带时区且介于任务生成与当前之间；同一登记的重试返回原结果。

**身份**：`service:` 身份只读，所有写操作返回 403。

**来源变化**：任务按审核时冻结的应开值跟进；来源变化不阻断任务，财务重新审核后旧任务被替代。

## 公开接口与依赖

- `public.py`：`open_lines(connection, purchase_line_ids=None, lock=False)`——有效任务行（应开、已收、单位）及所属任务（供应商、采购公司、币种、报关单）；`lock=True` 时按"任务 → 任务行"顺序加锁，供 matching 审核分配使用。
- 订阅：`ReviewApproved`（生成任务）、`AllocationChanged`（收票进度），均在 `app.py` 中登记。
- 读取：`source.public.SourceDirectory`（供应商、采购公司、子采购单号、行品名、供应商分页）。不读取 review；审核数据只经事件取得。
- 外部适配：`SubpoContractSource`（NS 合同）、`integrations/contract_archive.py`、`integrations/wecom.py`。
- 订阅关系在 `app.py` 中登记：`events.subscribe(ReviewApproved, on_review_approved)`。

## 过渡期

旧 `reconciliation` 模块的开票任务、群配置接口与旧表仍在，前端已不调用，第 4e 步删除。旧任务不迁移，旧地址 `/invoice-followup*` 跳转到 `/tasks`。旧供应商群配置不迁移，需在新页面重新维护。

## 验证

`backend/tests/test_task.py`（SQLite，source 与 review 真实保存）：生成与冻结值、重新审核替代、已完成行跳过、分组与隔离、订阅方失败回滚、列表搜索统计、详情、合同归档与拒绝覆盖、通知版本与登记、只读、供应商群、HTTP。并发与锁须在 MySQL 上验证。

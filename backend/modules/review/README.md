# review 模块：财务核对

架构 v2 第 4b 步新建。财务按 source 模块已保存的报关单与关联子采购明细整单审核；审核通过后保存审核记录，冻结开票口径的审核行，并发布 `ReviewApproved` 事件。表结构见[数据库设计](../../../docs/architecture/database.md)（`review_records`、`review_lines`）。

**2026-10-15 方案修订（待实施）**：数据库第 10 节计划新增 `review_purchase_bases`，按子采购行管理跨报关单的有效依据版本，`review_lines` 引用该版本。同内容复用，关键内容变化重审；不能仅按某张报关单的旧审核 ID 决定全局任务是否更新。该表、只读依据门面与失效事件尚未实现，下文描述当前代码。

异常币种在财务核对时凭合同或结算证据核实，币种、证据引用、来源摘要、操作者和时间随新审核版本保存；普通有母单子采购自动继承，无需逐票选择。人工核实不改 source / NS。已有缺币种审核不能原地补写；母单读取失败应先重试。后续 `ReviewApproved` 扩展依据 ID 与版本，matching 通过公开门面在确认事务中验证当前依据。

## 职责

- 报关单列表：关键字、账套、审核状态筛选与分页，状态计数在后端完成。
- 整单审核：财务人工确认，不调整金额；来源变化后要求重新审核，历史审核保留。
- 冻结开票口径：子采购行的采购数量、采购单位、含税金额（来源缺失时为空）。
- 发布 `ReviewApproved`：订阅方 task 模块（第 4c 步接入）在同一事务中生成开票任务；订阅方失败时整个审核回滚。

## 目录

| 层 | 文件 | 说明 |
| --- | --- | --- |
| controller | `review_controller.py` | `POST /api/review/declarations/query`、`POST /api/review/declarations/{id}/approve` |
| service | `review_service.py` | 列表编排；审核确认（账户锁、摘要核对、写记录与行、发布事件） |
| dao | `review_record_dao.py` | 有效审核查询（可加锁）、版本号、替代、写入、历史 |
| | `review_line_dao.py` | 冻结行写入与读取 |
| entity | `record.py`、`line.py` | 与迁移 `0001_baseline` 一致（`test_schema_entities.py` 比对） |
| dto | `review_dto.py` | 列表查询（每页最多 50）、审核请求（`contentSha256` 为 64 位十六进制，备注最多 300 字） |
| vo | `review_vo.py` | 报关单、报关行、子采购行、审核状态、列表 |
| mapper | `declaration_mapper.py` | source 内容 → 页面 VO；source 内容 → 冻结行与事件行 |
| policy | `review_policy.py` | 审核状态判定、不可审核原因、状态文案 |

## 审核规则

| 状态 | 条件 | 能否审核 |
| --- | --- | --- |
| `blocked` 不可审核 | 报关单没有关联的子采购单 | 否 |
| `pending` 待审核 | 未审核，或有效审核的内容摘要与当前来源不一致（显示"来源已变化"提示） | 是 |
| `approved` 审核通过 | 有效审核的内容摘要与当前来源一致 | 否（查看记录） |

- 页面提交打开时看到的 `contentSha256`。确认时在 source 的同步账户锁内、同一事务中重读来源并重算摘要；与页面不一致或与已保存摘要不一致时返回 409，要求刷新后重新核对。
- 同一内容重复提交返回已有结果，不新增记录、不重复发布事件。
- 来源变化后重新审核：旧记录置为 `superseded`，新记录版本号加 1，事件携带 `superseded_review_id` 供订阅方处理旧任务。
- 冻结范围是关联子采购单的全部有效行（开票按子采购行）；已定位的报关行 ID 一并保存。来源金额缺失的行照常冻结、金额为空，后续只能人工按差异结束。
- 服务身份（`service:` 前缀）只读，审核返回 403；操作者取自认证身份。
- 数据库提交结果不确定时返回 503，提示刷新后查看；同一内容重复提交不会重复审核。

## 公开接口（`public.py`）

- `ReviewApproved`：`review_id`、`superseded_review_id`、`ns_account`、`customs_declaration_id`、`record_no`、`revision`、`approved_by`、`lines`。
- `ApprovedLine`：`review_line_id`、`purchase_order_id`、`purchase_line_id`、`supplier_id`、`company_id`、`order_no`、`currency`、`quantity`、`unit`、`amount`（金额与数量为 Decimal）。

## 依赖

只通过 `backend.modules.source.public` 读取来源：`DeclarationService`（索引、分页内容、账户锁）、`snapshot`、`digest`。不读写 source 的 DAO 或表。

## 过渡期

- 旧 `reconciliation` 模块的审核接口与旧表仍保留，前端已不再调用；第 4e 步删除。
- 自第 4c 步起，`app.py` 登记 task 模块订阅 `ReviewApproved`，审核通过即生成开票任务。review 不读取 task，响应中不返回任务数。
- 历史审核数据不迁移，新链路需重新审核。

## 验证

`backend/tests/test_review.py`（SQLite，source 真实保存合成 NS 数据）：状态与计数、筛选分页、冻结行与事件、幂等、过期页面、来源变化重审、不可审核、服务身份、订阅方失败回滚、HTTP 校验。账户锁与并发须在 MySQL 上验证。

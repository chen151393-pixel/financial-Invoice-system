# review 模块：财务核对

架构 v2 第 4b 步新建。财务按 source 模块已保存的报关单与关联子采购明细整单审核；审核通过后保存审核记录，冻结开票口径的审核行，并发布 `ReviewApproved` 事件。表结构见[数据库设计](../../../docs/architecture/database.md)（`review_records`、`review_lines`）。

4d 已增加 `review_purchase_bases`、只读门面 `current_bases` / `basis_versions` 和 `PurchaseBasisInvalidated`。按全局子采购行冻结依据，同内容复用，来源关键变化重审；所有受影响报关记录进入待审核。

异常币种在财务核对时凭合同或结算证据核实，币种、证据引用、来源摘要、操作者和时间随新审核版本保存；普通有母单子采购自动继承，无需逐票选择。人工核实不改 source / NS。已有缺币种审核不能原地补写；母单读取失败应先重试。`ReviewApproved` 已携带依据 ID，matching 通过公开门面在确认事务中验证当前依据。

## 职责

- 报关单列表：关键字、账套、供应商、审核状态筛选与分页，状态计数与供应商选项在后端完成。
- 整单审核：财务人工确认，不调整金额；来源变化后要求重新审核，历史审核保留。
- 批量审核（2026-10-22）：一次最多 50 张（一页），逐张走与单张相同的锁内复核和事务，被拒绝的逐张返回原因。
- 冻结开票口径：子采购行的采购数量、采购单位、含税金额（来源缺失时为空）。
- 发布 `ReviewApproved`：订阅方 task 模块（第 4c 步接入）在同一事务中生成开票任务；订阅方失败时整个审核回滚。

## 目录

| 层 | 文件 | 说明 |
| --- | --- | --- |
| controller | `review_controller.py` | `POST /api/review/declarations/query`、`POST /api/review/declarations/approve-batch`、`POST /api/review/declarations/{id}/approve` |
| service | `review_service.py` | 列表编排；审核确认（账户锁、摘要与出库准入核对、写记录与行、发布事件）；批量审核逐张调用 |
| dao | `review_record_dao.py` | 有效审核查询（可加锁）、版本号、替代、写入、历史 |
| | `review_line_dao.py` | 冻结行写入与读取 |
| entity | `record.py`、`line.py` | 与迁移 `0001_baseline` 一致（`test_schema_entities.py` 比对） |
| dto | `review_dto.py` | 列表查询（每页最多 50，`supplierId` 为数字 ID）、审核请求（`contentSha256` 为 64 位十六进制，备注最多 300 字）、批量审核请求（1–50 张，ID 不重复） |
| vo | `review_vo.py` | 报关单、报关行、子采购行、审核状态、列表（含供应商选项）、批量审核结果 |
| mapper | `declaration_mapper.py` | source 内容 → 页面 VO；source 内容 → 冻结行与事件行 |
| policy | `review_policy.py` | 审核状态判定、不能审核原因、状态文案；出库准入规则本身在 source `admission_policy.py` |

## 审核规则

| 状态 | 条件 | 能否审核 |
| --- | --- | --- |
| `unshipped` 未出库 | 未审核通过，且报关单缺少真实报关单号或没有关联的子采购单。2026-10-23 起这类报关单拉取时即跳过，只有库中遗留旧数据会落到此状态 | 否（列表不显示） |
| `pending` 待审核 | 已出库且未审核，或有效审核的内容摘要与当前来源不一致、依据待复核（显示"来源已变化"提示） | 是 |
| `approved` 审核通过 | 有效审核的内容摘要与当前来源一致，且依据无需复核 | 否（查看记录） |

- 列表"全部"只含待审核与审核通过；未出库的旧数据不显示、不计数，也不进入工作台待办，审核时返回 409 及原因。列表筛选只有 all / pending / approved。
- 批量审核：逐张提交页面所见的 `contentSha256`；来源已变化、未出库、报关单不存在的计入 `skipped` 并返回原因，其余照常审核。数据库不可用（503）时停止后续，已完成的照常生效，页面重新读取。需要人工币种证据的报关单仍走单张审核。

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

## 4e 切换

- 旧 `reconciliation` 审核实现与接口已删除，数据库旧表仍保留。
- 自第 4c 步起，`app.py` 登记 task 模块订阅 `ReviewApproved`，审核通过即生成开票任务。review 不读取 task，响应中不返回任务数。
- 旧模块历史审核不迁移；既有 v2 审核按迁移保留冻结值并补记依据，证据不可还原时待复核。

## 验证

`backend/tests/test_review.py`（SQLite，source 真实保存合成 NS 数据）：状态与计数、筛选分页、未出库旧数据不显示且拒绝审核、供应商筛选与选项、批量审核部分通过与幂等、冻结行与事件、幂等、过期页面、来源变化重审、服务身份、订阅方失败回滚、HTTP 校验。账户锁与并发须在 MySQL 上验证。

## 币种核实接口

审核请求可带 `currencyEvidence: [{purchaseOrderId, currency, reference, note}]`。币种使用三位大写代码，证据引用和说明非空。同一订单全部审核行使用同一证据；已有来源币种或母单尚未读取时拒绝人工覆盖。原子冻结时保存认证身份、时间和来源摘要，相同证据重试不追加审核。

`purchase_basis_service.py` 负责冻结/失效，`basis_reader.py` 供调用方核对当前来源，`purchase_basis_dao.py` 只操作 review 表。迁移 `0006` 为既有审核复制原冻结值，不能恢复的来源证据标待复核。

## 单位名称展示（2026-10-16）

财务核对响应中的报关单位、子采购单位及报关数量说明通过 source 只读门面解析为单位名称，仅影响展示，不修改原始编号、数量金额或审核／比对结论。字典缺失、停用及未知编号保留原值，规则与兼容表归属见 [source 单位说明](../source/README.md)；验证见 `backend/tests/test_unit_display.py`。

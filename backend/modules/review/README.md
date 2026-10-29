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

- 列表计数 `counts` 另含 `changed`（待审核中来源已变化、需重新核对的张数）与 `approvedThisMonth`（北京时间本月审核通过的张数，按有效审核记录的 `approved_at`），供页面概况卡展示；随关键字、供应商条件变化。
- 申报幅度提醒与可自动审核预判（2026-10-27，`policy/auto_review_policy.py`）：任一报关行采购单价超出人民币报关单价容差时 `marginAlert` 为真；待审核、来源未变化、子采购行全部有行级关联、含税金额齐全、币种已确定、每条报关行申报幅度都已算出且未超出容差时 `autoReview.eligible` 为真，否则返回原因。只用于提示、计数（`counts.marginAlert`、`counts.autoApprovable`）与筛选（`status=margin_alert` / `auto`），不自动写入审核结果；供应商白名单待业务确认。NS 同步与审核提交后在后台计算并存库；列表仅读取结果，按数据库条件统计与分页，详见下文。
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

## 对照表展示字段（2026-10-26）

子采购行及合并行新增 `salesOrderExchangeRate`：读取该子采购单通过 `sales_order_id` 关联的已同步销售订单汇率，以十进制字符串返回，保留有效小数；未关联销售订单、尚未同步或汇率为空时返回空字符串。不借用母采购单汇率，不参与审核冻结、内容摘要或金额重算，无需数据库迁移。

`POST /api/review/declarations/query` 的报关单新增 `salesOrders`（来源报关行销售单号，按出现顺序去重拼接）；`company` 继续作为主行申报抬头。报关行新增 `originPlace`（境内货源地，来源 `custrecord_swc_goods_place`）、`parent`（该报关明细自身的采购订单编号 `custrecord_swc_purachse_no`，由 source 从已保存原始记录补充）。引用显示名称，不把内部 ID 当作单号；缺失返回空字符串，不借用关联子采购的母单号、不推断销售关系、不计算金额、不修改冻结依据或内容摘要。

## 申报幅度（2026-10-23）

报关行响应包含 `margin`（如 `5.63%`）、`marginStatus`（ok / negative / unavailable）、`marginNote`、`declaredUnitPriceCny`（人民币报关单价）、`combinedPurchaseUnitPrice`（兼容字段名，现为采购含税金额折算的报关单价），规则在 `policy/margin_policy.py`。新单价字段替代原总金额展示字段 `declaredCny`、`purchaseTotal`，前端同步更新。

2026-10-26 按用户确认改为单价口径：人民币报关单价 = 报关单价 × 对应销售单汇率（人民币不换算）；采购金额折算报关单价 = 该报关行关联采购行的含税总金额 ÷ 总报关数量；申报幅度 =（人民币报关单价 − 采购金额折算报关单价）÷ 人民币报关单价 × 100%。不平均采购行单价，不用报关总金额代替报关单价。单位缺失／不一致、采购币种非人民币、金额数量或单价汇率缺失、任一子采购报关数量或报关单价非正数时不计算并写明原因。

比较与计算使用未舍入的 Decimal；人民币单价展示最多六位小数，幅度两位小数。2026-10-27 按用户确认增加固定人民币单价容差：`REVIEW_UNIT_PRICE_TOLERANCE_CNY` 默认 `0.10` 元/单位，允许非负金额（最多两位小数），设为 `0` 关闭容差，修改后重启后端自动排队重算，完成后生效。仅当“采购金额折算报关单价 − 人民币报关单价”大于容差时状态为 `negative`；大于 0 且不超过容差（含边界）时返回 `ok`，`marginNote` 显示“精度范围内一致”、实际单价差额与容差。差额按未舍入值判断，不把 0.100001 舍入为 0.10 后放行；真实幅度仍保留，正常状态下可显示负幅度。容差为固定人民币金额，不叠加 0.005 × 汇率的动态容差，也不是报关总额容差。缺汇率等无法计算的状态保持 `unavailable`。无需数据库迁移。汇率不参与内容摘要，变化不触发重审；发票比对的既有金额／单价校验保持原口径。

2026-10-28 按用户确认改为报关口径：报关行与子采购行的单位比较使用**报关单位** `declared_unit`（NS `custrecord_swc_delare_unit`）；报关单价使用**申报单价** `declared_unit_price`（NS `custrecord_swc_grossamountzj`，与报关数量、报关单位配套，同 NS 报关单打印口径），不再使用 `unit`（`custrecord_swc_unit`）与 `unit_price`（`custrecord_swc_unitprice`）。报关行展示的数量、单位、单价同为这一套，页面与计算一致。NS 未填申报单价（2026-08-17 前的报关行）时按报关金额 ÷ 报关数量试算（source `declared_unit_price`），报关行单价旁显示“试算”徽标、幅度说明中注明“（试算）”，接口字段 `priceEstimated`；报关金额或报关数量也缺失时显示“申报单价缺失，且报关金额或报关数量缺失，无法试算”，不按 0 计算。计算版本升为 `review-v4`，启动后自动重算快照。申报单价不参与内容摘要（已审核报关单不因本次改动需要重审）。

同一报关行内，子采购单号、供应商、品名、单位一致的采购行合并展示；币种、母单、数量口径也必须一致，关键字段缺失时不合并。`purchase_display_policy.py` 分别汇总报关数量、采购数量及含税金额。数量列显示总报关数量；单行采购单价直接取来源 `unit_price`（含税），合并采购单价为总含税金额 / 总采购数量（展示两位小数），按采购单位标注。不同采购单位不合并。合并行 `members` 保留原始明细，原始行数统计、申报幅度计算、审核冻结均继续使用原始行。金额或数量缺失时不显示部分合计冒充总额；总数量非正数时不计算单价。

## 后台计算与数据库分页（2026-10-27）

迁移 `0032_review_calculations` 新增本模块的三个查询投影表，保留已有来源、审核和冻结记录：

| 表 | 用途 |
| --- | --- |
| `review_calculation_jobs` | 每个 NS 账套一条持久任务；请求代次、已完成代次、算法及容差版本、失败原因与退避时间 |
| `review_declaration_snapshots` | 每张有效且已出库报关单一条快照；审核状态、来源变化、审核时间、幅度异常、自动审核预判与搜索字段。`payload` JSON 保存完整展示数据、每条报关行的幅度／状态／原因／人民币报关单价／合并采购单价及销售汇率，金额为十进制字符串 |
| `review_snapshot_suppliers` | 快照关联供应商，用于数据库筛选和下拉选项 |

- `app.py` 将 `SourceChanged`、`ReviewApproved` 订阅到 `calculation_service.request_calculation`，与来源／审核事务一起提交队列，不在同步请求中计算。账套内所有报关单一起重建，保证一个销售订单汇率影响的其他报关单、关联改挂、失效与人工币种依据变化均被覆盖；连续同步请求按账套合并。
- `CalculationWorker` 每两秒检查持久队列，MySQL 命名锁保证多进程仅一个后台消费者。读取来源与 Decimal 计算在写事务外完成，复用 `declaration_mapper`、`margin_policy`、`auto_review_policy`；短事务取得队列行锁，核对代次和算法版本后原子替换整个账套快照。计算期间再次同步／审核时，旧结果丢弃，新请求仍待处理。
- 账本锁被其他写入占用（`ApiError.code == "ledger_busy"`）不算计算失败：只把重试推迟 5 秒，不增加失败次数、不写失败原因，页面仍显示“后台计算中”。失败与推迟记录只更新本模块的队列行，不取账本锁，保证账本长时间繁忙时也能记下，后台线程不会每两秒整账套重算。
- 失败记录中文原因并以 2—256 秒退避自动重试；进程重启继续未完成任务。启动时发现未建立快照的账套或算法／`REVIEW_UNIT_PRICE_TOLERANCE_CNY` 变化即排队。缺少汇率、金额或单位等属于已完成计算的 `unavailable`，保留具体原因，不当作零或系统失败。
- `ReviewService.browse` 委托 `review_query_service.py`；`dao/declaration_snapshot_dao.py` 只查 review 表，使用 SQL 聚合计数、供应商子查询、关键字过滤、`ORDER BY declaration_date DESC, customs_declaration_id DESC LIMIT ... OFFSET ...`。每次列表共四条查询，不访问 source 原始 JSON、不组装全量来源、不重算幅度；每月审核数量仍按请求当时的北京时间自然月计算，跨月无需重建。
- 接口仍为 `POST /api/review/declarations/query`。新增单据字段 `calculationStatus`（ready / pending / failed）、`calculatedAt`（最近完成计算的 UTC 时间）。更新中／失败时 `notices` 明确提示，暂展示上次完成的单据快照与状态统计；旧幅度与自动审核结论隐藏，审核按钮关闭，该账套暂不进入异常／自动审核计数和筛选。首次补算完成前单据尚不显示；完成后刷新列表。
- 审核接口继续在来源锁内实时重读摘要和冻结依据。缓存只为查询提速，不代替审核校验，也不自动批准任何单据。审核接口返回当前单据时可复用原计算规则，列表请求始终只查库。
- 兼容单位字典或来源数据通过外部维护脚本直接修改、未发布事件的情况：执行下列补算命令刷新；新来源写入口必须发布 `SourceChanged`。算法或快照结构变化时提升 `policy/calculation_policy.py` 中的版本。

部署顺序（应停止旧版后端后升级，再启动新版后台消费者）：

```powershell
npm.cmd run db:upgrade
node scripts/python.mjs -m backend.manage rebuild-review
npm.cmd run dev:api
```

`rebuild-review` 从本地已入库来源与审核依据重建所有账套，可重复执行；不请求 NS、不写审核记录。错误会使命令失败并保留队列，不能将部分完成报告为补算成功。升级后直接启动新版服务也会后台补算已有数据；数据量大时可先运行管理命令，完成后再开放查询。

验证：`test_review_calculations.py` 覆盖持久队列、初始补算、四条 SQL 分页、脏快照限制、事务回滚、失败重试、规则变化、审批更新、共享销售汇率及缺汇率。`test_review_calculations_mysql.py` 在随机隔离库验证新旧代次并发和单消费者命名锁；未提供专用 MySQL 连接时明确跳过。既有业务测试通过 `review_helpers.MaterializedReviewService` 显式模拟后台已完成，再调用真实数据库分页。

## 分字段批量搜索（2026-10-28）

`POST /api/review/declarations/query` 新增 `supplierName`、`recordNo`、`purchaseOrderNo` 字符串，分别匹配供应商名称、CD 编号和子采购单号。每框支持单条或用中英文逗号、分号、换行分隔的多条内容；忽略空项、去重，最多 50 条，每条最多 120 字符，保留词内空格。框内取任一部分匹配，框间同时满足；`%`、`_` 按普通字符查询。旧 `keyword`、`supplierId` 仍兼容原调用。

所有条件在 review 快照 SQL 中过滤，列表、分页和概况计数使用同一范围，不读取实时 source。v3 查询投影新增响应字段 `purchaseOrderNumbers`，包含全部关联子单号（含无明细子单），启动时自动补算旧投影；补算期间显示现有后台计算状态，并兼容旧快照中的子单展示字段。无需数据库迁移，不触发 NS 写入。

## 子采购数量与单价分别注明口径（2026-10-29）

- 对照表 `quantity` / `unit` 取子采购行自身 `declared_quantity` / `declared_unit`；不借报关主行数量、不回退采购数量。`scope=declared` 表示数量口径。
- `price` 单行直接取 NS 含税单价 `unit_price`；`purchaseQuantity` / `purchaseUnit` 返回原采购数量、单位。合并价格 = 含税总金额 / 总采购数量，界面单价旁标注采购单位。来源单价缺失保持空值。
- 申报幅度另按采购含税总金额 / 子采购总报关数量折算，与人民币申报单价按同报关单位比较。响应沿用 `combinedPurchaseUnitPrice` 字段，界面明确显示“采购金额折算报关单价”，不将它称为原采购单价。缺报关单位、数量、金额或任一报关数量非正数时不计算。
- 例：冷裱膜展示 1525 平方米、采购含税单价 81.13 元/卷、金额 8113 元；供幅度比较的折算报关单价为 5.32 元/平方米。PVC 膜合并展示 1220 平方米、采购含税单价约 230.66 元/卷；折算报关单价为 18452.6 / 1220。
- 开票依据仍冻结原采购数量、单位和含税金额；行级关联仍依来源身份。计算版本 `review-v5` 启动自动补算旧快照，无需迁移、不改审核记录。
- 回归：`test_review_declared_purchase.py`、`test_review_purchase_groups.py`、`test_declared_price.py` 和前端 `pl-comparison.test.mjs`。

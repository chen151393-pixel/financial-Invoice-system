# review 模块：财务核对

架构 v2 第 4b 步新建。财务按 source 模块已保存的报关单与关联子采购明细整单审核；审核通过后保存审核记录，冻结开票口径的审核行，并发布 `ReviewApproved` 事件。表结构见[数据库设计](../../../docs/architecture/database.md)（`review_records`、`review_lines`）。

4d 已增加 `review_purchase_bases`、只读门面 `current_bases` / `basis_versions` 和 `PurchaseBasisInvalidated`。按全局子采购行冻结依据，同内容复用，来源关键变化重审；所有受影响报关记录进入待审核。

异常币种在财务核对时凭合同或结算证据核实，币种、证据引用、来源摘要、操作者和时间随新审核版本保存；普通有母单子采购自动继承，无需逐票选择。人工核实不改 source / NS。已有缺币种审核不能原地补写；母单读取失败应先重试。`ReviewApproved` 已携带依据 ID，matching 通过公开门面在确认事务中验证当前依据。

## 职责

报关单列表支持 `createdFrom` / `createdTo`（`YYYY-MM-DD`，默认 `null`）：须同时填写，开始日期不能晚于结束日期。按 source 的 `ns_created_at` 换算北京时间，包含起止两天；有日期条件时排除创建时间缺失的单据，不使用申报日期或本地入库时间替代。通过 source 公开门面在同一只读事务内获取 ID，review DAO 再统一筛选列表、状态计数和分页；未填写时沿用快照查询，无数据库迁移。

- 报关单列表：关键字、账套、供应商、审核状态筛选与分页，状态计数与供应商选项在后端完成。
- 整单审核：财务人工确认，不调整金额；来源变化后要求重新审核，历史审核保留。
- 批量审核（2026-10-22）：一次最多 50 张（一页），逐张走与单张相同的锁内复核和事务，被拒绝的逐张返回原因。
- 冻结开票口径：子采购行的采购数量、采购单位、含税金额（来源缺失时为空）。
- 财务通过发布 `ReviewApproved`；两项当前版本均通过后发布 `InvoiceReady`，task 在同一事务中生成开票任务；订阅方失败时最后一项审核及放行一起回滚。

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
- `status=customs_approved` / `counts.customsApproved` 按当前有效海关审核筛选与计数，不限制财务审核状态。先由 review DAO 读取匹配当前回执版本及摘要的审核引用，再经 source 门面核实真实报关单号唯一、来源 ID 与当前摘要一致；回执换版、来源变化、重号均不计入。ID 条件与其他查询条件一起在数据库聚合、筛选和分页，不对当前页做过滤，无数据库迁移。
- 申报幅度提醒与可自动审核预判（2026-10-27，`policy/auto_review_policy.py`）：任一报关行的关联采购未税单价（按真实税率逐行还原未税金额，合计除以下单数量合计）超出人民币报关单价容差时 `marginAlert` 为真；待审核、来源未变化、子采购行全部有行级关联、含税金额齐全、币种已确定、每条报关行申报幅度都已算出且未超出容差时 `autoReview.eligible` 为真，否则返回原因。只用于提示、计数（`counts.marginAlert`、`counts.autoApprovable`）与筛选（`status=margin_alert` / `auto`），不自动写入审核结果；供应商白名单待业务确认。NS 同步与审核提交后在后台计算并存库；列表仅读取结果，按数据库条件统计与分页，详见下文。
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
- `app.py` 登记 task 模块订阅 `InvoiceReady`，海关与财务均审核通过才生成开票任务。review 不读取 task，响应中不返回任务数。
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


## 采购未税 USD 单价与申报幅度（2026-11-19）

财务核对不再取报关行 `unit_price` 作为采购单价。`policy/purchase_price_policy.py` 使用当前报关行明确关联的原始采购明细：逐行按已同步的真实税率将含税金额还原为未税金额（采购原币保留两位小数、四舍五入），汇总后除以这些明细的**采购下单数量 `quantity` 合计**，再按对应销售单汇率折为 USD。不使用报关数量、展示合并行、采购行原单价或整单单头金额，不固定除以 1.13。

- 分母始终是采购下单数量，采购单位与报关单位变化不改变采购单价；一张采购单涉及多个报关行时，只取明确归属当前行的采购明细。相同采购行重复关联去重；同一采购行同时归属多个报关行、没有明确份额时列入未关联，不任选一行或重复计价。
- 未税金额先在各行采购原币下还原，再统一为人民币汇总。人民币采购按销售汇率除为 USD；USD 采购直接使用其美元未税金额（参与人民币汇总时乘同一销售汇率）；其他或待核实币种明确阻止计算。人工核实币种使用当前有效开票依据中的币种。
- 2026-11-25：明确返回的零金额明细按未税金额零参与合计，其采购下单数量仍计入分母；全部明细金额为零时采购未税单价为零，其他口径校验通过且申报单价为正时幅度为 100%。NULL 金额与负金额继续阻止计算，零金额不代表税率、币种或数量已核实，不能跳过这些校验。
- 销售单仅从当前行关联子采购的 `sales_order_id` 候选中，按报关行完整销售单号唯一匹配。币种须为 USD、汇率须为正数；不借用其他销售单汇率。缺金额、税率、有效下单数量或销售汇率时返回具体原因，不回退报关行采购价，也不把缺失税率视为 13% 或零。
- 例：CD000962 铝运动水壶，含税金额 68400、38400 元，税率均 13%，逐行未税金额 60530.97、33982.30 元；采购数量 9000、6000 个；销售汇率 6.70。USD 单价 = 94513.27 ÷ 15000 ÷ 6.70 = 0.940430547…，响应展示最多六位小数 `0.940431`。
- 采购单价独立于幅度校验。申报幅度比较每条关联子采购明细对应的母采购原生行单位与报关单位，母采购行按母单 NS ID、原生行号、货品 ID 唯一定位；使用 source 返回的 `parent_purchase_unit` 明确名称，报关单位通过既有字典解析。母采购单位不同使用 `unit_mismatch`；缺母单、对应行或单位名称返回 `unavailable` 及具体补同步原因。两种状态下幅度为“—”，不允许自动审核，采购 USD 价可独立展示。报关数量继续与关联子采购报关数量合计核对，数量不符使用 `quantity_mismatch`。报关行原始 `unit`、`quantity` 保留供追溯，原始口径差异不再阻止幅度计算。
- 申报价仍取 `declared_unit_price`，未填时复用 source 的报关金额 ÷ 报关数量试算。幅度 =（人民币申报单价 − 人民币采购未税单价）÷ 人民币申报单价 × 100%。沿用未舍入人民币差额和 `REVIEW_UNIT_PRICE_TOLERANCE_CNY`（默认 0.10 元）判断异常，不能按页面显示精度放行。
- 开票审核冻结继续使用采购下单数量、单位、含税金额；本次不改开票依据、审核历史或 NS 来源原文。

`POST /api/review/declarations/query` 及审核返回的报关行新增：`purchaseUnitPriceUsd`（采购未税 USD 单价）、`declaredUnitPriceUsd`（申报 USD 单价）、`purchaseOrderQuantity`（关联采购下单数量合计）、`purchasePriceNote`（取价口径或无法计算原因）。均由后端计算为十进制字符串，前端不计算。`originalPrice` 兼容字段为同一采购未税 USD 单价，`originalPriceUnit` 显示对应母采购明细单位，多个不同母采购单位按出现顺序去重展示；`originalQuantity` 仍保留报关行原始数量。`originalUnitPriceCny` 返回新采购未税人民币比较价，旧 `combinedPurchaseUnitPrice` 仅作旧快照读取别名。

算法版本为 `review-v17`，部署重启自动从本地来源重建快照，更新旧子采购单位校验及原始口径校验的结果。补算中隐藏旧采购单价、幅度及自动审核结果；也可执行 `node scripts/python.mjs -m backend.manage rebuild-review`。无需新增迁移。母采购证据只有 `units` 编号且缺少明确单位名称时，需重新同步报关单或关联子采购单以补齐 `parentLines.unitname`。历史采购未同步税率的，先在 `NETSUITE_PL_LOOKUP.purchase_line.storage_fields` 配置 `tax_rate`（NS `custrecord_swc_subpo_item_tax`）并重新同步；补齐前如实显示无法计算，不伪造成功。

2026-11-25 零金额修正将当前算法版本提升至 `review-v19`，保留 v18 的海关回执结论刷新行为。部署重启后自动补算已有来源，清除零金额行造成的旧不可计算结果；也可使用上面的 `rebuild-review` 命令。无需重新同步 NS 或改写来源、审核及开票冻结记录。

验证：`test_review_purchase_price.py`、`test_review_declared_purchase.py`、`test_review_tolerance.py`、`test_review_calculations.py`、`test_review_original_caliber.py`、`test_declared_price.py` 和前端 `pl-comparison.test.mjs`。

## 后台计算与数据库分页（2026-10-27）

迁移 `0032_review_calculations` 新增本模块的三个查询投影表，保留已有来源、审核和冻结记录：

| 表 | 用途 |
| --- | --- |
| `review_calculation_jobs` | 每个 NS 账套一条持久任务；请求代次、已完成代次、算法及容差版本、失败原因与退避时间 |
| `review_declaration_snapshots` | 每张有效且已出库报关单一条快照；审核状态、来源变化、审核时间、幅度异常、自动审核预判与搜索字段。`payload` JSON 保存完整展示数据、每条报关行的幅度／状态／原因／人民币报关单价／报关行单价及销售汇率，金额为十进制字符串 |
| `review_snapshot_suppliers` | 快照关联供应商，用于数据库筛选和下拉选项 |

- `app.py` 将 `SourceChanged`、`ReviewApproved` 订阅到 `calculation_service.request_calculation`，与来源／审核事务一起提交队列，不在同步请求中计算。账套内所有报关单一起重建，保证一个销售订单汇率影响的其他报关单、关联改挂、失效与人工币种依据变化均被覆盖；连续同步请求按账套合并。
- `CalculationWorker` 每两秒检查持久队列，MySQL 命名锁保证多进程仅一个后台消费者。读取来源与 Decimal 计算在写事务外完成，复用 `declaration_mapper`、`margin_policy`、`auto_review_policy`；短事务取得队列行锁，核对代次和算法版本后原子替换整个账套快照。计算期间再次同步／审核时，旧结果丢弃，新请求仍待处理。
- 账本锁被其他写入占用（`ApiError.code == "ledger_busy"`）或行锁等待超时／死锁（`lock_conflict`）不算计算失败：只把重试推迟 5 秒，不增加失败次数、不写失败原因，页面仍显示“后台计算中”。失败与推迟记录只更新本模块的队列行，不取账本锁，保证账本长时间繁忙时也能记下，后台线程不会每两秒整账套重算。
- 失败记录中文原因并以 2—256 秒退避自动重试；进程重启继续未完成任务。启动时发现未建立快照的账套或算法／`REVIEW_UNIT_PRICE_TOLERANCE_CNY` 变化即排队。缺少汇率、金额或单位等属于已完成计算的 `unavailable`，保留具体原因，不当作零或系统失败。
- `ReviewService.browse` 委托 `review_query_service.py`；`dao/declaration_snapshot_dao.py` 只查 review 表，使用 SQL 聚合计数、供应商子查询、关键字过滤、`ORDER BY declaration_date DESC, customs_declaration_id DESC LIMIT ... OFFSET ...`。快照查询为四条 SQL；服务另读取当前海关审核引用并通过 source 门面批量核实单头，分页后汇总双审进度。不访问 source 原始 JSON、不组装全量来源、不重算幅度；每月审核数量仍按请求当时的北京时间自然月计算，跨月无需重建。
- 接口仍为 `POST /api/review/declarations/query`。新增单据字段 `calculationStatus`（ready / pending / failed）、`calculatedAt`（最近完成计算的 UTC 时间）。更新中／失败时 `notices` 明确提示，暂展示上次完成的单据快照与状态统计；旧幅度与自动审核结论隐藏，审核按钮关闭，该账套暂不进入异常／自动审核计数和筛选。首次补算完成前单据尚不显示；完成后刷新列表。
- 查询返回的 `review.reviewedByName` 通过 `identity.public.actor_names` 按页批量解析。飞书账号取本地人员目录姓名（含已停用人员），系统身份显示“系统”，无法解析时返回原标识，没有审核人时返回 `null`。历史快照读取时即可补充姓名，`review.reviewedBy` 仍保存原操作者标识。
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

## 单位不一致快捷筛选（2026-11-10）

`POST /api/review/declarations/query` 支持 `status=unit_mismatch` 和 `counts.unitMismatch`：筛选至少一条报关行 `marginStatus=unit_mismatch` 的待审核报关单，按整单计数，多条异常行不重复累计。`status=margin_alert` / `counts.marginAlert` 独立筛选至少一条报关行 `marginStatus=negative` 的单据；只有单位或数量不一致不进入申报幅度异常。同单不同明细存在两类问题时同时进入对应分类，不能用两个卡片数字相加作为异常总数。

复用当前快照 JSON，在数据库中按逐行状态筛选、计数后分页，不依赖旧快照混合分类的 `margin_alert` 列。响应按已有逐行结果归类 `marginAlert`、`unitMismatch`、`quantityMismatch`，兼容未保存新标记的旧快照；不重算金额，不改变自动审核条件。叠加现有查询条件，过期或计算失败的快照仍排除，主行分类标记一并清空。无需迁移、补算或重新拉取 NS；重启更新后的后端并刷新页面即可使用。回归见 `test_review_unit_filter.py`（SQLite 与可选隔离 MySQL）。

## 真实报关单号筛选（2026-11-09）

`POST /api/review/declarations/query` 新增 `declarationNo`，按快照中的真实海关报关单号（NS `custrecord_swc_realno`，响应字段 `declaration`）部分匹配，与 CD 编号 `recordNo` 是不同字段。多条输入、去重、上限与 `%`、`_` 按普通字符的规则同下文；与其他框同时满足。只读快照，不查询实时来源，无迁移。验证见 `test_review_calculations.py::test_split_bulk_search_uses_snapshot_fields_and_filtered_counts`。

## 分字段批量搜索（2026-10-28）

`POST /api/review/declarations/query` 新增 `supplierName`、`recordNo`、`purchaseOrderNo` 字符串，分别匹配供应商名称、CD 编号和子采购单号。每框支持单条或用中英文逗号、分号、换行分隔的多条内容；忽略空项、去重，最多 50 条，每条最多 120 字符，保留词内空格。框内取任一部分匹配，框间同时满足；`%`、`_` 按普通字符查询。旧 `keyword`、`supplierId` 仍兼容原调用。

`declarantName` 按报关单主行的申报抬头搜索，匹配已有快照的 `company` 字段，沿用上述批量搜索规则。在数据库聚合和分页前应用条件，列表、审核状态计数及概况卡使用相同范围。

所有条件在 review 快照 SQL 中过滤，列表、分页和概况计数使用同一范围，不读取实时 source。v3 查询投影新增响应字段 `purchaseOrderNumbers`，包含全部关联子单号（含无明细子单），启动时自动补算旧投影；补算期间显示现有后台计算状态，并兼容旧快照中的子单展示字段。无需数据库迁移，不触发 NS 写入。

## 子采购展示数量与单价口径（2026-11-09 更新）

- 对照表 `quantity` / `unit` 取子采购行自身 `declared_quantity` / `declared_unit`；不借报关主行数量、不回退采购数量。`scope=declared` 表示数量口径。
- `price` = 本行含税金额 / 本行展示的报关数量；合并行先汇总金额和报关数量，再相除。四舍五入固定两位小数并保留尾零，单价旁标注报关单位。金额或报关数量缺失、数量非正数时返回空值，不回退 NS 原单价。`purchaseQuantity` / `purchaseUnit` 仍返回原采购数量、单位。
- 申报幅度按本页“采购未税 USD 单价与申报幅度”规则读取原始采购明细；展示合并只影响展开表，不改变价格分母。
- 例：242310.6 / 17687.33 = 13.699666…，显示 `13.70`；冷裱膜 8113 / 1525 显示 `5.32` 元/平方米；PVC 膜 18452.6 / 1220 显示 `15.13` 元/平方米。
- 开票依据仍冻结原采购数量、单位和含税金额；行级关联仍依来源身份。计算版本 `review-v10` 启动自动补算旧快照，无需迁移、不改审核记录。
- 回归：`test_review_declared_purchase.py`、`test_review_purchase_groups.py`、`test_declared_price.py` 和前端 `pl-comparison.test.mjs`。

## 数量校验与双单价规则（2026-10-30）

报关数量校验继续保留；采购取价及幅度校验以当前 `review-v17` 规则为准。审核冻结和子采购展示仍使用各自原有字段。

## 海关回执与报关单比对（2026-11-12）

财务导入单一窗口导出的海关回执，按出口报关单号对应 NS 报关单的真实报关单号（不是 CD 号），比对明细行的品名、单位与数量，并保存回执中的境外收货人。NS 报关单没有境外收货人字段，因此该字段只来自回执、不参与比对。

页面权限代码为 `customs-match`（独立于 `finance`）：`/api/review/customs-receipts` 下的接口由 identity 的 `api_page_policy` 按该页面授权。未保存配置的角色沿用升级前默认页面范围并自动包含本页；已保存过页面配置的角色需管理员在“人员与权限”中勾选“报关单比对”。

### 拥有的表

`review_customs_receipts`（每个报关单号一行：境外收货人、当前版本、比对结果、匹配到的 NS 报关单 ID）、`review_customs_receipt_lines`（按版本保留的海关明细）。迁移 `0042_review_customs_receipts`。

### 文件

| 层 | 文件 | 说明 |
| --- | --- | --- |
| controller | `customs_receipt_controller.py` | `POST /api/review/customs-receipts/import`、`/query`、`/rematch` |
| service | `customs_receipt_reader.py` | 后台读取 .xlsx / .xls / .csv；忽略 XLSX 尾部空白格式，拒绝公式与错误值，资源边界见下文 |
| | `customs_receipt_parser.py` | 表头别名识别（标题行可在前 10 行内）、逐行校验、按报关单号分组、内容摘要 |
| | `customs_receipt_service.py` | 导入（解析在事务外，保存/换版与比对在账本锁事务内）、列表、重新匹配（每批 200 张短事务） |
| policy | `customs_match_policy.py` | 比对规则（纯函数） |
| dao / entity | `customs_receipt_dao.py`、`customs_receipt.py` | 两张表的读写与定义 |
| dto / vo / mapper | `customs_receipt_dto.py`、`customs_receipt_vo.py`、`customs_receipt_mapper.py` | 请求、响应与行 → VO 转换 |

### 比对规则

1. 以出口报关单号查找 source 中有效的 NS 报关单：没有为 `ns_missing`，多张同号为 `ns_duplicate`，两者都不比对明细。
2. 同一报关单内，海关项与 NS 报关行按“规范化品名（`normalize_name`）+ 规范化单位”归组。优先将两侧各只出现一次的相同数量逐行配对，精确比较、不设容差。剩余行继续按数量合计作拆行或合并比对；余额只出现在一侧时，保留整个组进行原有比对。
3. 单位：海关取成交单位；NS 取报关单位（经单位字典显示名）。法定单位与数量只展示。品名相同但单位不同的剩余组为“单位不一致”，其余为“NS 无对应行”或“海关无对应项”。
4. 整单状态：全部一致为 `matched`，含拆行或合并为 `split_matched`，任一组不一致（含一对一行“总价不一致” `total_mismatch`）为 `different`。
5. 境外收货人：同一报关单内各项须一致（空值不比较），否则整份文件拒绝；匹配到 NS 报关单后状态为“已保存”，回执为空为“回执未提供”，未匹配为“待关联”。
6. 展开明细显示 NS 报关行原始金额和币种。品名与单位已配对的一对一同币种组按原金额精度比较，`totalMismatch` 为 true（不同）、false（相同）或 null（未比对）。主行 `totalComparison` 反映全部一致、有差异、部分未比对或未比对。拆行、合并逐行展示金额。2026-11-17 起总价参与准入：一对一行数量一致但总价不同，组状态为 `total_mismatch`（“总价不一致”），整单 `different`，见下文“自动审核一对一按行比价”。

### 导入与换版

2026-11-26：海关回执改为持久后台导入。`POST /api/review/customs-receipts/import` 接收原文件后返回 **202** 与 `pending` 作业，不表示已导入。`GET /api/review/customs-receipts/imports` 返回当前认证身份最近的作业和未完成状态；`pending` / `running` / `completed` / `failed` 分别表示排队、后台解析比对、入库成功、失败。失败原因持久保存；解析失败整份不入库，保存过程失败整份回滚。只有回执与作业结果在同一账本事务内提交后才显示成功。

- `service/customs_import_service.py` 复用原解析、换版、比对规则；`customs_import_worker.py` 通过 MySQL 命名锁单消费者按上传顺序处理。进程中断后接续 `pending` / `running`，不要求页面保持打开。
- `review_customs_import_jobs` 由迁移 `0057_review_customs_import_jobs` 创建。原文件暂存 `CUSTOMS_IMPORT_ROOT`（默认 `data/customs-imports`），文件名采用随机标识；完成或确认失败后清除暂存文件，数据库只保存元数据与结果。部署必须先升级数据库，并持久挂载该目录（默认已落在 Compose 的 `/app/data` 挂载内）。不执行线上迁移或补导入。
- 支持用户提供的 24 列单一窗口原表；表头仍按既有别名识别，不增加要求列。XLSX 不依赖声明尺寸，尾部空白行、列和仅有格式的单元格不算明细；公式、错误单元格及非空超限数据仍会明确失败。原 4MB 业务限制与遗漏的 128KB 请求拦截已移除；异步接口专用传输资源上限为原文件 64MiB、JSON 90MiB、解压 256MiB，最多 100000 项，不放大其他模块的限制。
- 上传/接收中断时显示“未确认成功”，查询进度失败提示先核实，不能据此宣称未入库或重复上传。后台明确失败时提示“本文件未导入，原有数据未被此文件替换”；关闭弹窗后页面继续显示未完成和失败记录并轮询，成功后自动刷新列表；已完成的绿色成功提示仅在导入弹窗展示，列表页刷新后不显示。

验证：新增 `backend/tests/test_customs_import_jobs.py` 覆盖排队不解析、后台完成、失败不替换、事务回滚、重启恢复、权限、超过旧限制的 HTTP 请求及空白格式。前端状态覆盖见 `frontend/tests/customs-import.test.mjs`。

- 同一文件按真实报关单号分组，组内按规范化项号去重。重复项的明细内容相同则保留首次出现的行，不同项号各自保留。`POST /api/review/customs-receipts/import` 返回的 `rows` 为去重后的明细行数。
- 一个文件内任一行有误（缺必需列、长号码被存为数字、同号同项的明细内容冲突、出口日期或境外收货人前后不一致、数值格式或精度超限）时整份拒绝。
- 同一报关单号再次导入：内容相同不换版，只刷新比对；内容变化时版本号加 1，新增一版明细，旧版本保留。
- 重新匹配只按当前 NS 报关单重算比对结果，不修改回执内容；不传 ID 时处理全部回执。
- 服务身份（`service:`）只读，导入与重新匹配返回 403。

### 依赖

经 `backend.modules.source.public.declarations_by_number(connection, numbers)` 在同一连接中只读 NS 报关单与报关行，不读写 source 的表。

### 验证

`backend/tests/test_customs_receipts.py`：比对规则（拆行、合并、单位/数量不一致、单边缺失、重号）、文件解析（xlsx 与带标题行的 GBK CSV、各类拒绝）、导入换版、列表筛选计数与重新匹配。MySQL 变体需提供 `BUSINESS_MIGRATION_TEST_SERVER_URL`，未配置时跳过。


## 海关审核与双审核开票门槛（2026-11-13，迁移 0044）

- `POST /api/review/customs-receipts/query` 支持 `status=approved`，响应新增 `counts.approved`，用于“已审核通过”概况卡与列表筛选。包含自动和人工海关审核，不要求财务审核已通过；仅统计当前回执版本、内容摘要与当前唯一有效 NS 来源及其摘要一致的记录。回执换版、NS 来源变化、停用或同号多单后不计入。统计随单号、商品名、收货人和出口日期条件变化；与现有概况卡一致，不受状态与差异类型选择影响，列表同时应用差异类型并在数据库分页。该分类与明细一致／有差异可重叠，不可直接相加。无需数据库迁移。
- 新增 `POST /api/review/customs-receipts/approve-batch`：`items` 为 1–50 个不重复的 `{id, token}`，`method` 为 `auto` 或 `manual`，`note` 最多 300 字。返回 `approved` / `skipped` 逐张结果及跳过原因；每张独立事务，数据库故障停止后续，部分已成功的保留。
- 列表每张新增 `approval`：`token`、`approved`、`label`、`allowed`、`autoAllowed`、`reason`、`approvedBy`、`approvedAt`、`note`。服务端按当前 NS 来源重新核对可操作性；比对状态筛选与概况仍基于最近导入/重新匹配保存的结果，来源修改后可使用“全部重新匹配”更新统计。
- 自动审核只放行逐行一一对应、数量一致且每行总价比对一致的回执（2026-11-17 起不再包含拆行/合并一致）。人工单张或批量审核允许已唯一匹配的差异单，说明选填（2026-11-17 起不再强制）；审核人、方式、时间写入审核记录留痕。未找到或重号的 NS 单据不可审核。操作者来自认证身份，服务身份只读。
- 提交在账本锁内重新比对，并核对回执版本、内容摘要、NS 身份与当前来源摘要。旧页面拒绝；重复提交同版本幂等。回执换版或来源变化后旧审核保留，当前版本重新待审核。
- `ReviewApproved` 继续表示财务通过并驱动快照计算、依据失效/承接；`task_release_service.py` 核实当前财务审核和海关审核，发布 `InvoiceReady`。task 先生成任务，matching 再重算台账及建议，全部复用最后一项审核的事务。两项先后不限；财务因币种待核实仍为待审核时不放行任务。
- `review_customs_approvals` 保存不可变审核版本、方式、说明及身份；放行依据直接保存在 `review_records.customs_approval_id`，空表示尚未放行，每个财务审核版本只设置一次。迁移只新增这张审核表和财务审核的一个可空字段，不回填旧任务、不删除任何业务数据；已生成任务保留，后续新任务与后继任务使用双审核门槛。
- 部署先运行 `npm.cmd run db:upgrade` 至 `0044_review_dual_approval` 再重启服务；不自动批准既有一致回执。测试见 `test_customs_approval.py`，MySQL 并发用例仅在提供隔离测试建库连接时执行。

### 双审进度与跨页定位

- `POST /api/review/declarations/query` 和 `POST /api/review/customs-receipts/query` 接受可选 `exactDeclarationNo`。该参数精确匹配真实出口报关单号，优先于支持部分匹配的 `declarationNo`，其余查询、统计及分页仍由后端处理。
- 两个列表的每行均返回 `approvalProgress`，包含 `finance`、`customs`、`status`、`label`、`reason`、`nextStep`、`linked` 和 `taskIds`。双审分别核对当前 NS 摘要、回执版本及冻结开票依据。出现重号、缺回执或来源变化时返回对应原因；`linked` 表示当前真实报关单号与回执可以唯一关联。
- 已放行时经 task 只读门面查询和冻结依据匹配的有效任务，包括同依据沿用的既有任务。没有有效任务时返回当前可核实的原因，例如未关联任务的供应商当前已关闭通知。任务查询由应用装配，避免 review 与 task 互相导入。本次无需新增迁移。

## 海关比对：自动审核一对一按行比价（2026-11-17）

原规则只按品名、单位、数量判定状态，总价差异只是展示字段，且拆行/合并一致也可自动审核，导致总价不一致的回执仍显示“可自动审核”。现规则（`policy/customs_match_policy.py`）：

- 一对一配对的 NS 报关行与海关项，同币种且两侧金额齐全时按十进制精确比较总价；数量一致、总价不同的组为 `total_mismatch`“总价不一致”，说明列出两侧总价，整单为 `different`（有差异），转人工审核。
- `auto_review(status, result)` 决定 `approval.autoAllowed`：仅当整单 `matched`（每组都是一对一且数量一致）且每组 `totalMismatch` 均为 false 时可自动审核。NS 报关行与海关项非一一对应（拆行、合并，`split_matched`）、总价有差异、或任一行总价未能比对（币种不同、金额缺失）时转人工核实，原因写入 `approval.reason` 并在列表“审核”列显示；以 `method=auto` 提交时返回 409 及同一原因。
- 人工审核准入：已唯一匹配且来源摘要就绪即可人工审核；说明选填，含 `different`。每次审核在 `review_customs_approvals` 保存审核人认证身份 `approved_by`、方式 `method`、时间 `approved_at` 与可选说明，列表明细显示“操作人 · 时间 · 说明”，作为审核审计。
- 列表、提交均按当前 NS 来源实时重比对，已导入回执刷新即按新规则展示。概况卡计数读取导入或重新匹配时保存的状态，部署后执行一次“全部重新匹配”使计数与新规则一致；已审核通过的记录不受影响。
- 测试：`test_customs_receipts.py::test_auto_review_requires_one_to_one_rows_with_equal_totals`、`test_customs_approval.py::test_split_rows_and_total_mismatch_go_to_manual_review`。


## 报关单比对按差异类型计数与筛选（2026-11-25，迁移 0056）

问题：列表每行按当前 NS 来源实时比对，但概况卡与状态筛选读取导入或手动“重新匹配”时保存的结论。11-17 总价规则上线后、以及 NS 报关行修改后，若没有手动全部重新匹配，卡片会显示“有差异 0 张”而列表里已出现“总价不一致”。

- **保存结论自动刷新**：`customs_receipt_service.refresh_matches(engine)` 按当前 NS 来源与比对规则重算全部回执，每批 200 张短事务（账本锁），只写结论（状态、NS 报关单、比对明细、差异标记）有变化的回执，比对时间不算变化。财务后台计算 `CalculationService.calculate` 在发布快照前调用；NS 同步（`SourceChanged`）、审核与算法版本变化都会触发。算法版本提升为 `review-v18`，部署重启后自动刷新旧结论，无需手工“全部重新匹配”。刷新失败时本次后台计算失败并按原退避重试。比对规则（`customs_match_policy`）变化时须同时提升 `CALCULATION_VERSION`。
- **差异类型**：`policy.difference_kinds(result)` 由分组状态派生四类标记并保存到回执头：`quantity_mismatch` 数量不一致、`unit_mismatch` 单位不一致、`total_mismatch` 总价不一致、`line_missing` 品名缺行（NS 无对应行或海关无对应项）。一张回执可同时属于多类。
- **接口**：`POST /api/review/customs-receipts/query` 新增 `difference`（`quantity_mismatch` / `unit_mismatch` / `total_mismatch` / `line_missing`，空为不限），与 `status` 同时生效，在数据库按标记筛选分页；`counts` 新增 `quantityMismatch`、`unitMismatch`、`totalMismatch`、`lineMissing`（随查询条件变化，不受状态筛选影响，可重叠，合计可能大于 `different`）。
- **页面**：概况仍为四张卡（海关回执、明细一致、有差异、未找到 NS），第三张由“数量或单位不一致”更名为“有差异”；查询栏新增“差异类型”下拉，选项附各类张数，与状态切换条同时生效，列表标题写明所选类型。有差异回执的提示改为“不能自动审核，人工核对后可审核，差异说明选填”，与后端规则一致。
- **验证**：`test_customs_receipts.py::test_counts_and_filters_split_differences_by_kind`、`::test_background_refresh_updates_stale_saved_conclusions`，`test_review_calculations.py::test_calculation_refreshes_saved_customs_conclusions`，前端 `pl-comparison.test.mjs` 的概况卡用例。

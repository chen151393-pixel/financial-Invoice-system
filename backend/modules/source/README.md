# source 模块：NS 来源数据

架构 v2 第 4a 步新建。负责从 NS 读取报关单、子采购单及关联依据，保存到新表 `source_*`，并向其他模块提供只读门面。表结构见[数据库设计](../../../docs/architecture/database.md)第 4.1 节。

**2026-10-15 已实现补强**：现有 `0004` 母单币种继承保留；已补继承所依据的原始版本引用、真实无母单与查询失败的区分，以及母单变化对全部相关审核的失效传播，详见数据库第 10.1、10.2 节。异常人工核实归 review，不向 source 或 NS 回写人工选定币种。

## 职责

- 采购报关联查：实时调用 NS 共用脚本，只读不入库（`POST /api/source/pl-comparison`）。
- 来源保存：同步页按页读取 NS，完整补齐基础明细、关联子采购和 PL 名称后，在一个短事务内保存；精确追溯缺失单独标记。2026-10-16 取消本地累计 300 条详情及单类关联记录限制，超过后继续分页读取；详情任务保持固定并发，整批全部读取成功后才入库。
- 关联维护：报关单—子采购单关联、依据状态（`relation_status`）、展示内容摘要（`content_sha256`）。
- 只读门面：报关单分页、完整内容、审核确认期间的账户锁（供 review 模块使用）。

## 目录

| 层 | 文件 | 说明 |
| --- | --- | --- |
| controller | `pl_comparison_controller.py` | 采购报关联查接口 |
| service | `storage_service.py` | 同步保存编排：账户锁、读取 NS、映射、写入 |
| | `parent_reference_service.py` | 事务外核实 REST 缺失的母单引用，保留独立查询证据 |
| | `link_service.py` | 保存后维护关联、依据状态、内容摘要；标记受影响但未同步的报关单 |
| | `declaration_service.py` | 报关单完整内容读取、分页、审核用账户锁 |
| | `ns_reader.py`、`relation_reader.py`、`relation_matcher.py` | 读取 NS 记录、关联依据、v3 整单关联（由 business 移入） |
| | `pl_comparison_service.py`、`contract_service.py` | 采购报关联查、子采购合同下载（由 business 移入） |
| dao | `document_dao.py` | 单头 + 明细保存规则（子采购单、报关单共用） |
| | `purchase_order_dao.py`、`customs_declaration_dao.py`、`customs_purchase_link_dao.py` | 各表查询与写入 |
| | `supplier_dao.py`、`company_dao.py`、`parent_order_dao.py`、`raw_record_dao.py` | 主数据、母采购单头、原始数据（同步锁在 `core/named_lock.py`） |
| entity | 10 个文件，一张表一个 | 与迁移 `0001_baseline`、`0002` 一致（`test_schema_entities.py` 比对） |
| mapper | `storage_mapper.py`、`bundle_mapper.py` | NS 记录 → 新表行；配置键 → 新列；逐单错误定位和原始证据保留 |
| | `ns_fields.py` | NS 字段取值、Decimal 安全转换 |
| policy | `ns_config.py`、`relation_policy.py`、`local_relation_policy.py` | 字段映射配置、v3 完整性规则、本地行定位规则（由 business 移入） |
| | `content_digest.py`、`currency_policy.py` | 内容摘要、子采购单币种规则（名称规范化在 `core/names.py`） |
| | `admission_policy.py` | 报关单准入（已出库）：有真实报关单号且有关联子采购单（2026-10-21 业务确认） |

## 同步明细批量读取（2026-10-19）

- 已支持的报关、子采购明细映射先按原父引用查询完整 ID 列表，再每批最多 300 个 ID 使用 SuiteQL 读取配置的展示/保存字段与逐行定位必需字段，不再逐条下载完整明细记录。超过 300 条继续分批，不截断；单头仍走原 REST 读取。
- 字段清单归 `policy/line_read_policy.py`；`integrations/netsuite/record_projection.py` 只负责已授权记录的字段投影和传输。保留原生行 ID、父单、PL、公司、货源地、商品、母采购行、销售行、履行引用与有效状态，继续执行现有 Packing、母采购行及 v3 追溯规则，不降为仅整单关联，也不按品名猜配。
- 引用恢复为原有 `id/refName` 形状；数值按 Decimal 解析，源空字段保留缺字段语义，由原映射规则决定拒绝或允许缺失。未知记录或字段映射使用原详情通道；商品引用用作展示字段时也保留原通道，避免 SuiteQL 与 REST 显示名差异。已进入批量通道后发生权限、超时、分页、漏行或身份异常时明确失败，不自动逐条重发。
- 部分成功模式仅在同一页的报关组之间复用已核实的 PL 名称，下一页或重同步重新读取；单据、明细、成员范围、币种和逐行依据不使用跨组缓存。原始快照中的明细只包含本次实际读取字段，业务内容摘要仍基于原有字段和关联计算。
- 验证见 `backend/tests/source/` 与 `test_sync_optimization.py`、`test_sync_large_batches.py`、`test_sync_partial_save.py`。覆盖逐行关联/审核摘要等价、精度、完整性、组失败隔离和新页重新读取。无需部署新的 NS 脚本，沿用当前 SuiteQL 只读权限；其他账套的字段可见性仍须验证。

协议参考：[Oracle SuiteQL REST 查询](https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/section_157909186990.html)。

2026-10-19 真实只读样本：对 CD000839、CD000840 的 3 条报关明细、9 条子采购明细，新旧基础读取的业务映射结果相同；HTTP 请求从 22 次降至 12 次，单次对照耗时为 11.08 秒与 6.45 秒。此测量仅覆盖单头已取得后的基础数据补齐，不含原始行/v3追溯、币种读取及数据库保存，不代表完整同步固定提速比例；没有写入 NS 或业务库。

## 部分保存整页一次读取（2026-10-19）

- 原部分保存模式先按报关关联组拆分，再对每组重复执行整条 NS 读取链（报关明细、反查子采购、PL、母单核实、原始行、Packing、销售/母采购行、v3 比对、母单单头）。20 组一页约需 250–300 次串行 NS 请求，这是线上单批 120 秒级耗时的主要来源（按代码路径估算，未在真实 NS 计时）。
- 现在 `PartialSyncService` 先对整页调用一次 `StorageService.read_bundle`，再由纯转换 `mapper/group_bundle.py` 按 NS 反查的报关—子采购成员关系拆成关联组，每组仍单独 `commit`（映射校验 + 短事务写入）。失败隔离、锁顺序、逐单结果与旧行为一致：映射或写入失败只影响本组，数据库结果不明停止后续组。
- 整页读取遇到业务错误（任一组的读取、追溯或核实失败）时，记录 `ns_sync_whole_page_fallback` 日志后改为原逐组读取，保持“失败只影响本组”；此时比原来多一次整页尝试。
- 母单缺失提示改由 `policy/parent_reference_policy.py` 的 `missing_parent_warnings` 按组生成，避免整页提示串组。单头仍为 REST 整条读取，`source_raw_records` 保存内容不变。
- 验证：`tests/source/test_line_batch_save.py` 断言 20 组一页的列表查询从 60 次降至 3 次、明细批次从 40 次降至 2 次；`tests/sync/test_sync_timing.py` 覆盖整页读取失败回退逐组；`test_sync_partial_save.py` 原有的组失败隔离、结果未知停止和锁冲突用例全部通过。

## 保存规则

- 按 NS 账套 + NS 内部 ID 识别单据；来源修改时间早于已保存版本、或记录类型变化时拒绝覆盖，整页回滚。
- 明细按稳定行键（`<NS 行记录类型>:<行 ID>`）更新；本次未返回的明细置为无效，不删除。
- 字段映射沿用服务器配置 `NETSUITE_PL_LOOKUP` 的 `storage_fields` 键名，对应新表列见 `mapper/storage_mapper.py` 的 `FIELDS`；默认缺字段、超长、精度不符时拒绝整页；规格型号缺失、已核实无母单及单价展示精度例外见对应章节。
- **开票口径**：子采购行 `unit` / `quantity` 取配置键 `unit_name` / `quantity`。按 2026-10-10 的决定，`unit_name` 应映射到 NS `custrecord_swc_subpo_item_unit`（采购单位）；报关单位另存 `declared_unit`。
- 供应商取子采购单上的 NS 供应商引用；采购公司取 `company_record_type` 记录（身份为 `类型:ID`）；申报主体记录类型未配置，身份前缀为 `declarant:`，与采购公司分开。
- 原始数据（NS 单据正文、关联依据）存 `source_raw_records`，内容不变不重复保存。

## 原始行追溯与基础保存（2026-10-16）

- 同步配置不再以原始报关行 RESTlet、PL v3 RESTlet 已配置作为保存前提；数据库、基础字段映射及记录读取权限仍须满足。
- 未配置原始行接口，或该接口返回同账套、契约版本 1 的明确错误 `RAW_SUBLIST_UNAVAILABLE` / `RAW_FIELDS_UNAVAILABLE` 时，基础单据继续保存。关联依据标为 `partial`，原因进入 `relation_issues` 和响应 `storage.warnings`，不会标为 `matched`。
- 原始来源不可用时不调用依赖它的 v3 追溯；独立可读取的 Packing、销售采购关系、母采购行仍保存为实际依据。原始来源可读但 v3 未配置时，同样标记追溯待补齐。
- 原始行多批读取中任一批明确不可用时，整次原始行结果弃用，不能把先前批次当成完整来源；已成功返回的数据仍严格校验单据范围、行身份、字段与唯一性。
- 认证或网络失败、账套／版本不符、来源内容损坏、超限、其他脚本错误，仍整页失败。基础单据及关联子采购读取、字段与金额映射、母采购单头币种读取仍执行原有校验，不做宽泛异常降级。已配置且实际调用的 v3 接口失败、旧版或范围不符也保持失败。
- `partial` 是技术追溯状态，不作为人工财务审核的额外门槛；审核继续基于有效关联子采购的完整明细，冻结数量、金额、单位与币种后生成任务。同步本身不审核、不创建开票任务。

## 子采购单币种（2026-10-15 确认）

2026-10-15 只读核对正式 NS 账户：子采购单（`customrecord_swc_subpo`）没有独立币种、汇率或独立结算字段（`custrecord_swc_subpo_item_ratewithrate` 是含税单价，不是汇率）。

| 情况 | 处理 |
| --- | --- |
| 有母采购单（`custrecord_swc_subpo_mainpo`） | 同步时以固定 SuiteQL（`parent_headers`）读取母采购单头，币种取母单 `currency` 引用的明确名称或已支持的代码，规范化为三位代码；汇率 `exchangerate` 保存在 `source_parent_orders.exchange_rate` 供追溯，本期不自动换汇；`currency_source = parent_order` |
| 子采购独立结算或汇率换算 | NS 当前没有对应字段，暂不适用 |
| 没有母采购单 | 待核实（需从合同或其他结算来源人工核实，人工核实入口在 review 财务审核表单） |
| 母采购单未读取到、币种缺失或无法识别为三位代码 | 待核实，原因写入 `currency_issue` |

待核实的子采购行在发票比对中不能通过（保留金额确认限制）。币种参与报关单内容摘要：币种变化后已审核的报关单需重新审核。2026-10-16 已修复：`parent_headers` 只查询母采购交易的 `currency`、`BUILTIN.DF(t.currency)` 和汇率，移除当前角色不可访问的 `currency` 表连接。币种名称按 `policy/currency_policy.py` 的明确中英文名称及所支持代码规范化，例如“人民币”→`CNY`；不能依据内部 ID `1`、地区、模糊简称或未知三字母名称猜测。旧快照的 `currencysymbol` 仍兼容，若明确代码与已识别名称冲突则待核实。未读取到、未识别或冲突时仍保留原来的人工核实与匹配限制，不默认填人民币。原始名称、币种内部 ID、汇率仍保存为版本依据。

补强后的确认以 review 的有效冻结依据为准：真实缺币种经财务有据核实后可使用审核币种，source 仍保留 `unresolved` 原值；不能以 source 仍为空否定合法人工依据，也不能在未核实前开放分配。网络或权限错误须重试，不能改写成无母单。`custrecord_swc_subpo_item_ratewithrate` 是含税单价，不是汇率。

### 本次真实只读验证（2026-10-16）

正式 NS 账套 5939865 的 CD000839、CD000840 已通过修正后的读取及隔离 SQLite 保存验证：合计 2 张报关单、3 条报关明细、5 张子采购、9 条采购明细；子采购币种均由母单“人民币”规范化为 CNY。原始子列表不可见保持追溯待补齐，不阻断基础保存。测试库已清理，正式业务库与 NS 记录未修改；此结果不等于已在正式业务库同步或验证 MySQL 并发。

## 关联规则

| 关联 | 来源 | 说明 |
| --- | --- | --- |
| 单头级 `ns_reference` | 子采购单的 NS 报关引用 | 同一子采购单同一时刻只指向一张报关单；改挂时旧关联置为 stale |
| 行级 `local_packing` | `policy/local_relation_policy.py`（原有规则） | 按子采购原始行、Packing、母采购行唯一定位报关汇总行；不按品名猜配 |
| 行级 `ns_v3` | NS v3 整单关联 | **尚未生成**：v3 行身份 `sourceKey` 的格式需从 NS 共用脚本确认；v3 结果先作为依据原样保存 |

- 依据状态：关联依据 `status=matched` 时为 `complete`，否则 `partial` 并保存原因。
- 本次未完整同步、但关联的子采购单已更新的报关单：依据改为 `partial`（"关联子采购已更新，请重新完整同步本报关单。"）并重算内容摘要，审核侧据此要求重新审核。

## 公开接口（`public.py`）

- `PlScriptService`、`SubpoContractSource`。
- 报关单读取门面（第 4b 步加入，供 review 使用）：`DeclarationService`（索引、分页内容、账户锁 `locked`）、`snapshot`（锁内读取完整内容）、`digest`（重算内容摘要）。2026-10-22 起索引返回真实报关单号并可按供应商筛选；`suppliers(account)` 返回有效报关单关联的供应商选项。
- 报关单准入（2026-10-22 加入）：`admission_issues(declaration_no, order_count)` 返回未出库原因列表，`admission_reason(issues)` 返回提示文案。2026-10-23 起拉取时即按此跳过（见下节）；review 保留同一判断，只用于拦截库中遗留的旧数据。
- 归档用报关单头（2026-10-23 加入，供 task 使用）：`SourceDirectory.declarations(ids)` 返回 `{id: {record_no, declaration_no, created_at}}`，`created_at` 为 NS 创建时间（UTC）。
- 子采购行比对上下文（第 4d 步加入，供 matching 使用）：`purchase_lines(connection, line_ids)`——子采购单号、供应商与采购公司（含规范化名称）、品名、单位、数量金额、币种及来源、是否有效、内容摘要 `digest`（建议生成后来源变化即改变）。
- 来源目录（第 4c 步加入，供 task 使用）：`SourceDirectory`（`service/directory_service.py`）——按 ID 批量取供应商、采购公司、子采购单号与行品名（含已停用记录，保证历史任务可显示），按名称 / 单号搜索 ID，有效供应商分页。

## 4e 切换

第 4b 步起，同步页 `/api/ns/sync/{kind}/pull-save` 经 `StorageService.sync_page` 保存到本模块新表；业务库连接检查只检查本模块的表（`entity.SOURCE_TABLES`）。旧 business 实现及过渡门面已在 4e 删除。

## 验证

`backend/tests/test_source_storage.py`（SQLite，合成 NS 数据，含 `/pull-save` 接口）、`test_schema_entities.py`、`test_pl_script.py`；`test_source_currency.py` 验证币种名称、旧代码、冲突、错误和来源版本；`test_source_optional_trace.py` / `test_source_optional_sync.py` 验证精确追溯可选、异常不放行及同步→审核→任务链路。锁与并发须在 MySQL 上验证。

4d 补充母单原始版本、币种内部 ID 及子单继承引用；母单变化刷新所有已关联子单，即使当前页未包含该子单。保存事务发布 SourceChanged，经 review 和 matching 传播失效。前端 PL 查询已从 reconciliation 移至 source，URL 与只读功能不变。

## 单位名称展示（2026-10-16）

单位编号在响应展示层通过 source 门面读取既有 `unit_dictionary`（`unit_id`、`unit_name`、`enabled`）解析为名称，仅使用启用且名称非空的条目。中文／文本单位保持原值，缺表、未知编号、停用编号保留来源值；数据库连接或查询失败仍报错，不吞掉异常。适用于财务核对（含报关数量说明）、开票任务行、发票比对采购侧及采购报关联查单位列；发票原始单位与同步原始字段不替换。

仅改变显示，不改变原始表、审核冻结单位、数量、单价、金额、内容摘要或比对结论；字典不是箱／件等数量换算规则。比对项显示名称时同时保留采购单位原值说明。来源目录 `describe` 新增 `units` 字典；现有展示字段仍返回字符串。验证见 `backend/tests/test_unit_display.py`。

`unit_dictionary` 为管理员维护的历史兼容表，本次明确归 source 只读访问，经 `public.py` 的 `unit_names(connection)`、`unit_label(value, names)` 提供给其他模块；不纳入新迁移链，不复制、改名或覆盖其数据。保留它以支持现有单位编号；后续明确迁移到 source 命名表并切换所有展示调用方后，才能移除兼容映射。

### 供应商档案只读查询

`SourceDirectory.suppliers(account, keyword, page, page_size, *, include_ids=None, exclude_ids=(), matching_ids=())` 支持 task 供应商档案：包含/排除 ID 先过滤再分页；关键词匹配名称、NS 内部 ID 或调用方提供的匹配 ID。返回 NS 内部 ID，用于区分同名供应商；source DAO 只查询本模块表。


同步页读取优化：`ns_reader.py` 合并同类父引用查询，复用 `integrations/netsuite/read_batch.py` 的批内详情缓存与有界只读并发；子采购入口仍逐报关复核已有子采购归属。来源读取器、关联读取器及保存服务通过可选回调报告真实阶段，不依赖 sync 私有实现。保存范围、币种规则、完整性校验、锁和短事务未改变；缓存不跨保存批次使用。


## 报关规格型号缺失（2026-10-16）

`customrecord_swc_delare_detail` 的 `specification → custrecord_swc_huge` 是非关键展示字段，数据库本来允许 NULL。NS 明细响应未返回该字段时，现在保存为未知值（NULL），在 `storage.warnings` 中按报关单提示缺失条数及字段填写／可见性待核实。原始响应保留缺字段的事实，不补造型号，不保留上次型号冒充当前来源；型号变化继续参与原有摘要和审核失效判断。

仅此已知记录类型及映射获准降级，映射配置本身仍须提供。拼错字段名、其他记录类型、品名／数量／单位／金额等已配置字段缺失仍整批失败；存在但格式或长度不合法的型号也仍报错。不会根据字段缺失推断 NS 中确实为空，也不会绕过来源权限或逐行关联校验。规则位于 `policy/optional_field_policy.py`，Mapper 按规则保存 NULL，StorageService 汇总提示；无数据库迁移及前端规则变化。


## 按完整关联组保存（2026-10-16）

同步页面通过 `StorageService.sync_partial_page` 使用 `partial_sync_service.py`：在同一账本锁、账户锁内读取本页，将同一报关单及其全部关联子采购视为一个保存单元；无报关引用的子采购单独成组。每组复用 `_save_locked` 的完整读取、字段与币种校验、短事务和 `SourceChanged` 事件。成功组立即提交，其他组的数据或只读请求错误单独返回，不撤销已提交组。不能从失败组挑几条合规明细写入，避免覆盖旧完整单据或错误停用旧明细；金额精度仍严格校验，不截断、不四舍五入。

数据库连接或提交异常标记该组结果未知，立即停止后续组，保留此前确认成功的统计，未处理组明确标出；结果未知禁止自动重试。初始列表身份/分页错误及配置、锁错误仍在开始保存前失败。`sync_page` 保留旧整页原子行为，供旧调用方及已有 PL 保存流程兼容；本节逐组行为只用于同步页面启用的 `partialSave` 请求。

`vo/storage_result.py` 汇总单个确认提交组，`vo/partial_sync_result.py` 汇总本批入口单据状态；含关联补齐的实际新增／更新数量与入口单据数量口径不同。测试 `test_sync_partial_save.py` 覆盖单价错误、同报关多子采购、后续读取失败、组内回滚、旧数据保留、提交未知停止和成功单据审核生成任务。


## 单价展示精度（2026-10-16）

报关明细和子采购明细的 `unit_price` 使用既有 `DECIMAL(24,8)`。合法 NS 单价超过 8 位小数时，在 `policy/unit_price_policy.py` 中用 Decimal 按 ROUND_HALF_UP 四舍五入至 8 位，再执行列范围校验，避免仅因多余小数导致关联组保存失败。原始单价完整保存在 `source_raw_records`；响应 `storage.warnings` 按单据提示实际调整的明细数，尾随零不触发提示。NULL 继续表示未知。

此规则只用于这两类来源明细的单价：数量、行金额、单据总额、母单汇率和币种沿用原值及原有严格校验，不用处理后的单价乘数量反算金额。格式错误、非有限数值、浮点输入、整数位溢出（包括四舍五入进位后溢出）仍失败，不填零或截断。整页保存与逐关联组保存复用同一映射，无数据库迁移，无 NS 写入。

审核摘要仍基于本地展示值；原始单价更精细的变化另存原始快照版本。重复相同来源不重复创建任务；本地单价或金额等有效依据变化仍走原有审核失效机制，已冻结任务金额不会被来源同步重算。`test_source_unit_price.py` 覆盖边界值、原值留存、金额数量校验，以及两种入口、两种保存模式下同步→审核→任务与重复同步；使用隔离 SQLite 和合成 NS 数据，不能代替 MySQL 并发或真实 NS 联调。


## 缺失母单引用核实与错误定位（2026-10-16）

对子采购类型 `customrecord_swc_subpo` 的既有映射 `parent_order_no → custrecord_swc_subpo_mainpo`，REST 响应缺少字段时，`parent_reference_service.py` 在事务外通过固定 SuiteQL `purchase_parent_links` 查询该单据的母单引用及显式空值状态。每次最多查询 300 个内部 ID，超出继续分批，没有累计数量上限；已返回母单字段的记录不增加查询。

仅查询返回当前单据且明确确认母单为空，才允许基础数据保存：`parent_relation_status = no_parent`、`currency_source = unresolved`、币种为 NULL，页面沿用“待核实”展示。原始 REST 快照仍保留字段缺失，独立查询证据存入 `parentReferenceCheck`；数量、行金额和总额保留 NS 原值，不填默认币种、不换汇、不反算金额。缺少记录、身份重复或越界、查询失败或两次读取矛盾均保持失败，不能当作无母单；其他字段映射错误不放行。

审核沿用既有规则，可保留待核实币种或由财务提供合同等依据人工核实，人工币种不回写 source；未核实币种仍不能确认发票匹配。同一报关单关联组的原子性不变，真实无母单不再阻断该组的基础保存。`mapper/bundle_mapper.py` 对字段映射错误补充实际出错单据的单号与内部编号，逐单结果明确“本关联组未保存”，避免把关联子单错误误认为入口单据自身错误。

验证由 `test_source_parent_reference.py` 覆盖两类入口与两种保存模式、独立核实失败时旧数据保留、超过 300 条分批、原始金额与证据留存、人工币种及重复同步、同组无母单和实际错误单号。使用隔离 SQLite 与合成 NS 数据；没有数据库结构变更或 NS 写入。

2026-10-16 使用修复后的服务只读复核正式 NS：2226、2246、2251、2266 均明确无母单；2235 仍关联母单 371689。此联调未修改 NS 或本地业务数据，实际入库行为由上述隔离测试验证。

## 拉取时出库准入与 NS 创建时间（2026-10-23）

- 业务确认：没有真实报关单号、或 NS 反查不到关联子采购单的报关单**不拉取入库**；只因它被带出的子采购单一起跳过。规则复用 `policy/admission_policy.py`，数据包转换在 `mapper/admission_filter.py`，于 `StorageService.read_bundle` 读取单头与反查子采购之后、补读原始行和关联依据之前执行，整页与逐组两种保存方式都经过这里。
- 响应：`storage.skipped` 列出跳过的报关单（id、number、reason），`storage.warnings` 首条写明“已跳过未出库报关单……”；部分保存模式下入口单据状态为 `skipped`，`batch.counts.skipped` 单独计数，不算失败。NS 补齐后重新拉取对应日期范围即可入库。
- 不处理历史：之前已入库的未出库报关单保留在库中，不删除、不改写；review 列表不再显示它们，审核时仍会拒绝。
- 报关单新增 `ns_created_at`（迁移 `0027_source_customs_created_at`），取 NS 系统字段 `created`（与同步页“按创建日期”筛选同一字段），按 UTC 保存，供归档月份使用。字段缺失或无法识别时保存为空，不用申报日期等其他日期代替；已入库的报关单在下次同步时补齐。**真实 NS 的 REST 单头是否返回 `created` 尚待一次只读核实。**
- 验证：`backend/tests/source/test_admission_sync.py`。

## 销售单汇率与人民币申报价（2026-10-23）

- 同步时按子采购单的销售单引用（`custrecord_swc_subpo_so`）以固定只读 SuiteQL `sales_headers` 读取销售单头（单号、币种、汇率），保存到 `source_sales_orders`（迁移 `0029_source_sales_orders`），子采购单 `sales_order_id` 指向它。读取失败时提示“销售单汇率读取失败”，不影响单据保存，原关联保持不变。**真实 NS 的销售单汇率字段尚待一次只读核实。**
- 报关行对应的销售单：其关联子采购单的销售单中单号与报关行销售订单号一致的；没有一致的且只有一个时取该销售单（`policy/declared_price_policy.py`）。
- 申报幅度 =（申报价 − 采购价）÷ 申报价：申报价 = 报关行金额 × 对应销售单汇率（人民币报关行不换算）；采购价 = 该报关行行级关联子采购行的**含税**金额合计。报关行与子采购行单位不一致、采购币种不是人民币、金额或汇率缺失时不计算并写明原因；只标出负数（采购价高于申报价）。汇率**不参与**报关单内容摘要，变化不触发重审。
- 门面：`declared_cny`、`pick_sales_order`（review 申报幅度）；`declared_prices(connection, purchase_line_ids)`（matching 价格校验）；`purchase_lines` 上下文新增 `declared`（不参与摘要）；报关单 `snapshot` 新增 `sales_orders`（不参与摘要）。
- 验证：`backend/tests/test_declared_price.py`。

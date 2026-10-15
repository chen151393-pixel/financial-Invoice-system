# source 模块：NS 来源数据

架构 v2 第 4a 步新建。负责从 NS 读取报关单、子采购单及关联依据，保存到新表 `source_*`，并向其他模块提供只读门面。表结构见[数据库设计](../../../docs/architecture/database.md)第 4.1 节。

**2026-10-15 方案修订，待实施部分**：现有 `0004` 母单币种继承保留；后续补继承所依据的原始版本引用、真实无母单与查询失败的区分，以及母单变化对全部相关审核的失效传播，详见数据库第 10.1、10.2 节。异常人工核实归 review，不向 source 或 NS 回写人工选定币种。

## 职责

- 采购报关联查：实时调用 NS 共用脚本，只读不入库（`POST /api/source/pl-comparison`）。
- 来源保存：同步页按页读取 NS，完整补齐明细、关联子采购、PL 名称与关联依据后，在一个短事务内保存。
- 关联维护：报关单—子采购单关联、依据状态（`relation_status`）、展示内容摘要（`content_sha256`）。
- 只读门面：报关单分页、完整内容、审核确认期间的账户锁（供 review 模块使用）。

## 目录

| 层 | 文件 | 说明 |
| --- | --- | --- |
| controller | `pl_comparison_controller.py` | 采购报关联查接口 |
| service | `storage_service.py` | 同步保存编排：账户锁、读取 NS、映射、写入 |
| | `link_service.py` | 保存后维护关联、依据状态、内容摘要；标记受影响但未同步的报关单 |
| | `declaration_service.py` | 报关单完整内容读取、分页、审核用账户锁 |
| | `ns_reader.py`、`relation_reader.py`、`relation_matcher.py` | 读取 NS 记录、关联依据、v3 整单关联（由 business 移入） |
| | `pl_comparison_service.py`、`contract_service.py` | 采购报关联查、子采购合同下载（由 business 移入） |
| dao | `document_dao.py` | 单头 + 明细保存规则（子采购单、报关单共用） |
| | `purchase_order_dao.py`、`customs_declaration_dao.py`、`customs_purchase_link_dao.py` | 各表查询与写入 |
| | `supplier_dao.py`、`company_dao.py`、`parent_order_dao.py`、`raw_record_dao.py` | 主数据、母采购单头、原始数据（同步锁在 `core/named_lock.py`） |
| entity | 10 个文件，一张表一个 | 与迁移 `0001_baseline`、`0002` 一致（`test_schema_entities.py` 比对） |
| mapper | `storage_mapper.py` | NS 记录 → 新表行；配置键 → 新列 |
| | `ns_fields.py` | NS 字段取值、Decimal 安全转换 |
| policy | `ns_config.py`、`relation_policy.py`、`local_relation_policy.py` | 字段映射配置、v3 完整性规则、本地行定位规则（由 business 移入） |
| | `content_digest.py`、`currency_policy.py` | 内容摘要、子采购单币种规则（名称规范化在 `core/names.py`） |

## 保存规则

- 按 NS 账套 + NS 内部 ID 识别单据；来源修改时间早于已保存版本、或记录类型变化时拒绝覆盖，整页回滚。
- 明细按稳定行键（`<NS 行记录类型>:<行 ID>`）更新；本次未返回的明细置为无效，不删除。
- 字段映射沿用服务器配置 `NETSUITE_PL_LOOKUP` 的 `storage_fields` 键名，对应新表列见 `mapper/storage_mapper.py` 的 `FIELDS`；缺字段、超长、精度不符时拒绝整页。
- **开票口径**：子采购行 `unit` / `quantity` 取配置键 `unit_name` / `quantity`。按 2026-10-10 的决定，`unit_name` 应映射到 NS `custrecord_swc_subpo_item_unit`（采购单位）；报关单位另存 `declared_unit`。
- 供应商取子采购单上的 NS 供应商引用；采购公司取 `company_record_type` 记录（身份为 `类型:ID`）；申报主体记录类型未配置，身份前缀为 `declarant:`，与采购公司分开。
- 原始数据（NS 单据正文、关联依据）存 `source_raw_records`，内容不变不重复保存。

## 子采购单币种（2026-10-15 确认）

2026-10-15 只读核对正式 NS 账户：子采购单（`customrecord_swc_subpo`）没有独立币种、汇率或独立结算字段（`custrecord_swc_subpo_item_ratewithrate` 是含税单价，不是汇率）。

| 情况 | 处理 |
| --- | --- |
| 有母采购单（`custrecord_swc_subpo_mainpo`） | 同步时以固定 SuiteQL（`parent_headers`）读取母采购单头，币种取 `purchaseOrder.currency` 的三位代码；汇率 `exchangerate` 保存在 `source_parent_orders.exchange_rate` 供追溯，本期不自动换汇；`currency_source = parent_order` |
| 子采购独立结算或汇率换算 | NS 当前没有对应字段，暂不适用 |
| 没有母采购单 | 待核实（需从合同或其他结算来源人工核实，人工核实入口尚未实现） |
| 母采购单未读取到、币种缺失或无法识别为三位代码 | 待核实，原因写入 `currency_issue` |

待核实的子采购行在发票比对中不能通过（保留金额确认限制）。币种参与报关单内容摘要：币种变化后已审核的报关单需重新审核。三位代码取自 NS 币种记录的 `symbol` 字段，部署后请在正式账户只读核对一次。

补强后的确认以 review 的有效冻结依据为准：真实缺币种经财务有据核实后可使用审核币种，source 仍保留 `unresolved` 原值；不能以 source 仍为空否定合法人工依据，也不能在未核实前开放分配。网络或权限错误须重试，不能改写成无母单。`custrecord_swc_subpo_item_ratewithrate` 是含税单价，不是汇率。

## 关联规则

| 关联 | 来源 | 说明 |
| --- | --- | --- |
| 单头级 `ns_reference` | 子采购单的 NS 报关引用 | 同一子采购单同一时刻只指向一张报关单；改挂时旧关联置为 stale |
| 行级 `local_packing` | `policy/local_relation_policy.py`（原有规则） | 按子采购原始行、Packing、母采购行唯一定位报关汇总行；不按品名猜配 |
| 行级 `ns_v3` | NS v3 整单关联 | **尚未生成**：v3 行身份 `sourceKey` 的格式需从 NS 共用脚本确认；v3 结果先作为依据原样保存 |

- 依据状态：关联依据 `status=matched` 时为 `complete`，否则 `partial` 并保存原因。
- 本次未完整同步、但关联的子采购单已更新的报关单：依据改为 `partial`（"关联子采购已更新，请重新完整同步本报关单。"）并重算内容摘要，审核侧据此要求重新审核。

## 公开接口（`public.py`）

- `PlScriptQuery`、`PlScriptService`、`SubpoContractSource`。
- 过渡期导出（仅供旧 business / reconciliation 使用，第 4e 步删除）：`PlReader`、`RelationReader` 等 NS 读取能力。
- 报关单读取门面（第 4b 步加入，供 review 使用）：`DeclarationService`（索引、分页内容、账户锁 `locked`）、`snapshot`（锁内读取完整内容）、`digest`（重算内容摘要）。
- 子采购行比对上下文（第 4d 步加入，供 matching 使用）：`purchase_lines(connection, line_ids)`——子采购单号、供应商与采购公司（含规范化名称）、品名、单位、数量金额、币种及来源、是否有效、内容摘要 `digest`（建议生成后来源变化即改变）。
- 来源目录（第 4c 步加入，供 task 使用）：`SourceDirectory`（`service/directory_service.py`）——按 ID 批量取供应商、采购公司、子采购单号与行品名（含已停用记录，保证历史任务可显示），按名称 / 单号搜索 ID，有效供应商分页。

## 过渡期

第 4b 步起，同步页 `/api/ns/sync/{kind}/pull-save` 经 `StorageService.sync_page` 保存到本模块新表；业务库连接检查只检查本模块的表（`entity.SOURCE_TABLES`）。旧 `business` 模块的保存不再由同步页调用，第 4e 步删除。

## 验证

`backend/tests/test_source_storage.py`（SQLite，合成 NS 数据，含 `/pull-save` 接口）、`test_schema_entities.py`、`test_pl_script.py`；锁与并发须在 MySQL 上验证。

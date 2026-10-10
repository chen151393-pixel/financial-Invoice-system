# 业务记录模块

## 同步来源关系

`PlReader.complete_customs_purchases` 按 NS 显式报关引用反查全部关联子采购。`relation_reader.py` 读取原始报关行、Packing、销售采购行关系及母采购行键；`relation_matcher.py` 在同次同步中复用 `PlScriptService` 按CD获取NS v3整单关联，核验报关身份、明细数量及子单范围。`StorageService.sync/sync_page` 将来源、关联、分摊展示值及单头外键原子保存。固定只读SQL位于 `relation_sources.py`，不接收网页SQL。`relation_mapper.py` 校验已存契约、身份和摘要后向财务模块提供展示结果，不返回原始Packing或NS正文。

关系证据与结果存入独立业务表 `customs_reconciliation_results`，一张报关单对应一条当前结果。`evidence_data` 保存原始依据，`comparison_payload` 保存v3契约，摘要、完整性、数量及时间独立成列。迁移 `0005_customs_relations` 搬迁旧报关JSON中的依据后移除旧键，完整字段见[表说明](../../../docs/mysql/customs-reconciliation-results.md)。`relation_dao.py` 负责该表SQL，`relation_storage_mapper.py` 转换存储契约；`relation_policy.py` 的技术完整性规则由同步与兼容NS实时审核路径共用；本地财务人工审核不以其结果为前置条件，金额不在Python重新分摊。接口未配置或仍是旧版时完整同步失败；完整读取后实际存在的来源冲突可以保存为partial。字段与配置见[原始来源说明](../../../docs/finance-source-reader.md#同步时保存的对应关系)。既有 `save_related_snapshot` 内部快照导入仍不自动访问NS；补齐实时关联使用网页拉取并保存入口。

服务器内部 `RelationBackfillService.targets/run(ids, owner)` 支持对同身份、同账套的已入库报关单单独补拉依据，每批最多20张。复用同步命名锁和 `RelationReader`，事务内重新核对原快照后仅更新独立关联结果表；原单据字段、子采购、外键及完整同步时间不变。`mode=evidence_backfill`、`baseSyncedAt` 记录补拉性质及原快照时间；因子采购仍来自旧快照，技术完整性状态保持 `partial`，不表示逐行匹配已经完成，也不单独阻止财务人工审核。没有新增接收浏览器原文的入口。

`CustomsReconciliationSource` 向财务模块提供已入库的报关及直接关联采购。`review_source_mapper.py` 为实际展示的来源内容生成稳定摘要；人工审核通过后，来源变化会使旧审核不再适用。`locked_review` 在确认期间复用同步账户锁，避免保存审核的同时替换来源。人工审核的权限、状态和审计归属 reconciliation 模块，机器关联完整性与财务审核状态分开保存。

`local_relation_policy.py` 补充本地来源的报关行定位：NS 子采购创建脚本将原报关品名写入 `custrecord_swc_subpo_item_bgname`；按子单的报关引用、PL、公司、商品、母采购原生行（销售采购链接和母行商品共同核实）及履行/销售行引用定位已存 Packing，再以公司＋原报关品名＋Packing 货源地定位唯一汇总行。合法无母 PO 的子行必须有履行请求与销售行引用。不用普通采购品名、汇总行母采购字段或显示行号猜配。重复汇总行、跨多行、来源冲突、依赖失效及不属于当前快照的补拉依据均不生成归属。

该定位只生成展示关系 `lineRelations`，优先保留已验证的 NS v3 展示契约；没有 v3 时按本地关系逐行展开，数量和金额仍为子单原值，不生成分摊额度，不将技术状态改为 `matched`。无需新增表或字段，复用来源表 `source_data` 和关系表 `evidence_data`；先分页主键再读取当前页依据，原始 JSON 不返回前端。行归属参加审核内容摘要，改变归属后旧预览和审核不再适用。测试见 `backend/tests/test_local_line_relations.py`。

## 母采购表

独立业务库已新增母采购单主表／明细表及母子组合外键，见[八表关联说明](../../../docs/mysql/eight-table-relations.md)。版本 `0002_parent_relation_status` 增加子单母采购状态（unknown／no_parent／linked）及子行 `ns_parent_line_ref` 原始标识字段；版本 `0003_customs_price_precision` 将报关单价扩为 DECIMAL(38,18)，保留来源精度。迁移命令为 `npm.cmd run db:business:upgrade`。历史空引用仍默认 unknown；服务端快照在核实母行后写入 linked，REST 与独立 SQL 同时确认没有母单、且不存在母行引用时写入 no_parent。网页母采购自动拉取和定时同步尚未接入。

## 母子采购快照关联导入

内部入口 `StorageService.save_related_snapshot(bundle, owner)` 接收服务器完整读取的报关、子采购、母采购与行证据，不提供浏览器上传原文接口。归属仍由认证 owner 派生，快照 NS 账户必须与调用服务的账户一致。沿用原账户命名锁和 `dao.save_document`，母采购、报关、子采购在同一事务保存，重复调用按来源身份及稳定行键更新，失败整批回滚。未更改既有网页 API。

`related_purchase_policy.py` 执行来源身份、完整性、单位、母行对应和金额核对，复用 `storage_mapper.py` 的 Decimal／字段长度转换。`entity.py` 按需反射母采购两表，`dao.py` 在调用方事务中返回母行本地主键，Service 建立组合外键。

母采购 REST `item[].line` 与 SuiteQL `transactionline.id` 交叉核实；本地母行键保存 `transactionline:<uniquekey>`。子行保留原始母行标识，按母单 ID＋原生行 ID＋商品引用定位母行，不使用显示数组下标。母行 `amount` 保存 `grossAmt`；税额与未税金额、商品行合计与单头金额须一致。母行含税单价未建立可靠映射时留空，原始价格字段保存在来源 JSON。

本入口限定完整读取的商品采购；存在母单引用时，缺母单、费用行、截断明细、已知金额不一致或母行不匹配均拒绝整批导入。`purchase_parent_evidence` 须与子单范围相同，明确返回 linked／no_parent 及母单 ID，与 REST 对照；只有双重证据确认空引用才能写入 no_parent。引用变化时 DAO 在同一事务中先解除旧子行组合外键，再更新单头和明细；任一保存失败仍整体回滚。

`empty_field_evidence` 仅允许核实后保留申报主体、报关规格、子采购行单价及金额的源空值，不将字段省略普遍解释为空。完整原文仍保留在 source_data，证据保存在 emptyFieldEvidence。子采购行金额缺失时数据库保存 NULL，source_data.amountValidation.status 为 source_missing，返回“金额待核实”警告；全部金额存在且单头明细一致时为 matched。这是来源金额核对结果，不是财务审批状态。缺失金额不得当零汇总，也不得据此开放开票审核。

单位名称必须有同次核实的 NS 单位字典；子采购 `custrecord_swc_subpo_item_unit` 未返回时原始采购单位 `unit_name` 留空，不将 `custrecord_swc_subpo_item_bgunit` 写入该字段。子单自己的 `bgqty/bgunit` 另存于 `declaration_quantity/declaration_unit`，与 NS PL 汇总表的子采购展示数量、单位同源；它们不是母采购单或报关单行的单位。来源币种名称保留为来源值，未宣称已经标准化为 ISO 编码。

隔离 MySQL 验证见 `backend/tests/test_related_purchase_storage.py`：重复导入、稳定行键、无母单证据、关联变更、源空金额标记、单位缺失、跨账户／不完整快照拒绝、错误母行／商品拒绝、金额不一致和回滚。2026-09-23 与迁移测试合计 45 项通过；全后端 285 项通过，58 项需独立配置跳过，其中本次 43 项 MySQL 测试已单独通过；lint 通过。

业务库连接检查使用命令 `npm.cmd run db:business:check`（`core/database.py`）；原 `GET /api/business/database-status` 接口无调用方，已删除。

## 文件职责

当前核对页使用 `POST /api/ns/pl-script-comparison`：`dto.py` 的 `PlScriptQuery` 校验条件，`pl_script_service.py` 调用NS共用服务并检查账户、范围及完整性，`pl_script_vo.py` 按contractVersion校验v1／15列、v2／17列展示契约。v2末两列为NS原单价及报关币种，保持字符串，采购行这两列必须为空；版本和列数不符时拒绝，不在Python补算。NS追溯和分摊直接复用Suitelet同目录模块，仅返回查询JSON，不在Python中维护第二套规则。需上传新版RESTlet才能返回17列，旧版在过渡期间保持兼容，见 [部署说明](../../../docs/pl-script-integration.md)。

`controller.py` 只声明 `POST /api/ns/pl-script-comparison`；`service.py` 装配联查与存储用例。

## 公开入口

HTTP：`POST /api/ns/pl-script-comparison`。其他模块通过 `public.py` 读取来源。模块通过应用工厂注入依赖，不建立全局客户端或全局数据库连接。

已删除无调用方的接口：`/api/ns/pl-comparison`、`/api/ns/pl-lookup`、`/api/ns/pl-lookup/config`、`/api/ns/related-purchase`、`/api/ns/records/*`、`/api/ns/query`、`/api/business/pl-sync`、`/api/business/pl-storage/config`、`/api/business/pl-documents/query`、`/api/business/database-status`。

## 关键约束

`StorageService.sync(pl)` 与 `query(pl, page)` 已无 HTTP 入口，暂时保留：它们承载 `_save` 去重、关联与回滚规则的主要测试（`test_pl_storage.py`、`test_sync_storage.py`、`test_business_migrations.py`）。架构方案第 4 步把这些测试改为经 `sync_page` 后删除。

## 验证

在项目根目录运行 `npm.cmd run test:api`、`npm.cmd run lint:api` 和 `npm.cmd run check:architecture`。接口验证使用FakeNS，不操作真实NS。

## PL本地保存

同步页新增按页保存入口，复用 `StorageService.sync_page`：由同步模块提供服务器分页读取回调，在原有账户锁内读取，`PlReader.collect_records` 补齐独立明细、关联报关单和各自 PL。与旧PL保存共用 Mapper、DAO、短事务和去重规则；标准采购订单暂不支持保存。接口说明见 [同步模块](../sync/README.md#按页拉取并保存)。

`pl_reader.py`共用完整读取；`entity.py`反射既有四表，不自动建表；`storage_mapper.py`纯字段／Decimal转换；`dao.py`负责命名锁、查询及保存SQL；`storage_service.py`协调账户范围串行读取及原子事务。接口与字段映射见 [PL保存说明](../../../docs/pl-storage.md)。当前核对页仅查询 JSON，不提供 Excel 导出。

PL脚本结果校验通过后，Service按来源补充 `missingCells`，用于拼表关键字段缺失提示；保留NS关联、分摊和备注，不新增差额算法。

## 匹配快照公开读取

`public.PurchaseMatchingSource.read(owner)`只读返回当前身份有效子采购及其有效明细，用于matching模块的逐行试匹配。DAO执行带tenant限制的查询，不保存匹配关系，不调用NS。

## 供应商选择公开接口

`SupplierDirectory.read(owner, keyword, account, supplier_id, page, page_size)` 从同身份的有效采购订单按 NS 环境与供应商稳定 ID 分组，提供服务器搜索、分页及精确身份查询；过滤缺失供应商 ID 的来源。供 reconciliation 的供应商群配置调用，SQL 位于 `supplier_dao.py`，不创建独立供应商主数据副本。

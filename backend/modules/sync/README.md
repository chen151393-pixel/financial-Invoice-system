# 数据同步与连接模块

柠檬云页 `/sync/lemon` 现由应用层装配发票模块的Excel导入组件，支持原文件预览和确认入库。导入使用独立 `/api/invoices/import/*` 契约，见[发票模块](../invoice/README.md)；本模块的柠檬云API连接状态仍为未接入。

展示服务器连接配置与最近M2M认证结果，支持三类单据只读分页拉取；子采购订单和报关单另支持补齐明细后按页保存到独立 MySQL。尚未执行定时全量或增量同步，不写回 NS。

## 文件职责

controller.py接收请求；service.py生成连接状态并调用NS认证；dto.py校验分页；pull_service.py负责读取单据及校验上游响应，通过应用工厂注入的业务存储公开用例完成保存。没有持久同步队列。

## 公开入口

`GET /api/ns/status；POST /api/ns/connect`。模块通过应用工厂注入依赖，不建立全局客户端或全局数据库连接。

- `GET /api/ns/sync/sources`：三类单据的 allowed/reason 和柠檬云未接入状态。
- `POST /api/ns/sync/purchase-orders/pull`：标准采购订单 `purchaseOrder`。
- `POST /api/ns/sync/sub-purchase-orders/pull`：子采购单，使用 `NETSUITE_PL_LOOKUP.purchase.type`。
- `POST /api/ns/sync/customs-declarations/pull`：报关单，使用 `NETSUITE_PL_LOOKUP.customs.type`。

请求为 `{"offset":0,"limit":20}`，offset 为 0～99980，limit 为 1～20，必须是整数。拒绝多余字段；所有记录类型必须在 NETSUITE_RECORD_TYPES 白名单内并具有远端读取权限，不自动扩大权限。

可选 `startDate`、`endDate` 按记录创建日期筛选，格式 `YYYY-MM-DD`，必须同时填写或同时留空，年份 1900～2100，开始日不得晚于结束日。例如 `{"offset":0,"limit":20,"startDate":"2026-09-01","endDate":"2026-09-16"}`。旧请求省略日期时保持不限定日期。

后端向 NS 列表传入 `q`：标准采购订单使用 `createdDate`，两类自定义单据使用 `created`；条件为起始日 `ON_OR_AFTER` 且结束日次日 `BEFORE`，覆盖起止当天。按 NS 查询时区解释日期，不转换为浏览器时区。字段不可由客户端指定。筛选失败直接报错，不降级为无条件拉取。语法依据 [Oracle Record Collection Filtering](https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/section_1545222128.html)；各部署需验证字段可筛选权限及 NS 日期格式。

响应新增 `dateRange: {startDate, endDate, label}`，`label` 为“创建日期”；翻页必须携带相同日期条件。界面显示实际返回范围，修改日期后需重新拉取首页。

服务器配置 `NETSUITE_SYNC_DATE_FORMAT` 控制发送给 NS 的日期格式，默认 `YYYY-MM-DD`，也支持 `M/D/YYYY`、`D/M/YYYY`。必须与 NS 账户的查询格式一致，修改后重启后端。浏览器请求仍使用 `YYYY-MM-DD`；后端先计算结束日的次日，再按配置转换。非法配置在启动时拒绝，不自动切换格式或去掉筛选重试。

按 [Oracle 分页约束](https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/section_156414087576.html)，offset 必须是 limit 的整数倍，最多 1000 页；下一页按 limit 递增偏移。达到上限且仍有数据时明确报错，不宣称已全部拉取。

响应包含 rows（id、number、record 原始字段）、count、offset、hasMore、nextOffset、pulledAt、message。先读取列表 ID 再逐张读取详情；详情失败、重复 ID、分页异常时整页报错。金额小数返回十进制字符串，不跟随 NS 返回的链接。

## 关键约束

认证成功不等于拥有记录读写权限，状态不能虚构为同步完成。

仅拉取接口返回 REST 单头详情及内嵌资源，不额外联查独立明细。列表会随 NS 数据变化，不是不可变快照。定时同步、增量游标和柠檬云接口尚未实施。

## 按页拉取并保存

`POST /api/ns/sync/{kind}/pull-save` 使用与 `/pull` 相同的分页和日期请求，仅支持 `sub-purchase-orders`、`customs-declarations`。保留旧 `/pull` 的只读行为。前端不上传单据正文或操作者，保存使用后端读取结果及认证身份。

保存复用 business 模块的 StorageService、PlReader、Mapper 和 DAO：补齐每张单据的独立明细；子采购单同时补齐并保存关联报关单，报关单的其他 PL 明细也保留。采购主表的 PL 根据每张源单分别解析。单页及关联数据超过既有 300 条详情读取上限时拒绝整页保存，不截断后标记完整。

存储位置为 `BUSINESS_MYSQL_*` 指定的独立库：`purchase_orders`、`purchase_order_lines`、`customs_declarations`、`customs_declaration_lines`。复用六表结构及 `NETSUITE_PL_LOOKUP.storage_fields`，不新建表。标准采购订单尚无对应存储映射，保存返回422，不能与子采购单混写。

来源配置增加 `storageAllowed/storageReason`，反映读取权限、数据库和映射状态。点击保存时后端重新校验；数据库及字段转换失败不能视为成功。保存与旧 PL 保存共享身份／账户命名锁；全部 HTTP 读取结束后在短事务内原子更新，重复来源沿用主键，完整明细中缺失的旧行停用。空页不清空原数据。

成功响应保留分页字段并增加 `storage`：`purchase/customs` 各含 `created/updated/linesCreated/linesUpdated`，另含 `savedAt/message/warnings`；这些计数仅在提交成功后返回。采购保存计数包含关联报关单。下一页需继续携带日期条件。数据库提交或连接结果不确定时返回503，先核实本地数据，不自动重试。按 PL 查询本地记录复用 `POST /api/business/pl-documents/query`，使用相同身份；同步页暂未增加本地历史浏览页面。

## 同步对应关系（2026-09-24）

“拉取并保存”和已有 PL 保存入口现在共享同一条关系读取链路：先读取报关单与汇总明细，再按子采购单的 NS 报关引用反查全部子采购及明细（包括当前分页之外的同单子采购），同时读取 Packing、销售→母采购行关系和母采购来源行身份。原始报关子行通过已准备的只读 RESTlet 读取，配置见 [来源接口说明](../../../docs/finance-source-reader.md)。只读 `/pull` 继续作为单头详情预览，不保存关系；使用 `/pull-save` 才完整补齐并入库。

证据与当前关联结果保存在独立表 `customs_reconciliation_results`；需完成 `0005_customs_relations` 迁移。同次调用NS v3整单查询，保存明确的报关行→子采购行引用及本次数量金额。读取完成后随报关、子采购及外键同一事务提交，重复拉取替换本次证据；完整反查后解除已移出的旧子采购外键，保留采购本身和其他身份/账套。原始行或v3接口未配置、接口旧版、失败、截断、返回范围不一致时整页失败，不降级保存成完整同步；实际来源冲突则保存明确原因及可确认的关联。

响应 `storage.relations` 包含 `declarations/collected/matched/partial/rawLines/packingLines/purchaseLinks`。`matched` 表示来源及逐行关联完整，可以进入待审核；不是审核通过。`collected` 保留原计数兼容，不能单独据此判断审批。财务页读取保存结果，状态筛选和分页在后端完成。

固定 SuiteQL 仅接受服务端校验的内部 ID，最多300个ID/次、5000行/类及8MiB/类，不向浏览器开放SQL或任意URL。报关原始行接口每批最多20张。超过上限要求缩小同步范围，不截断保存。

## 验证

在项目根目录运行 `npm.cmd run test:api`、`npm.cmd run lint:api` 和 `npm.cmd run check:architecture`。接口验证使用FakeNS，不操作真实NS。

test_sync_pull.py 覆盖三类映射、身份、参数、金额精度、空结果和失败。真实 NS 读取权限与数据仍需联调。

`test_sync_storage.py` 覆盖补齐明细、PL解析、身份及参数校验、禁用映射、重复保存、原子回滚、空页、与PL保存互斥和HTTP提交。2026-09-16 在临时 MySQL 8.4.9＋假 NS 上通过全后端220项测试，1项另需专用回写库的测试跳过；不代表 MySQL 8.0 或真实 NS 入库已验收。真实业务库仅完成连接与六表可见性检查。

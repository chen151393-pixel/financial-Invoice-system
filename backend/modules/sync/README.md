# 数据同步与连接模块

柠檬云页 `/sync/lemon` 现由应用层装配发票模块的Excel导入组件，支持原文件预览和确认入库。导入使用独立 `/api/invoices/import/*` 契约，见[发票模块](../invoice/README.md)；本模块已提供已有账号授权绑定；发票 API 拉取仍未接入。配置、前端操作与接口见[账号绑定说明](../../../docs/lemon-account-binding.md)。

展示服务器连接配置与最近M2M认证结果，支持三类单据只读分页拉取；子采购订单和报关单另支持补齐明细后按页保存到独立 MySQL 的 source 新表（架构 v2 第 4b 步起）。尚未执行定时全量或增量同步，不写回 NS。

## 文件职责

controller/ns_controller.py接收 NS 请求；service/connection_service.py生成连接状态并调用 NS 认证；dto/source_dto.py校验分页；pull_service.py负责读取单据及校验上游响应，通过应用工厂注入的 source 模块 `StorageService.sync_page` 完成保存。没有持久同步队列。

## 公开入口

`GET /api/ns/status；POST /api/ns/connect`。模块通过应用工厂注入依赖，不建立全局客户端或全局数据库连接。

- `GET /api/ns/sync/sources`：三类单据的 allowed/reason 和柠檬云未接入状态。
- `POST /api/ns/sync/purchase-orders/pull`：标准采购订单 `purchaseOrder`。
- `POST /api/ns/sync/sub-purchase-orders/pull`：子采购单，使用 `NETSUITE_PL_LOOKUP.purchase.type`。
- `POST /api/ns/sync/customs-declarations/pull`：报关单，使用 `NETSUITE_PL_LOOKUP.customs.type`。

请求为 `{"offset":0,"limit":20}`，offset 为 0～99980，limit 为 1～20，必须是整数。拒绝多余字段；所有记录类型必须在 NETSUITE_RECORD_TYPES 白名单内并具有远端读取权限，不自动扩大权限。

可选 `startDate`、`endDate` 按记录创建日期筛选，格式 `YYYY-MM-DD`，必须同时填写或同时留空，年份 1900～2100，开始日不得晚于结束日。例如 `{"offset":0,"limit":20,"startDate":"2026-09-01","endDate":"2026-09-16"}`。旧请求省略日期时保持不限定日期。

后端向 NS 列表传入 `q`：标准采购订单使用 `createdDate`，两类自定义单据使用 `created`；条件为起始日 `ON_OR_AFTER` 且结束日次日 `BEFORE`，覆盖起止当天。按 NS 查询时区解释日期，不转换为浏览器时区。字段不可由客户端指定。筛选失败直接报错，不降级为无条件拉取。语法依据 [Oracle Record Collection Filtering](https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/section_1545222128.html)；各部署需验证字段可筛选权限及 NS 日期格式。

响应新增 `dateRange: {startDate, endDate, label}`，`label` 为“创建日期”；翻页必须携带相同日期条件。界面显示实际返回范围，修改日期后需重新开始时间段拉取。

2026-10-16：请求支持 `requireDateRange: boolean`（默认 false，兼容旧调用方）。当前页面固定提交 true，后端要求起止日期均填写并沿用格式、顺序和分页上限校验；校验失败前不读取 NS 或保存。前端依次调用相同接口直至 `hasMore=false`，中途停止／失败只结束后续请求，已提交批次不会整体回滚，不自动重试结果未知的保存。各批保存计数不代表整个时间段去重总量；关联补齐可能读取日期范围外的关联单据。旧调用方省略该字段仍可按页不限定日期拉取。

服务器配置 `NETSUITE_SYNC_DATE_FORMAT` 控制发送给 NS 的日期格式，默认 `YYYY-MM-DD`，也支持 `M/D/YYYY`、`D/M/YYYY`。必须与 NS 账户的查询格式一致，修改后重启后端。浏览器请求仍使用 `YYYY-MM-DD`；后端先计算结束日的次日，再按配置转换。非法配置在启动时拒绝，不自动切换格式或去掉筛选重试。

按 [Oracle 分页约束](https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/section_156414087576.html)，offset 必须是 limit 的整数倍，最多 1000 页；下一页按 limit 递增偏移。达到上限且仍有数据时明确报错，不宣称已全部拉取。

响应包含 rows（id、number、record 原始字段）、count、offset、hasMore、nextOffset、pulledAt、message。先读取列表 ID 再逐张读取详情；详情失败、重复 ID、分页异常时整页报错。金额小数返回十进制字符串，不跟随 NS 返回的链接。

## 关键约束

认证成功不等于拥有记录读写权限，状态不能虚构为同步完成。

仅拉取接口返回 REST 单头详情及内嵌资源，不额外联查独立明细。列表会随 NS 数据变化，不是不可变快照。定时同步、增量游标和柠檬云发票拉取尚未实施。

## 按页拉取并保存

`POST /api/ns/sync/{kind}/pull-save` 使用与 `/pull` 相同的分页和日期请求，仅支持 `sub-purchase-orders`、`customs-declarations`。保留旧 `/pull` 的只读行为。前端不上传单据正文或操作者，保存使用后端读取结果及认证身份。

第 4b 步起，保存由 [source 模块](../source/README.md) 完成：在 NS 账户锁内读取本页、补齐明细、关联子采购、PL 名称与关联依据，再在一个短事务内写入 `source_*` 新表（主数据、单头与明细、报关—子采购关联、依据状态、内容摘要、原始数据）。保存规则见 source 模块文档。旧 business 六表保存已在 4e 删除。

存储位置为 `BUSINESS_MYSQL_*` 指定的独立库，需完成新迁移链（`schema_version`）。字段映射沿用 `NETSUITE_PL_LOOKUP.storage_fields`。标准采购订单尚无对应存储映射，保存返回422。

来源配置的 `storageAllowed/storageReason` 反映基础读取权限、新表是否可见和字段映射；原始报关行及 v3 追溯接口不再是基础保存的配置前提。点击保存时后端重新校验；数据库及字段转换失败不能视为成功。全部 NS 读取结束后在短事务内原子更新，重复来源按 NS 身份更新，本次未返回的旧明细置为无效。空页不清空原数据。

成功响应保留分页字段并增加 `storage`：`purchase/customs` 各含 `created/updated/linesCreated/linesUpdated`，另含 `savedAt/message/warnings`；这些计数仅在提交成功后返回。采购保存计数包含关联报关单。下一页需继续携带日期条件。数据库提交或连接结果不确定时返回503，先核实本地数据，不自动重试。同步页暂未增加本地历史浏览页面；已保存的报关单在财务核对页（`/review`）查看。

## 同步对应关系（2026-09-24）

“拉取并保存”和已有 PL 保存入口现在共享同一条关系读取链路：先读取报关单与汇总明细，再按子采购单的 NS 报关引用反查全部子采购及明细（包括当前分页之外的同单子采购），同时读取 Packing、销售→母采购行关系和母采购来源行身份。原始报关子行通过已准备的只读 RESTlet 读取，配置见 [来源接口说明](../../../docs/finance-source-reader.md)。只读 `/pull` 继续作为单头详情预览，不保存关系；使用 `/pull-save` 才完整补齐并入库。

关联依据保存在 `source_customs_purchase_links` 与 `source_raw_records`。同次调用NS v3整单查询，保存明确的报关行→子采购行引用及本次数量金额。读取完成后随报关、子采购及外键同一事务提交，重复拉取替换本次证据；完整反查后解除已移出的旧子采购外键，保留采购本身和其他身份/账套。2026-10-16 起，未配置原始行接口，或同账套、版本 1 响应明确返回原始子列表／字段不可见时，基础单据可保存，追溯标记待补齐并跳过依赖原始行的 v3 查询。原始行可读取但 v3 未配置时也保存待补齐状态。认证、连接、基础读取失败、截断、范围或账套不符，以及其他原始行错误或已调用的 v3 接口失败／旧版仍整页失败；不会将这些错误吞成空成功。

响应 `storage.relations` 包含 `declarations/collected/matched/partial/rawLines/packingLines/purchaseLinks`。`matched` 仅表示来源及逐行关联完整，不是审核通过，也不是人工审核的必需门槛；`partial` 的完整基础单据仍按 review 的子采购、币种及冻结依据规则审核。`collected` 保留原计数兼容，不能单独据此判断审批。财务核对页（review 模块）读取 source 保存结果，状态筛选和分页在后端完成。

固定 SuiteQL 仅接受服务端校验的内部 ID，最多300个ID/次、5000行/类及8MiB/类，不向浏览器开放SQL或任意URL。报关原始行接口每批最多20张。超过上限要求缩小同步范围，不截断保存。

## 验证

在项目根目录运行 `npm.cmd run test:api`、`npm.cmd run lint:api` 和 `npm.cmd run check:architecture`。接口验证使用FakeNS，不操作真实NS。

test_sync_pull.py 覆盖三类映射、身份、参数、金额精度、空结果和失败。真实 NS 读取权限与数据仍需联调。

新链路保存与 `/pull-save` 接口由 `test_source_storage.py`、`test_sync_pull.py` 覆盖；原始追溯缺失仍可保存、审核并生成任务，以及错误仍拒绝保存，由 `test_source_optional_trace.py`、`test_source_optional_sync.py` 覆盖；来源变更与确认竞争见 `test_matching_mysql.py`。旧 `test_sync_storage.py` 随 business 实现退役，历史验收记录不代表当前正式环境已部署。

## 柠檬云账号绑定

`controller/lemon_binding_controller.py` 提供状态、开始授权、固定回调、确认与核实接口；`service/lemon_binding_service.py` 处理身份和一次性授权上下文；`dao/lemon_binding_dao.py` 条件更新 `entity/lemon_binding.py` 定义的绑定表。外部调用通过 `integrations/lemon/existing_account.py`，不放在数据库事务内。配置与手机号校验在 policy/dto 中。迁移 `0016_sync_lemon_bindings` 不包含密码或令牌字段。

入口为 `/api/sync/lemon/binding`，固定回调保留用户已指定的 `/api/lemon/oauth/callback`。只有管理员可绑定，回调需同一浏览器临时 Cookie，真正提交还需原身份及账号密码。网络结果未知或进程中断后禁止直接再次绑定，先查询官方状态；单 API worker 约束与部署步骤见上方说明。测试见 `test_lemon_binding.py`、`test_lemon_binding_database.py`。

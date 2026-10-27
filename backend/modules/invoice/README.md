# invoice 模块：进项发票

## 列表状态展示（2026-10-19）

列表及详情保留 `sourceStatus` 状态码，返回展示分类 `displayStatus` 和可空中文 `statusNotice`。`policy/invoice_status_policy.py` 将入库状态为 normal/red_offset 且含税金额为负的票展示为 `red_letter`（红字发票）；其余 red_offset 票展示为“已被红冲”。作废、未知状态优先保留。该分类兼容已入库的“正常”负数 Excel 票，不改写历史版本、不要求重新导入；不凭负金额推断原票已被红冲，也不猜测关联关系。Excel 来源状态兼容“已红冲”“已被红冲”两种明确文本。

查询 `status` 支持 `normal/red_letter/red_offset/void/unknown`，列表、分页与统计复用同一 DAO 条件。normal/red_offset 筛选排除已归类 red_letter 的负数票，作废/未知票仍按来源状态筛选。正常票提示为空，其余分类返回说明。不更改匹配规则，无数据库迁移。测试覆盖来源“正常”的负数票、来源红冲的正负票、作废和未知负数票，以及分页、详情、统计与 HTTP 查询的一致性。

架构 v2 第 4d 步在原地重建：读写新表 `invoice_raw_records`、`invoice_headers`、`invoice_items`（[数据库设计](../../../docs/architecture/database.md)第 4.4 节）。旧两表 `invoices`、`invoice_lines` 不再读写，旧数据不迁移。

**2026-10-15 接入与版本修订**：本期柠檬云 `GetInvoice` 人民币进项票和现有柠檬云 Excel 通道在适配时明确写入 `CNY`，不因接口无币种字段逐票转待核实；已记录 `currency_source=source_rule` 与 `source_rule_version=lemon_cny_v1`。这是本期来源范围约定，不依赖 NS 采购币种推断发票币种。

`invoice_versions` 与 `InvoiceChanging` / `InvoiceChanged` 已实现。相同业务内容复用当前版本，变更追加版本；重排保持逻辑 ID，身份歧义或不完整明细保留旧行并限制确认。既存 v2 发票追加基线快照，原分配缺少历史证据时保留占用并待复核。

## 职责

- 柠檬云 Excel 导入：预览不写数据；确认时重新解析、复核去重并整批原子保存。
- 进项发票列表（搜索、票面状态、开票日期、分页、按币种汇总）与详情。
- 导入事务中发布 `InvoicesImported`，matching 订阅后生成比对建议。
- 柠檬云 open2 手动拉票已接入：订阅 sync 的公开事件，保存票头/原始证据/不可变版本；专业版同时补齐商品行，默认版明细待接入。见[接入说明](../../../docs/lemon-invoice-sync-plan.md)。

## 目录

| 层 | 文件 | 说明 |
| --- | --- | --- |
| controller | `invoice_controller.py` | `GET /api/invoices/import/configuration`、`POST /import/preview`、`POST /import/confirm`、`GET /api/invoices`、`GET /api/invoices/stats`、`GET /api/invoices/{id}` |
| service | `import_service.py` | 预览凭证（绑定操作者、文件名、文件摘要、预览时票据版本，30 分钟）、命名锁、去重分类、整批保存、发布事件 |
| | `invoice_service.py` | 列表与详情 |
| | `invoice_stats_service.py` | 分布统计：最近 6 个月按开票日期的张数与人民币价税合计、票面展示状态（红字按负金额识别，同列表）、柠檬云账套张数与人民币价税合计；非人民币发票不混入金额，另返回 `otherCurrencyCount`；筛选条件同列表，分页参数不起作用 |
| | `invoice_reader.py` | 门面读取：`read_invoices`、`lock_invoice`（传入调用方连接） |
| | `excel_parser.py`、`xlsx_reader.py` | 柠檬云 XLS / XLSX 解析与源数据校验（沿用原实现） |
| dao | `header_dao.py`、`item_dao.py`、`raw_record_dao.py` | 各表读写 |
| mapper | `import_mapper.py` | 解析结果 → 新表行（金额两位小数、字段长度、名称规范化） |
| | `invoice_mapper.py` | 行 → 响应 |
| entity | `header.py`、`item.py`、`raw_record.py` | 与迁移一致（`test_schema_entities.py` 比对） |

## 导入规则

- 支持 34 列票头商品合并表（表名不限）与"发票信息""货物信息"双表；只接受 20 位文本票号的数电进项票，每次 1–1000 张，文件不超过 4MB。
- 只导入业务类型为"采购固定资产"的发票，其他类型跳过（响应给出原文件票数与跳过数）。
- 去重键 `invoice_key` = 发票代码 + 号码（数电票代码为空）。Excel 暂用固定账套标识 `lemon`；API 使用环境与 asid 的哈希命名空间。跨渠道同票因账套尚未对齐，在两个导入方向均拒绝，不自动合并。
- 原始数据摘要不含文件名与行号：同一张票重新导入时业务内容相同则跳过；同来源内容变化追加不可变版本并更新当前投影，跨来源冲突整批拒绝。
- 柠檬云 Excel 不含购买方与币种：币种按人民币（CNY）保存，购买方为空（比对时记为"发票未提供"）。
- 发票金额为两位小数；超过两位或超出字段长度时预览即拒绝。
- 服务身份（`service:`）只读，不能确认导入。
- 已删除旧实现中没有任何调用方的"图片单票录入"（`import_image_snapshot`）。

## 公开接口（`public.py`）

- 事件 `InvoicesImported(invoice_ids)`：本次新增或更新的发票 ID。
- `read_invoices(connection, invoice_ids)`：票头（状态、销售方、购买方及规范化名称、币种、价税合计、备注）与发票行（品名及规范化名称、规格、数量、单位、含税金额）。
- `lock_invoice(connection, invoice_id)`：在调用方事务中锁定票头（matching 审核分配时使用）。
- `read_invoice_amount_scope(connection, filters, after_id=0)`：复用列表的关键字、状态和日期筛选；首批返回全范围票面汇总，每批至多 500 张统计票头，供 matching 汇总匹配金额。返回普通数据，不暴露表结构，不按页面页码限制范围。

## 依赖

`core/named_lock.py`（导入互斥）、`core/names.py`（名称规范化）、`core/events.py`。不读取其他模块。

## 验证

`backend/tests/test_invoice.py`（SQLite，仓库虚构的 `fixtures/lemon-invoices.xls` 与内存生成的 XLSX）：预览与确认、重复跳过、跨来源冲突整批拒绝、业务类型筛选、预览凭证与服务身份、列表筛选汇总与详情、事件、HTTP。

## 版本文件

`service/version_service.py` 保存原始来源、不可变快照和当前投影；`policy/version_policy.py` 规范化业务摘要，排除显示行号；`dao/version_dao.py` 管理追加版本。`0008` 迁移增加版本表和当前逻辑行标记。列表详情仅展示当前行，比对视图保留历史行及其占用。

预览后其他请求改变同票版本时，旧确认返回 409 并要求重新预览；同一文件提交成功后的重试可以返回重复跳过。默认版和专业版票头已通过 sync 事件接入；专业版商品明细 API 已接入，默认版仍待接入。

## API 票头入库（2026-10-16）

`policy/lemon_invoice_policy.py` 校验进项范围、开票日期、字符串票号、状态与 Decimal 金额；`mapper/lemon_invoice_mapper.py` 转换官方票头；`dao/lemon_invoice_dao.py` 查询来源身份与跨渠道冲突；`service/lemon_invoice_service.py` 订阅事件并复用 `version_service.py` 保存。依赖仅为本模块与公开事件，不调用外部 HTTP。

同一环境/账套/InvoiceId 去重；票头变化追加不可变版本并复用现有匹配失效事件。默认版 API 票只保存票头，`detail_status=pending`；专业版通过明细接口补全并复用逐行匹配事件。现有查询接口保留，详情新增中文 `detailStatusLabel`。Excel 与 API 同票在账套未对齐时双向拒绝，防止重复台账与额度。

2026-10-19：专业版小驼峰字段由适配层规范化后复用同一校验和入库服务。专业版来源为 `lemon_professional`、账套命名空间前缀 `professional:`，默认版仍为 `lemon_open2` / `open2:`。两版都参与来源 ID 稳定性检查和 Excel 跨渠道冲突校验。真实只读数据在隔离 SQLite 验证：78 张读取、15 张新增、63 张范围外跳过；重复拉取 15 张未变化，未产生重复版本。商品行仍为 0；不表示生产数据库已写入。

API 业务类型支持多选，默认“采购固定资产”和“采购支出”；Excel 仍只新增固定资产。`policy/lemon_scope_policy.py` 通过 `public.py` 提供默认值、真实返回类型候选和结果文案。事件携带所选集合；未选类型跳过，取消勾选不改变旧票状态；上游将旧票改为范围外类型仍换版并置为待核实。全部跳过、空结果和全部重复时 `saved=false`，明确说明未新增或更新。真实7张采购支出票已在隔离 SQLite 验证入库和去重，未写生产库。

## 专业版商品明细与匹配（2026-10-19）

`policy/lemon_detail_policy.py` 校验列表与详情的票号、来源编号、种类、日期、供应商、状态、业务类型、备注及金额一致性，逐行金额合计须与票头相等。`mapper/lemon_detail_mapper.py` 转换品名、规格、单位、数量、金额和税率；原始详情保存在现有 raw_record。数量最多 8 位小数、金额最多 2 位，全部使用 Decimal；含税行金额由来源未税金额加税额得到，不用数量乘单价反算。

品名、单位、正数量、正含税金额齐备才标记 complete；空明细、缺少匹配字段及含折扣负行等不适用当前正数分配的票保留 pending。已有完整票后来缺明细时保留原逻辑行、限制确认；来源行身份仍复用品名/规格/单位，重排不新增版本，相同身份多行发生变化时保留旧行并标记 failed，不猜测对应关系。没有购买方和单价来源时不补造。

重新按原账套、日期范围拉取即可给既有票头补全，保持发票 ID；内容相同不重复建版或建议。完成后通过现有 InvoicesImported 自动生成建议；发票后续变化沿用 InvoiceChanging/InvoiceChanged 使已确认分配待复核。无需新增表或迁移。完整性统计读取保存后的真实投影，不能把明细完整等同已匹配。

详情协议、默认版边界与验证范围见[接入说明](../../../docs/lemon-invoice-sync-plan.md#专业版商品明细与匹配2026-10-19)。

### 列表定向补拉与未补齐原因

`read_lemon_refresh_targets(connection, invoice_ids)` 经 `public.py` 返回补拉所需来源身份、原账套命名空间、日期及当前版本，不暴露原始正文。sync 根据这些数据复用原拉票用例，invoice 继续通过同一事件与版本服务保存。

修正已有空票头补拉不完整行时仍显示 0 行的问题：无历史逻辑行时保存实际收到的商品行用于展示，仍保持 pending、禁止确认匹配；已有逻辑行时继续保留原投影与分配。结果的 `detailIssues` 给出空商品行、缺少匹配字段或身份歧义的具体原因，最多返回 100 张，`detailIssueCount` 为总数。来源为空时不会伪造商品行。

验证：`tests/sync/test_lemon_detail_refresh.py` 覆盖空票头补行、空响应原因与重复版本；既有匹配测试继续检查版本失效和占用保护。无需数据库迁移。

## 按账套筛选

`GET /api/invoices` 新增可选 `account`（最长 100 字符，空值表示全部），按票头 `lemon_account` 精确筛选，与关键字、票面状态和日期取交集。分页总数、票面汇总和 `read_invoice_amount_scope` 共用条件；未知账套返回空结果。`read_invoice_accounts(connection)` 只读返回全量已入库账套标识，供 sync 补充本地名称，不依赖当前页。无需数据库迁移。

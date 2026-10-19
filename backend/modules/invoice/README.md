# invoice 模块：进项发票

架构 v2 第 4d 步在原地重建：读写新表 `invoice_raw_records`、`invoice_headers`、`invoice_items`（[数据库设计](../../../docs/architecture/database.md)第 4.4 节）。旧两表 `invoices`、`invoice_lines` 不再读写，旧数据不迁移。

**2026-10-15 接入与版本修订**：本期柠檬云 `GetInvoice` 人民币进项票和现有柠檬云 Excel 通道在适配时明确写入 `CNY`，不因接口无币种字段逐票转待核实；已记录 `currency_source=source_rule` 与 `source_rule_version=lemon_cny_v1`。这是本期来源范围约定，不依赖 NS 采购币种推断发票币种。

`invoice_versions` 与 `InvoiceChanging` / `InvoiceChanged` 已实现。相同业务内容复用当前版本，变更追加版本；重排保持逻辑 ID，身份歧义或不完整明细保留旧行并限制确认。既存 v2 发票追加基线快照，原分配缺少历史证据时保留占用并待复核。

## 职责

- 柠檬云 Excel 导入：预览不写数据；确认时重新解析、复核去重并整批原子保存。
- 进项发票列表（搜索、票面状态、开票日期、分页、按币种汇总）与详情。
- 导入事务中发布 `InvoicesImported`，matching 订阅后生成比对建议。
- 柠檬云 open2 手动拉票已接入：订阅 sync 的公开事件，保存票头/原始证据/不可变版本；商品明细待补齐。见[接入说明](../../../docs/lemon-invoice-sync-plan.md)。

## 目录

| 层 | 文件 | 说明 |
| --- | --- | --- |
| controller | `invoice_controller.py` | `GET /api/invoices/import/configuration`、`POST /import/preview`、`POST /import/confirm`、`GET /api/invoices`、`GET /api/invoices/{id}` |
| service | `import_service.py` | 预览凭证（绑定操作者、文件名、文件摘要、预览时票据版本，30 分钟）、命名锁、去重分类、整批保存、发布事件 |
| | `invoice_service.py` | 列表与详情 |
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

## 依赖

`core/named_lock.py`（导入互斥）、`core/names.py`（名称规范化）、`core/events.py`。不读取其他模块。

## 验证

`backend/tests/test_invoice.py`（SQLite，仓库虚构的 `fixtures/lemon-invoices.xls` 与内存生成的 XLSX）：预览与确认、重复跳过、跨来源冲突整批拒绝、业务类型筛选、预览凭证与服务身份、列表筛选汇总与详情、事件、HTTP。

## 版本文件

`service/version_service.py` 保存原始来源、不可变快照和当前投影；`policy/version_policy.py` 规范化业务摘要，排除显示行号；`dao/version_dao.py` 管理追加版本。`0008` 迁移增加版本表和当前逻辑行标记。列表详情仅展示当前行，比对视图保留历史行及其占用。

预览后其他请求改变同票版本时，旧确认返回 409 并要求重新预览；同一文件提交成功后的重试可以返回重复跳过。默认版和专业版票头已通过 sync 事件接入；商品明细 API 尚未接入。

## API 票头入库（2026-10-16）

`policy/lemon_invoice_policy.py` 校验进项范围、开票日期、字符串票号、状态与 Decimal 金额；`mapper/lemon_invoice_mapper.py` 转换官方票头；`dao/lemon_invoice_dao.py` 查询来源身份与跨渠道冲突；`service/lemon_invoice_service.py` 订阅事件并复用 `version_service.py` 保存。依赖仅为本模块与公开事件，不调用外部 HTTP。

同一环境/账套/InvoiceId 去重；票头变化追加不可变版本并复用现有匹配失效事件。API 票只保存票头，`detail_status=pending`；不伪造商品行、不自动生成逐行候选。现有查询接口保留，详情新增中文 `detailStatusLabel`。Excel 与 API 同票在账套未对齐时双向拒绝，防止重复台账与额度。

2026-10-19：专业版小驼峰字段由适配层规范化后复用同一校验和入库服务。专业版来源为 `lemon_professional`、账套命名空间前缀 `professional:`，默认版仍为 `lemon_open2` / `open2:`。两版都参与来源 ID 稳定性检查和 Excel 跨渠道冲突校验。真实只读数据在隔离 SQLite 验证：78 张读取、15 张新增、63 张范围外跳过；重复拉取 15 张未变化，未产生重复版本。商品行仍为 0；不表示生产数据库已写入。

API 业务类型支持多选，默认“采购固定资产”和“采购支出”；Excel 仍只新增固定资产。`policy/lemon_scope_policy.py` 通过 `public.py` 提供默认值、真实返回类型候选和结果文案。事件携带所选集合；未选类型跳过，取消勾选不改变旧票状态；上游将旧票改为范围外类型仍换版并置为待核实。全部跳过、空结果和全部重复时 `saved=false`，明确说明未新增或更新。真实7张采购支出票已在隔离 SQLite 验证入库和去重，未写生产库。

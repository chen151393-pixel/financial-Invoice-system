# invoice 模块：进项发票

架构 v2 第 4d 步在原地重建：读写新表 `invoice_raw_records`、`invoice_headers`、`invoice_items`（[数据库设计](../../../docs/architecture/database.md)第 4.4 节）。旧两表 `invoices`、`invoice_lines` 不再读写，旧数据不迁移。

**2026-10-15 接入与版本修订**：本期柠檬云 `GetInvoice` 人民币进项票和现有柠檬云 Excel 通道在适配时明确写入 `CNY`，不因接口无币种字段逐票转待核实；计划记录 `currency_source=source_rule` 与 `source_rule_version=lemon_cny_v1`。这是本期来源范围约定，不依赖 NS 采购币种推断发票币种。

数据库第 10.4 节的 `invoice_versions`、稳定逻辑明细与 `InvoiceChanged` 尚待实施；此前保持当前内容冲突拒绝策略。后续同票变更追加不可变版本，关联确认进入复核，不能原地覆盖或释放旧占用。v2 已存发票及分配需准确回填版本或标记待核实，不因旧模块“不迁移”的决定而删除。

## 职责

- 柠檬云 Excel 导入：预览不写数据；确认时重新解析、复核去重并整批原子保存。
- 进项发票列表（搜索、票面状态、开票日期、分页、按币种汇总）与详情。
- 导入事务中发布 `InvoicesImported`，matching 订阅后生成比对建议。
- 柠檬云 open2 接口拉票在第 5 步接入（`integrations/lemon/` 为原型，尚未接入本模块）。

## 目录

| 层 | 文件 | 说明 |
| --- | --- | --- |
| controller | `invoice_controller.py` | `GET /api/invoices/import/configuration`、`POST /import/preview`、`POST /import/confirm`、`GET /api/invoices`、`GET /api/invoices/{id}` |
| service | `import_service.py` | 预览凭证（绑定操作者、文件名、文件摘要，30 分钟）、命名锁、去重分类、整批保存、发布事件 |
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
- 去重键 `invoice_key` = 发票代码 + 号码（数电票代码为空）。Excel 暂用固定账套标识 `lemon`；接入 open2 时与 API 账套对齐，同一张票按 `invoice_key` 识别。
- 原始数据摘要不含文件名与行号：同一张票重新导入时内容相同则跳过；内容不同视为冲突，整批拒绝，不覆盖已存发票。
- 柠檬云 Excel 不含购买方与币种：币种按人民币（CNY）保存，购买方为空（比对时记为"发票未提供"）。
- 发票金额为两位小数；超过两位或超出字段长度时预览即拒绝。
- 服务身份（`service:`）只读，不能确认导入。
- 已删除旧实现中没有任何调用方的"图片单票录入"（`import_image_snapshot`）。

## 公开接口（`public.py`）

- 事件 `InvoicesImported(invoice_ids)`：本次新增的发票 ID。
- `read_invoices(connection, invoice_ids)`：票头（状态、销售方、购买方及规范化名称、币种、价税合计、备注）与发票行（品名及规范化名称、规格、数量、单位、含税金额）。
- `lock_invoice(connection, invoice_id)`：在调用方事务中锁定票头（matching 审核分配时使用）。

## 依赖

`core/named_lock.py`（导入互斥）、`core/names.py`（名称规范化）、`core/events.py`。不读取其他模块。

## 验证

`backend/tests/test_invoice.py`（SQLite，仓库虚构的 `fixtures/lemon-invoices.xls` 与内存生成的 XLSX）：预览与确认、重复跳过、冲突整批拒绝、业务类型筛选、预览凭证与服务身份、列表筛选汇总与详情、事件、HTTP。

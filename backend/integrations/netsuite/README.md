# NetSuite 适配器

`auth.py`生成M2M签名；`client.py`维护Token缓存、HTTP请求、目标类型许可、超时与响应解析。保留现有SuiteTalk协议，不修改业务字段映射。

通过构造函数注入HTTPX客户端；测试使用MockTransport/FakeNS。此目录不判断用户审批或匹配金额，不自行重试写入。身份、字段许可和执行状态由业务模块再次校验。

验证：`npm.cmd run test:api` 中的签名、缓存、重定向与超时用例。

`client.vendor_bill_query` 使用主连接与服务端固定配置 `NETSUITE_VENDOR_BILL_QUERY_SCRIPT/DEPLOY`，只发送 `action=bills`、NS 供应商 ID `vendorId` 和母采购内部 ID 列表 `purchaseOrderIds`，复用限长、禁止重定向和不自动重试的 RESTlet 读取。source 校验版本 3 分组响应，不接受旧 `vendorCode`、`purchaseOrderNo` 请求或版本 2 响应。未配置返回 503，不转调旧保存脚本；业务契约与核验在 source，详见[供应商账单查询](../../../docs/ns-vendor-bill-query.md)。

## 原件只读下载

- `restlet_file.py`：子采购合同与报关资料共用的 RESTlet 读取步骤（GET 显式声明 JSON Content-Type、限长读取 JSON、兼容二次 JSON 字符串、解码并校验 PDF）。
- `subpo_contract.py`：子采购合同，按子采购单号在下载环境重新定位并核对供应商、报关单后取 PDF。
- `declaration_documents.py`（2026-10-23）：报关资料，按 CD 编号在下载环境重新定位报关单，并核对真实报关单号一致后才请求文件。

### 报关资料 RESTlet 约定（需 NS 侧部署）

配置 `NETSUITE_DECLARATION_DOC_SCRIPT` / `NETSUITE_DECLARATION_DOC_DEPLOY`（须同时填写），与子采购合同共用 `NETSUITE_SUBPO_CONNECTION_FILE` 专用只读连接，需要 `restlets` 与 `rest_webservices` 授权。

- 请求：`GET restlet.nl?script=…&deploy=…&id=<报关单 customrecord_swc_declare_record 内部 ID>&type=<类型>`，类型为 `customs_declaration`（报关单）、`sales_contract`（销售合同）、`invoice`（发票）。
- 响应：`{"id": "<同一内部 ID>", "type": "<同一类型>", "files": [{"filename": "…", "contentBase64": "<PDF base64>"}]}`；一类资料可返回多份，最多 10 份、合计不超过 20 MB，单份 PDF 不超过 7 MB。
- 旧 PDF 响应只保存校验通过的 PDF；`files` 为空返回“NS 中暂无该报关单的××文件”，ID、类型不符或 PDF 不完整一律不保存。文件名由系统按“类型_CD号[_序号].pdf”生成，不采用响应中的文件名。Excel 扩展见下节。

### Excel XML 扩展（2026-10-26）

上述旧 PDF 协议继续兼容。报关单和发票可在每个 `files` 项加入 `format: "excel_xml"`，正文为 UTF-8 SpreadsheetML 的 Base64；无 `format` 或值为 `pdf` 时仍按 PDF 校验。单份上限同为 7 MB。`declaration_file.py` 校验 XML 结构并拒绝 DTD/实体、公式及外部链接；不是通用 XLS/XLSX 上传入口。销售合同仍仅支持 PDF。

适配器内部返回 `files: [{content, format, extension}]`，task 据此生成 `.xls` / `.pdf` 文件名，不使用远端名称。先校验整组再返回，任一文件错误时不保存。

**状态（2026-10-26）：账户 5939865 已部署独立 Excel RESTlet（485/1）；真实报关单与发票下载、文件校验及共享盘保存已验证。任务队列状态联动与 Excel/WPS 视觉验收尚未验证。** 新 RESTlet 只实现报关单与发票，销售合同待接入。原 NS 脚本和按钮无需修改；新增接口的配置见 [外部下载接入说明](../../../netsuite/declaration_print/README.md)。未配置时任务详情显示“报关资料下载接口尚未配置”。

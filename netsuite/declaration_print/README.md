# 报关单与发票：外部下载接入

仅新增独立 RESTlet 及本目录的打印模块，原 NS 脚本和按钮保持不变。原打印在浏览器生成 Excel，没有可直接复用的服务端下载接口；新增接口沿用已核实的模板和字段，返回同格式 `.xls`（SpreadsheetML XML）。

**状态（2026-10-26）：账户 5939865 已部署，script=485、deploy=1。报关单和发票已通过真实接口及共享盘保存验证；销售合同打印来源仍待确认。**

## 接入步骤

1. 在 NS 文件柜新建独立目录，上传 `declaration_documents_restlet.js` 和 `declaration_print/` 下全部 `.js`，保持相对目录结构。不覆盖 `SWC_CS_DeclareButton.js`、`declare_common.js` 等原文件。
2. 为新文件创建 RESTlet 脚本及部署，授权现有集成角色读取相关记录。使用已有 M2M 凭证鉴权，不开放匿名访问。
3. 将实际部署编号填写到后端运行环境，沿用现有共享盘目录并重启后端：

```dotenv
NETSUITE_DECLARATION_DOC_SCRIPT=<新脚本的实际编号或ID>
NETSUITE_DECLARATION_DOC_DEPLOY=<新部署的实际编号或ID>
NETSUITE_SUBPO_ARCHIVE_ROOT=<现有共享盘根目录>
```

4. 用同一张报关单对比原按钮和新接口的 Excel，再测试共享盘落盘。后台仍通过现有任务队列自动下载；已失败的记录在任务页单项重试。

## 外部调用

向实际账套的 RESTlet 域名发送请求（域名以部署页面为准）：

```http
GET /app/site/hosting/restlet.nl?script=<新脚本ID>&deploy=<新部署ID>&id=<报关单内部ID>&type=invoice
Authorization: Bearer <现有M2M令牌>
Content-Type: application/json
Accept: application/json
```

`type=customs_declaration` 下载报关单，`type=invoice` 下载发票。返回：

```json
{
  "id": "870",
  "type": "invoice",
  "files": [{ "filename": "报关单发票打印.xls", "format": "excel_xml", "contentBase64": "<文件Base64>" }]
}
```

外部程序将 `contentBase64` 解码后写入共享盘。现有财务后端已完成此适配，复用下载队列、目录规则和重复下载保护；NS 本身不写共享盘。现有应用接口的登录权限不变，本次没有增加外部服务密钥调用应用接口的能力。

## 维护与验证

- `customs_reader.js`、`invoice_reader.js` 只读原字段；`*_template.js` 保存原模板；`*_excel.js`、`excel_template.js` 填充并转义文本；`document_service.js` 按类型生成文件。全部供新 RESTlet 使用。
- 模板依据 2026-10-26 只读取得的 `SWC_CS_DeclareButton.js`（文件 1954）和 `declare_common.js`（文件 1973）。原系统以后修改打印规则时，新增接口需单独同步。
- 保留原单价、行金额和表头取数规则，不重算数量×单价。原发票调用未设置 `option.title`，当前沿用原输出，需在真实验收时核对抬头。销售合同未接入时明确报错。
- `original-output.sha256.json` 记录原函数在合成数据上的输出摘要。运行 `npm.cmd run test:netsuite` 验证输出一致、特殊字符及错误参数；后端文件校验与归档测试见 `backend/tests/test_declaration_excel.py`。
- 后端兼容原 PDF 响应；Excel 仅限报关单和发票，单文件 7 MB。内容、格式或份数改变时拒绝覆盖已归档资料。

真实验收：`CD000959` 两类文件下载并通过后端校验；因缺少真实报关单号，不归档。`CD000954` 两类文件已通过同一适配器下载，并使用既有 `ContractArchive` 保存到配置的共享盘，写后摘要验证通过。此次直接验收没有修改任务资料状态；运行中的后端须重启以加载新增配置及 JSON 请求头修复，任务队列端到端状态尚未验收。Excel/WPS 中的布局、抬头与分页仍待人工核对。

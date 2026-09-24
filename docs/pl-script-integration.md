# 网站调用 NS 查询 JSON 接口

## 财务核对v3更新（2026-09-23）

两个正式页面独立导航：采购报关联查 `/pl-reconciliation` 调用 `POST /api/ns/pl-script-comparison` 保留平铺来源对照；财务核对 `/finance-reconciliation` 调用 `POST /api/reconciliation/query`，由reconciliation模块复用原business只读NS服务。财务核对使用已确认的三级展开，整单审核通过`POST /api/reconciliation/approve`保存到应用库，执行`npm.cmd run db:upgrade`增加三张审核表。详见[审核规则和表字段](../backend/modules/reconciliation/README.md)。

本次**本地代码已实现，NS端尚未上传**。部署包`outputs/finance-review-v3.zip`包含新版`pl_restlet.js`、`pl_trace.js`及说明。更新前核对现有共用查询服务版本；二者覆盖同一`pl_lookup`目录的对应文件，保持现有部署、配置、角色、账户不变。追溯脚本仅增加已确定关系的`customsIndex`，不改变配对或分摊算法。若NS仍是旧版本，网站可以查到原行，但不能按相邻行自动嵌套或整单审核。

v3保留17列字符串，新增：

- 组：`declarationId`（NS报关内部ID）、`recordNumber`（CD号）、`plNumbers`、`company`、`reviewIssues`。
- 行：`sourceKey`（原来源身份）、`customsRowId`（采购明确指向同组报关行；缺失为null）、`currency`（采购来源币种）。
- `customsRowId`由NS追溯时的`displayOrder.customsIndex`生成；不是网站通过顺序、品名或PL猜测。
- 没有来源诊断结果、诊断仍有待核实项或PL单号范围可能不完整时，返回`reviewIssues`。提交前后端还会按CD单独查询，内容变化即拒绝。

先使用同一个CD号对照NS与网站逐行数量/金额/币种及父子关系，再进行人工审核。不要用真实审批验证页面按钮；本次测试使用隔离数据。

## 本地接入验收状态

2026-09-23，本机应用库已升级到`0002_finance_review`，正式入口已能只读查询当前配置的沙箱账户`5939865-sb1`中的CD000630，返回3条报关行、4条采购行。实际接口仍是旧契约，页面显示待核实，未执行真实审批或NS写入。隔离合成来源已通过浏览器逐级展开、整单审批落库、重新查询、状态筛选、失败恢复及390像素布局检查；MySQL并发测试在随机独立测试库通过。NS v3上传和真实逐行对照仍待部署确认。

## 17列历史更新说明

网站出现“当前查询接口尚未提供单价和报关币种”表示本次响应仍是 `contractVersion: 1` 的15列。此前17列更新返回 `contractVersion: 2` 的17列，末两列直接读取共用服务的 `customsPrice` 和 `customsCurrency`；不在网站补算或将报关值填入采购行。本次同步采购空金额时含税单价返回空字符串，与NS页面、Excel一致，真实零金额仍正常返回。

部署包 `outputs/pl-restlet-17-columns.zip` 仅包含RESTlet入口和说明。覆盖实际RESTlet脚本记录引用的文件，放在共用 `pl_query_service.js` 同目录，保留部署编号、M2M权限和 `custscript_pw_config_file` 参数。随后在网站重新查询；单纯重启网站不会替换NS入口。若仍收到v1，核对后端配置的脚本／部署编号与实际覆盖文件是否对应；若返回 `SERVICE_VERSION_UNSUPPORTED`，说明RESTlet引用的共用服务仍不支持17列，需核对该目录，不能只改返回版本号。

报关源字段来自现有配置：`custrecord_swc_unitprice` 为单价、`custrecord_swc_currency` 为报关币种。共用空金额规则需使用已交付的 `2026-09-23-missing-purchase-amount-1` 服务及配套追溯模块；仅替换入口不会修复旧共用服务的空金额中断。此次未改配置或NS业务记录，未上传NS，真实外部调用待部署验收。

## 当前实现

原只读接口调用 `POST /api/ns/pl-script-comparison`，Python 校验身份与条件后，通过 M2M OAuth 2.0 调用 `pl_restlet.js` 的 POST 入口。RESTlet 仅依赖现有 `pl_query_service.js`，每次请求执行一次共用查询，返回 JSON。来源追溯、关联、数量与金额分摊、合并和行顺序仍由 NS 共用模块负责。

本接口不生成 Excel、不调用 `pl_excel.js`、不返回 Base64、`download` 或 `exportNotice`，不写业务记录或 File Cabinet。网站已移除导出按钮及专用样式。原 NS Suitelet 的页面、快照和 Excel 导出代码保留，本次未修改。

## 最小部署

1. 将 `scripts/netsuite/pl_restlet.js` 上传到当前 `pl_suitelet.js` 所在目录，使相对依赖 `./pl_query_service` 指向同一服务文件。
2. 共用服务需支持 `query(input, parameterPrefix)`，接受 `custscript_pw` 前缀，并输出 `TABLE_KEYS`（固定17列）、`complete`、`groups`、`counts`、查询范围及读取时间。用户提供的线上对应目录 `SuiteScripts/pl_lookup` 已具备这些能力。新版入口会先核对17列定义；旧服务不支持时返回 `SERVICE_VERSION_UNSUPPORTED`，应先核对差异，不要整包覆盖共用模块或切换查询模式。
3. 新建 RESTlet 脚本记录，选择 `pl_restlet.js`；建议脚本 ID 为 `customscript_pl_web_query`，部署 ID 为 `customdeploy_pl_web_query`，以 NS 实际保存的编号为准。
4. 在新脚本记录创建自由格式文本参数 `custscript_pw_config_file`，部署值填写原 Suitelet 的 `custscript_pl_config_file` 所指向的同一配置文件 ID。脚本参数不会跨记录自动共享。
5. 如果现有配置使用 savedSearch，另建 `custscript_pw_purchase_search`、`custscript_pw_customs_search` 参数，复制原 Suitelet 对应参数值；direct 模式只使用配置文件参数。本接口不要求切换 direct、不修改保存搜索。
6. 部署状态设为 Released，受众授权给实际 M2M 映射用户／角色；角色应拥有原查询所需数据权限。保留原 Suitelet 部署。集成启用 OAuth 2.0 RESTlets，不能使用仅限 Web Services 的角色。
7. 后端配置以下环境变量并重启。凭证只留在后端，浏览器不能提交脚本编号、账户、搜索编号或角色。

```dotenv
NETSUITE_SCOPE=rest_webservices,restlets
NETSUITE_PL_RESTLET_SCRIPT=customscript_pl_web_query
NETSUITE_PL_RESTLET_DEPLOY=customdeploy_pl_web_query
```

已有RESTlet部署时保留脚本记录、部署编号及参数。仅升级历史17列时只涉及入口；本次三级审核v3还需同步`pl_trace.js`的显式父行引用，具体以本文顶部v3步骤为准。

## 请求

```http
POST https://<account>.restlets.api.netsuite.com/app/site/hosting/restlet.nl?script=<script>&deploy=<deploy>
Content-Type: application/json
Authorization: Bearer <后端获取的访问令牌>
```

```json
{
  "type": "pl",
  "pl": "PL2601220005",
  "month": "",
  "createdFrom": "",
  "createdTo": "",
  "showIncomplete": true
}
```

`type` 支持 `pl`（PL单号）、`customsRecord`（NS报关记录号）、`declaration`（真实报关号），对应单号均放在 `pl` 字段。`month` 为 `YYYY-MM`；创建日期为 `YYYY-MM-DD`，必须成对。至少提供单号、月份或完整创建日期范围之一；多个条件同时生效。单号最多100字符，年份1900—2100。RESTlet拒绝额外字段，业务条件由共用服务再次校验。

## 响应

当前成功返回 `contractVersion: 3`（沿用v2的17列）、`complete: true`、`source: "netsuite-script"`，以及账户、查询编号、规范化条件、读取起止时间、耗时、月份字段说明、统计、报关单列表和分组有序行。后端继续兼容旧 `contractVersion: 1` 的15列响应。

- `counts`：`customs`、`purchase`、`groups`、`declarations`。
- `declarations`：每条含 `id`、`recordNumber`、`declarationNumber`、`date`、`created`。
- `groups`：每组含 `id`、`title`、`customsCount`、`purchaseCount`、`warnings` 和 `rows`。
- `rows`：每行含 `id`、`side`（customs/purchase）、`note`、`cells`。
- v2 的 `cells` 按固定17列返回字符串：报关单号、申报日期、PL、销售单、母采购单、子采购单、货源地、供应商、公司抬头、品名、型号、数量、单位、含税单价、总金额、单价、报关币种。末两列保留报关来源原值，采购行留空；数量和金额不转成浮点数。单价与含税单价是不同字段，不互相补值。
- v1 的 `cells` 仍必须为15列。网站保留原列，并提示末两列尚未接入；不会把缺少的接口字段视为已核实空值。各版本均严格校验每行列数，拒绝混合长度。

有范围但无结果时返回成功和空数组、零计数。查询失败时返回 `complete: false`、`error: {code, message}`，共用服务错误另含 `requestId`，不以空结果冒充成功。RESTlet可能通过HTTP 200承载此业务错误，Python同时检查HTTP状态与JSON的complete字段，并转换为网站错误响应。

Python核验账户、查询条件、行唯一性与统计一致性，并增加网站专用 `missingCells`（零起始列号）提示缺失字段。浏览器只负责显示，不重算金额。网站默认沿用NS的空白和行顺序，勾选“标记待确认字段”后显示缺失标记和字段清单；只有NS原备注增加表内备注行。失败不自动重试、不回退旧查询、不执行第二次查询。

## 验证与运行边界

### 已进入脚本后的错误排查

网站的 502 若包含查询编号，应在 RESTlet 部署执行日志中查找同编号的 `PL_QUERY_FAILED`。`CONFIG_FILE_PARAMETER_MISSING` 表示运行时没有取得 `custscript_pw_config_file` 的值；创建脚本参数定义后，还需在实际部署上填写原 Suitelet 使用的配置文件 ID。当前本地 `pl_config.json` 为 direct 模式，不需要保存搜索参数。

`stage=TRACE_SOURCES` 且 `code=QUERY_FAILED` 表示来源追溯期间发生未分类异常，不足以直接断定权限错误。使用 `2026-09-22-trace-diagnostic-1` 的 `pl_query_service.js` 和配套 `pl_trace.js` 后，NS 日志会补充受控的异常名称、记录类型、读取阶段和 API 操作；不会记录原始异常或业务值，也不会改变网页通用失败响应。原 Suitelet 成功而 RESTlet 失败时，核对实际执行角色、M2M 映射以及两入口加载的共用模块与配置。此诊断更新需部署到 NS 才生效，重启 Python 无法更新 NS 文件。

本地测试：`node --test tests/ns-pl-restlet.test.mjs tests/ns-pl-lookup.test.mjs tests/ns-pl-trace.test.mjs tests/ns-pl-direct.test.mjs tests/ns-pl-export.test.mjs`；后端 `npm.cmd run test:api`、`npm.cmd run lint:api`；前端 `npm.cmd run build`、`npm.cmd run lint`、`npm.cmd run typecheck`、`npm.cmd run test:reconciliation`。

部署后，使用同一账户、等效角色权限、同一单号及日期范围对照 NS 页面与网站的行序、数量和金额。角色或查询时点不同可能产生差异，两个请求不是同一事务快照。网站手动查询，不自动轮询；RESTlet仍占用账户并发额度，共用模块本身的诊断查询开销也保留。

用户提供的执行日志已确认 RESTlet 能进入共用查询，最近一次失败为 `TRACE_SOURCES` 阶段对 `customrecord_swc_declare_line` 的 `INSUFFICIENT_PERMISSION`。需在实际 M2M 执行角色上处理对应记录及关联记录的读取权限。本次17列入口尚需上传覆盖；权限恢复后的真实NS数据对照仍待验收，本地合成样本和模拟接口测试不代表线上已通过。旧 `/api/ns/pl-comparison` 保持原契约供已有调用方兼容，正式网站不再调用；其旧导出逻辑不在本次删除范围。

官方参考：[RESTlet POST入口](https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/section_4407966008.html)、[部署RESTlet](https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/section_4618456517.html)、[OAuth 2.0授权](https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/section_158263562006.html)。

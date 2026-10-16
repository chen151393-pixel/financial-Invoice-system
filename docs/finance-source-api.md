# 外部查询接口：报关原始行

状态：2026-10-16 已补充结构诊断与部署子列表配置；用户替换脚本后，正式账套 5939865 的 839、840 两张单诊断成功，原始子列表仍不可见，普通读取返回 RAW_SUBLIST_UNAVAILABLE。同步保存已针对该结构缺失单独标记追溯待补齐，其他基础数据错误仍阻止保存。入口为 [`netsuite/finance_source_restlet.js`](../netsuite/finance_source_restlet.js)，SuiteScript 2.1 RESTlet；仅依赖内置 `N/record`、`N/runtime`，上传单个文件即可，不依赖 PL 联查脚本。

本接口供后端读取报关单原始来源。单据类型固定为 `customrecord_swc_declare_record`，子列表默认使用历史脚本中的 `recmachcustrecord_swc_sl_relate`，可通过部署参数指定经核实的实际标识。默认值不代表已在正式环境验证可见。接口只读取，不创建、修改、删除、审核记录，也不计算匹配或分摊。读取到完整来源不代表财务审核通过。

## 现有脚本修复与诊断

截图中的脚本名为 `finance_restlet`，脚本 ID 为 `customscriptfinance_restlet`，文件为 `finance_source_restlet.js`。已有脚本应替换其引用的同一文件，保留现有脚本和部署 ID，无需再新建部署；截图只有脚本页，部署 ID 须到「部署」页签核对。

1. 将本仓库修订后的文件上传替换截图中的脚本文件，确认仍为 SuiteScript 2.1、POST 入口。
2. 使用原认证、原 External URL 发送下述诊断请求。示例 ID 须替换为待排查的两张报关单内部 ID，不是报关编号。

   ```json
   {"action":"diagnose","declarationIds":["839","840"]}
   ```

3. 对比每张单 `diagnostics` 中的 `bodyFields`、`expectedSublistVisible`、`sublists[].sublistId`、`fields` 和 `lineCount`。`identityField` 与 `missingFields` 仅检查现有字段契约，字段吻合不代表已证明该列表就是原始来源；脚本不会自动选择其他列表。
4. 如果确认实际原始子列表使用不同标识，在脚本「参数」页创建自由格式文本参数，ID 为 `custscript_fin_source_sublist`（非公司／用户偏好参数），再在对应部署的「参数」页填写实际的 `recmachcustrecord_...` 标识。空值继续使用原默认值。参数只在 NS 部署端配置，外部请求不能传子列表或字段映射。
5. 重新调用原读取请求 `{"declarationIds":["839","840"]}`，核对真实行 ID、Packing 引用、数量及报关归属；仍须完整字段与唯一身份检查通过，才能接入保存。

若诊断中完全没有原始子列表，不能仅凭此认定权限不足。需结合当前调用角色、实际子记录定义及页面生成明细的脚本确认读取路径；页面可见不保证 `record.load` 暴露同一列表。未核实前不能填写猜测的标识，也不能将读取失败改为空成功。若实际字段契约不同，需要依据诊断结果单独调整映射和测试。

### 诊断响应

诊断返回 `contractVersion: 1`、`account`、`mode: "diagnose"`、`complete: false`、`diagnosticsComplete` 和 `diagnostics`，**不返回 `declarations` 或任何业务字段值**。`diagnosticsComplete` 只表示结构检查是否执行完整，不表示原始行已找到或可落库；现有来源读取器会拒绝诊断响应。

每项含请求的 `id`；成功加载后含 `expectedSublistId`、`bodyFields`、`sublists`、`inspectionComplete`、`issues`，成功枚举列表后另含 `expectedSublistVisible`。每个子列表含 `sublistId`、`fields`、`lineCount`、`issues`，字段读取成功后另含 `identityField`、`missingFields`。读取失败的字段列表／行数保留 `null`，不会冒充空列表或零行。

`issues` 使用固定代码：`HEADER_LOAD_FAILED`（报关头加载失败）、`BODY_FIELDS_READ_FAILED`（单头字段枚举失败）、`SUBLISTS_READ_FAILED`（子列表枚举失败）、`FIELDS_READ_FAILED`（子列表字段枚举失败）、`LINE_COUNT_READ_FAILED`（行数不可读取或无效）、`QUERY_LIMIT`（额度不足）。单张失败不阻断其他单据诊断；诊断同样最多 20 张，不输出平台异常原文。

## 部署

1. 在需要调用的 NS 账套上传 `finance_source_restlet.js` 到 File Cabinet 的 SuiteScripts 目录。
2. 新建 RESTlet 脚本记录，选择该文件。建议脚本 ID：`customscript_finance_source_read`。
3. 新建部署，建议部署 ID：`customdeploy_finance_source_read`，启用部署并将状态设为 Released。记录实际生成的外部 URL。
4. 受众仅授权实际调用的 M2M 用户／角色；该身份须有报关头和原始子列表所需读取权限。沿用读取角色，不改为管理员执行，不开放匿名访问。
5. OAuth 2.0 集成须启用 RESTlets，证书映射须属于当前账套。正式与沙箱分别核对授权，不能仅切换 URL 就假定认证可用。
6. 用当前账套中一张已知报关单的内部 ID 验收：核对返回 account、recordNumber、原始行 ID、数量及 Packing 引用，再接入业务保存。

上述 ID 仅供新建时参考；已有部署必须填写实际 ID，例如截图的脚本 ID 是 `customscriptfinance_restlet`。不能用填写配置代替部署：

```dotenv
NETSUITE_SCOPE=rest_webservices,restlets
NETSUITE_FINANCE_SOURCE_SCRIPT=customscript_finance_source_read
NETSUITE_FINANCE_SOURCE_DEPLOY=customdeploy_finance_source_read
```

PL 接口仍使用独立的 `NETSUITE_PL_RESTLET_SCRIPT` / `NETSUITE_PL_RESTLET_DEPLOY`。本接口版本 1 与 PL 版本 3 是两份独立契约。本系统基础落库不再强制依赖本接口和 PL v3；精确追溯完整时才标记为 matched，部署本接口不会自动升级 PL。

## 调用

使用部署记录显示的 External URL。示例地址（脚本和部署 ID 以实际值为准）：

```text
正式：https://5939865.restlets.api.netsuite.com/app/site/hosting/restlet.nl?script=customscript_finance_source_read&deploy=customdeploy_finance_source_read
沙箱：https://5939865-sb1.restlets.api.netsuite.com/app/site/hosting/restlet.nl?script=customscript_finance_source_read&deploy=customdeploy_finance_source_read
```

请求方法为 POST，`Content-Type: application/json`、`Authorization: Bearer <当前账套访问令牌>`。认证由 NS 平台完成，脚本不保存客户端密钥或自行校验密码。外部系统须在服务端获取令牌。

```json
{"declarationIds":["839"]}
```

`declarationIds` 是 1～20 个不重复的正整数**字符串**，每个最多 20 位。这里填内部 ID，不是 `CD000839` 记录编号；示例 ID 不保证在每个账套存在。另可提供 `action`，省略或 `"read"` 表示读取，`"diagnose"` 表示结构诊断。不接受 SQL、其他记录类型、客户端子列表或额外字段。需要更多单据时由调用方分批请求；每批累计最多 2,000 行，超限返回失败，不截断数据。

## 返回字段

成功返回 `contractVersion: 1`、`complete: true`、`account`（例如 `5939865-sb1`）、`declarations`。每张单包含 `id`、`recordNumber`、`rows`；可见且确实为空的子列表返回 `rows: []`，不可见的子列表返回失败。

每行所有字段均为字符串，空值为 `""`，零数量为 `"0"`。数量直接取 NS 读取值的字符串表示，不做浮点运算，也不承诺恢复 NS 已转换为数字前的末尾零。

| 返回字段 | 中文含义 | NS 来源字段 |
| --- | --- | --- |
| id | 原始报关行内部 ID | 子列表 id，缺少时使用 internalid |
| declarationId | 所属报关单内部 ID | 请求中的报关头 ID |
| plId | PL 引用 ID | custrecord_swc_packing_main |
| packingId | Packing 行引用 ID | custrecord_swc_packinglist |
| companyId | 公司引用 ID | custrecord_swc_declare_company |
| fulfillmentId | 履行单引用 ID | custrecord_swc_fulfillment_id |
| fulfillmentLine | 履行行引用 | custrecord_swc_fulfillment_line |
| itemId | 货品引用 ID | custrecord_swc_declare_item |
| name | 开票／来源品名 | custrecord_details_item_name |
| sourceQuantity | 原装箱数量 | custrecord_swc_packingqty_2 |
| declarationQuantity | 申报数量 | custrecord_swc_details_packingqty |
| declarationUnitId | 申报单位 ID | custrecord_swc_details_unit |
| declarationModel | 申报型号 | custrecord_swc_details_model |
| parentPurchaseId | 母采购单引用 ID | custrecord_swc_detail_purchase |

调用方须检查 `complete === true`、契约版本、返回账套与请求一致，并核对单据范围和唯一行身份。本系统同步保存对同账套、版本 1 的 `RAW_SUBLIST_UNAVAILABLE` / `RAW_FIELDS_UNAVAILABLE` 单独处理：不使用原始行、不调用依赖它的 v3 追溯，基础数据通过其他校验后可保存为追溯待补齐；其他错误仍拒绝本页保存。只检查 HTTP 200 不够：脚本校验失败也可能由 NS 以 HTTP 200 返回；认证、权限和平台错误可能返回非 2xx 或平台错误体。

## 错误码

读取失败返回 `contractVersion`、`account`、`complete: false` 和 `error: {code, message}`，不会返回已经读出的部分单据。子列表不可见或缺字段时附带当前失败单据的 `error.diagnostic`（结构与诊断单项相同）；缺字段时还会返回 `error.missingFields`、`error.identityFieldMissing`。排查全部请求单据请使用诊断请求。

| code | 含义与处理 |
| --- | --- |
| INVALID_INPUT | 参数类型、数量、ID 格式、重复或额外字段不合法；修正请求 |
| INVALID_SOURCE_CONFIG | 部署子列表参数不是有效的 `recmachcustrecord_...` 标识或超过 200 字符；核实配置 |
| QUERY_LIMIT | 累计行数超过上限，或脚本剩余额度不足；缩小批次；单张超限须另行设计分页 |
| RAW_SUBLIST_UNAVAILABLE | 配置的子列表未出现在当前身份可见列表中；根据诊断核实标识、读取路径和权限 |
| RAW_FIELDS_UNAVAILABLE | 原始行身份或来源字段不完整；核实账套字段与角色权限 |
| INVALID_SOURCE_ID | 原始行 ID 无效或整批中重复；核实源数据 |
| HEADER_FIELDS_UNAVAILABLE | 报关记录编号不可读取；核实报关头数据和权限 |
| SOURCE_READ_FAILED | 单据不存在、读取权限不足或 NS 读取异常；核实 ID、权限及 NS 日志 |

HTTP 404 需要核对账套、脚本／部署 ID、启用状态和受众；仅凭 404 不能断言脚本不存在。错误响应不回显令牌、原始平台异常、业务正文或堆栈。

## 本地验证与交付范围

```powershell
node --test netsuite/tests/ns-finance-source.test.mjs
```

测试使用模拟 NS API，覆盖只读边界、参数限制、可见空列表、缺字段、跨单据重复行、累计行数限制和中途失败整批不返回，以及批量结构诊断、局部诊断失败、部署参数切换与拒绝猜测其他列表。真实子列表可见性、字段权限、OAuth 授权及平台运行情况仍须部署后验收。本次修改不代表已更新正式部署或已落库。

认证及 RESTlet 部署参考：[Oracle OAuth 2.0 认证说明](https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/section_158272429269.html)、[Oracle RESTlet 接口示例](https://blogs.oracle.com/developers/augment-netsuite-rest-functionality-with-restlet)。

结构与配置 API：[Oracle N/record](https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/section_4267255811.html)、[Oracle Script.getParameter](https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/section_4296661592.html)。

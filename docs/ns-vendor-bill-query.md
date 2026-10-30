# 供应商账单只读查询接入

状态：2026-10-28 版本 3 查询已在 NS `script=486&deploy=1` 部署，帝奇母单样本已通过真实查询和后端校验。远程脚本修订 `2026-10-28.3` 已合入，本次未核实线上修订号。审核绑定、持久准备任务和不可变账单分配方案已接入[阶段 A/B](ns-writeback-prepare.md)；NS 写入（阶段 C）代码已完成，写入脚本待部署验收。

2026-10-30：仓库只读脚本修订为 `2026-10-30.4`，在版本 3 上新增可选 `invoiceNumber` 与 `registrationCheck`。本次未部署至 NS；回写查询启用此核对须按[部署说明](ns-writeback-prepare.md#12-ns-端)先更新只读脚本及记录查看权限。

## 本阶段范围

- [NS RESTlet](../netsuite/vendor_bill_query_restlet.js)：按供应商与母采购内部 ID 查询，只接受 `action=bills`；依赖内置 `N/search`、`N/runtime`、`N/log`，不依赖现网 `VendorInvoice.js`。作废标志通过独立筛选搜索取得，发票明细逐行读取后合计。原始请求、响应、日志及部署要求见[版本 3 接口说明](ns-vendor-bill-query-api.md)。
- [后端 Service](../backend/modules/source/service/vendor_bill_query_service.py)：属于 source，保持 `POST /api/source/vendor-bills/query`。复用主连接、认证、限长与不重试的 RESTlet 读取；不连接业务库、不保存候选、不改变审核。
- [核对工具](../scripts/ns_vendor_bill_query_check.py)：调用已运行后端，按母单核对状态、账单 ID 与金额，将结果保存到本地 JSON。

仓库调用方为核对工具及测试，未接入业务前端。原版本 1/2 未部署，已同步替换全部调用方，不保留旧字段兼容；旧 `vendorCode`、`purchaseOrderNo` 请求及版本 2 响应直接拒绝。无需数据库迁移。

## 后端请求

已登录用户或现有服务身份调用，Content-Type 为 `application/json`：

```json
{
  "vendorId": "123",
  "purchaseOrderIds": ["456", "789"]
}
```

- `vendorId` 为 NS 供应商内部 ID；`purchaseOrderIds` 为 1–20 个不重复的母采购内部 ID。
- 可选 `invoiceNumber` 为 1–100 字符的完整发票号码字符串，保留前导零，不接受首尾空格和控制字符；提供时按同供应商、同完整号码、未停用查找 `customrecord_swc_vendor_invoice`。回写队列必传此参数；普通账单查询可省略。
- 每个 ID 必须是 1–20 位、不带前导零的正整数**字符串**。不接受数字类型、空格、编码、单号、名称或额外参数。
- 后端固定补充 `action: "bills"`；调用者不能指定账套、URL、脚本/部署编号或写动作。
- 本地身份取值：供应商取 `source_suppliers.ns_internal_id`，母采购取 `source_parent_orders.ns_internal_id`，并核对同一 `ns_account`。本地表主键、`order_no` 和子采购带显示前缀的 `parent_order_no` 都不是该参数。
- 本独立查询接口接收显式 NS ID；已接入的回写准备队列通过 source 门面从整票审核快照取得身份并核验关系。任意 ID 的只读查询不能作为写入授权。

## 后端响应

保留版本 3 原始分组结构，新增中文说明与展示字段：

| 字段 | 说明 |
| --- | --- |
| `contractVersion / complete / source` | 固定为 `3 / true / vendor-bill-query`，严格检查类型 |
| `account / query` | 必须与服务端主连接及本次请求相符 |
| `registrationCheck` | 请求包含 `invoiceNumber` 时必返 `{ invoiceNumber, records: [{ id, number, date }] }`，无登记明确返回空数组；号码须与请求完整一致。未请求时不返回核对对象 |
| `readStartedAt / readCompletedAt` | 有时区且顺序有效的读取窗口，不是跨表原子快照 |
| `status / vendor` | `OK`＋供应商对象；或 `VENDOR_NOT_FOUND`＋null，此时母单列表为空 |
| `purchaseOrders[]` | 按请求顺序完整返回，每项有 `id / status / reason / bills`；找到的母单另含编号、供应商、公司及币种 |
| `purchaseOrders[].bills[]` | 原始账单身份、审批、作废、税额、`amounts / details / consistent`；另加币种、展示金额及 `issues` |
| `queryId / reason / warnings` | 本地追踪 ID、中文结果说明及查询边界；不是锁或回写凭据 |
| `writeback` | 始终 `allowed: false`，附未接入审核/回写的原因 |

母单状态为 `FOUND`、`NO_BILLS`、`PO_NOT_FOUND`、`VENDOR_MISMATCH`。不存在的母单只含 ID、状态、空账单与中文原因；供应商不符时不返回账单。`OK` 仅表示完成查询，各母单可能有不同状态。没有旧版顶层 `bills / vendors / reasonCode`。

展示金额 `totalInvoiceAmount / receivedInvoiceAmount / availableInvoiceAmount` 分别取 `amounts.payable / received / available`，均保留两位小数字符串，不再对旧浮点结果舍入。后端用 Decimal 校验：

- 剩余金额＋非贷项核销金额＝应收金额；应收－已收＝可收。
- `consistent` 必须与“有效明细合计＝已收金额”的实际比较一致；明细数为 0 时合计须为 0。
- 账单供应商、母单、公司与币种不能越界；母单不能遗漏、重复、乱序或额外返回；全批最多 200 张账单，账单 ID 全批唯一。

正确标记为 `consistent: false` 的历史差异会返回并提示财务核实；伪造的一致性标志、金额算式错误或不完整结果整批返回 502，不泄露部分候选。非人民币/未知币种、未批准、作废、非正向额度、缺少子采购精确关联都会提示问题，仍不允许回写。零税额账单照常返回且不提示问题（2026-10-28 确认采购税额为 0 也须登记）。

HTTP 400：请求非法；401/403：现有认证/授权拒绝；503：配置或认证条件不足；502：NS 查询失败、超时、超限或契约/身份/金额不一致。错误沿用 `{ "error": "中文说明" }`，不透传 NS 异常原文，不重试、不切换其他账套或旧保存入口。

## 查询边界与部署

新版返回母单下全部可见账单，不按日期、零税额或可收金额为零过滤。空结果不再由旧平台筛选造成，但仍受查询身份权限影响，不能据此证明整个 NS 账套绝对不存在该账单。金额口径、贷项与非人民币处理须在 NS 核实；查询不占用额度。

NS 管理员按[部署说明](ns-vendor-bill-query-api.md#部署待-ns-管理员执行)上传单个脚本并建立独立 RESTlet，核实供应商、采购订单、供应商账单和有效发票明细的只读权限。后端配置：

```dotenv
NETSUITE_VENDOR_BILL_QUERY_SCRIPT=<脚本内部ID或customscript ID>
NETSUITE_VENDOR_BILL_QUERY_DEPLOY=<部署内部ID或customdeploy ID>
NETSUITE_SCOPE=rest_webservices,restlets
NETSUITE_WRITE_ENABLED=false
```

两个编号须同时填写，默认空值返回 503，重启后端生效。使用主连接 `NETSUITE_ACCOUNT_ID` 及其 M2M 凭证，不继承 `NETSUITE_SUBPO_CONNECTION_FILE` 下载专用连接；不得为此功能擅自切换主连接账套。无论全局写入开关如何设置，本接口只读。

## 部署后只读样本对照

准备 1–20 个样本，覆盖多母单、单/多账单、无账单、母单不存在、供应商冲突、零税额、已收齐及历史明细差异。参考值来自同账套、同母单的 NS 页面和独立记录，记录核对时间与操作者；旧勾选平台会过滤部分账单，不能只用其可见列表判断完整性。以下为虚构示例：

```json
[
  {
    "name": "按母单核对",
    "query": {"vendorId": "1", "purchaseOrderIds": ["10"]},
    "expected": {
      "status": "OK",
      "purchaseOrders": [{
        "id": "10",
        "status": "FOUND",
        "bills": [{
          "billId": "100",
          "totalInvoiceAmount": "1200.10",
          "receivedInvoiceAmount": "1100.50",
          "availableInvoiceAmount": "99.60"
        }]
      }]
    }
  }
]
```

保存为 `cases.json`，在项目根目录运行（输出文件须不存在且父目录已存在）：

```powershell
node scripts/python.mjs -m scripts.ns_vendor_bill_query_check --cases cases.json --expect-account <目标账套> --output bill-query-result.json
```

工具通过 `APP_ORIGIN` 与 `SERVICE_API_KEY`（至少 32 字符）调用后端，不自行启动应用、迁移或后台线程。再次校验账套、查询范围及结果完整性，逐母单比较状态、账单集合与 Decimal 金额。输出 `MATCH / DIFFERENT / NOT_COMPARED / ERROR`；只有全部与独立参考一致才退出 0，缺参考或失败退出 2。结果含业务数据，仅保存到受控位置。

## 验证与未完成项

```powershell
npm.cmd run test:netsuite
node scripts/python.mjs -m pytest backend/tests/test_vendor_bill_query.py backend/tests/test_vendor_bill_query_check.py
npm.cmd run test:api
npm.cmd run lint:api
```

测试覆盖版本 3 请求、分组响应、金额、状态/身份一致性、认证与核对工具，以及同号登记核对。旧版本的历史测试数字不代表本版本结果。MockTransport、Node VM 与隔离 SQLite 不能替代 NS 部署、实际权限和金额对照。本次不涉及 MySQL 并发或真实 NS 写入；审核准备队列及业务界面见回写模块文档。

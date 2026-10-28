# 外部查询接口：按母单查询供应商账单

状态：2026-10-28 已部署 `script=486&deploy=1`；母单 `YE-DQ20260624-Z010` 的真实查询及后端校验已通过。远程修订 `2026-10-28.3` 已合入本地，修复无效 `voided` 结果列与明细分组汇总；本次未核实线上修订号。入口为 [`netsuite/vendor_bill_query_restlet.js`](../netsuite/vendor_bill_query_restlet.js)，SuiteScript 2.1 RESTlet，依赖内置 `N/search`、`N/runtime`、`N/log`。用途见[NS 供应商账单回写方案](ns-vendor-bill-writeback-plan.md)。

接口只读取，不创建、修改或删除任何记录，也不判断账单能否回写；判定规则在后端。返回结果不是回写任务号，也不是写入授权。

## 与旧查询脚本的区别

旧脚本按“供应商 ID + 母单号”调用现网 `VendorInvoice.js` 的 `getData`。本脚本改为：

| 项目     | 旧脚本                                        | 本脚本                                             |
| -------- | --------------------------------------------- | -------------------------------------------------- |
| 查询条件 | 母单号（`tranid` 可能重复）                   | 母单 NS 内部 ID，一次最多 20 个                    |
| 返回范围 | 跳过税额为 0、可收为 0、2025-07-01 以前的账单 | 母单下全部供应商账单，不按日期、税额、可收金额过滤 |
| 额度计算 | 平台的浮点加减                                | 口径相同，换成整数分计算，返回两位小数字符串       |
| 依赖     | 必须与 `VendorInvoice.js` 放在同一目录        | 不依赖现网平台脚本                                 |
| 补充信息 | —                                             | 审批状态、是否作废、是否有税额、明细合计与是否一致 |

## 请求

```json
{ "action": "bills", "vendorId": "123", "purchaseOrderIds": ["456", "789"] }
```

- `vendorId`：NS 供应商内部 ID（`source_suppliers.ns_internal_id`）。
- `purchaseOrderIds`：母采购单内部 ID（`source_parent_orders.ns_internal_id`），1～20 个且不重复。
- 不接受其他字段；格式不符时返回 `INVALID_REQUEST`，不发起任何检索。

## 响应

```json
{
  "contractVersion": 3,
  "source": "vendor-bill-query",
  "account": "5939865",
  "complete": true,
  "status": "OK",
  "vendor": { "id": "123", "code": "V123", "name": "供应商名称" },
  "purchaseOrders": [
    {
      "id": "456",
      "number": "PO456",
      "vendorId": "123",
      "subsidiaryId": "3",
      "currencyId": "1",
      "currencyName": "人民币",
      "status": "FOUND",
      "bills": [
        {
          "billId": "9001",
          "billNumber": "BILL9001",
          "vendorId": "123",
          "purchaseOrderId": "456",
          "subPurchaseOrderId": "",
          "subsidiaryId": "3",
          "currencyId": "1",
          "currencyName": "人民币",
          "approvalStatus": "2",
          "voided": false,
          "hasTax": true,
          "amounts": {
            "remaining": "200.00",
            "applied": "1000.10",
            "payable": "1200.10",
            "received": "1100.50",
            "available": "99.60"
          },
          "details": { "count": 2, "total": "1100.50" },
          "consistent": true
        }
      ]
    }
  ]
}
```

- 响应另含 `query`（规范化后的请求）、`readStartedAt`、`readCompletedAt`。调用方必须先检查 `complete`。
- `status`：`OK`，或 `VENDOR_NOT_FOUND`（供应商不存在或已停用，此时不再检索采购单和账单）。
- 每个母单按请求顺序返回，`status` 为：
  - `FOUND`：有账单；
  - `NO_BILLS`：母单存在、供应商一致，但还没有账单；
  - `PO_NOT_FOUND`：母单不存在；
  - `VENDOR_MISMATCH`：母单属于其他供应商，不检索它的账单。
- 账单字段：
  - `subPurchaseOrderId`：账单上的子单字段，2026-04 起通常为空。
  - `approvalStatus`：`1` 待审批、`2` 已批准、`3` 已拒绝，空为无审批流程。
  - `hasTax`：税额是否不为 0。现网勾选页面不显示税额为 0 的账单。
- 金额口径（与现网 `VendorInvoice.js` 的 `handleJson` 相同）：
  - `remaining`：账单剩余未付金额；
  - `applied`：核销到账单的非贷项交易金额合计（付款等），贷项不计入；
  - `payable`：应收票金额 = `remaining` + `applied`；
  - `received`：累计已收票金额 `custbody_swc_vendor_amount`；
  - `available`：本次可收 = `payable` − `received`，可能为 0 或负数，由后端判定。
- `details`：有效发票明细（`customrecord_swc_vendor_invoice_detail`）的条数和“本次收”合计。`consistent` 表示累计已收票金额与明细合计是否相等，不相等的账单回写前须由财务处理。
- 非人民币账单的金额币种口径尚未在 NS 核实。已登记的账单全部是人民币，后端首期只处理人民币。

## 错误

失败时 `complete: false`，`error.code` 为固定代码，不输出 NS 异常原文，也不返回部分结果：

| 代码              | 含义                                                         |
| ----------------- | ------------------------------------------------------------ |
| `INVALID_REQUEST` | 请求格式不符                                                 |
| `INVALID_RESULT`  | 检索结果异常：金额格式不符、身份重复、同一账单的展开行不一致 |
| `QUERY_LIMIT`     | 超过 200 张账单、1000 行检索结果，或脚本剩余额度不足         |
| `QUERY_FAILED`    | 其他 NS 异常                                                 |

NS 执行日志中，成功为审计级 `VENDOR_BILL_QUERY_OK`，失败为错误级 `VENDOR_BILL_QUERY_FAILED`。日志包含 `revision`、`stage`、通过校验的查询 ID 和耗时；失败另含原始错误名称、消息及截断堆栈。接口仍只输出固定错误码，不记录原始请求、认证信息或完整业务响应。部署日志级别设为“审计”即可查看成功与失败。

`voided` 不可作为 `N/search` 结果列。修订 `.3` 使用独立搜索的 `voided is T` 筛选获取已作废账单，日志阶段为 `voided_lookup`；不再依赖 `.2` 的 `N/query` 补读方案。发票明细不按账单字段 GROUP 汇总，改为逐行读取后按整数分合计，最多 5000 条；超限整批失败。

## 部署（待 NS 管理员执行）

已有部署无需重建：在 File Cabinet 覆盖原脚本文件，保留 `script=486&deploy=1`，下一次查询日志应显示 `revision=2026-10-28.3`。以下步骤用于首次部署。

1. 上传 `vendor_bill_query_restlet.js` 到 File Cabinet 的 SuiteScripts 目录。
2. 新建 RESTlet 脚本记录，建议脚本 ID：`customscript_vendor_bill_query`。
3. 新建部署，建议部署 ID：`customdeploy_vendor_bill_query`，状态设为 Released，部署受众包含系统使用的 M2M 角色。
4. 角色需要查看权限：供应商、采购订单、供应商账单、`customrecord_swc_vendor_invoice_detail`，并能通过 SuiteQL 读取交易的 `id`、`voided`。
5. 部署后先用一个已知母单发起请求，与 NS 页面上该母单的账单、供应商开票平台中的“已收／可收”逐项核对。

后端只读调用与配置项已在本地接入：`POST /api/source/vendor-bills/query` 接收同样的 `vendorId`、`purchaseOrderIds`，由适配器固定补充 `action=bills`；保留本页版本 3 分组结构，并增加中文说明、展示金额、问题提示和 `writeback.allowed=false`。配置、响应校验及样本核对工具见[后端接入说明](ns-vendor-bill-query.md)。旧单号参数和版本 2 响应不再接受。账单 ID 持久同步、审核绑定与回写队列仍待实现；本地接入不代表已部署或真实联调。

## 验证

```bash
node --test netsuite/tests/ns-vendor-bill-query.test.mjs
```

测试用伪造的 `N/search`、`N/log` 覆盖：按母单返回、额度计算与贷项排除、不按日期和税额过滤、多母单状态、请求与结果校验、1000 行分批探测、明细 5000 条上限、作废筛选与分阶段日志。搜索模拟器明确拒绝 `voided` 结果列，保留帝奇母单样本测试。

真实只读核对样本：母单 `YE-DQ20260624-Z010`（308488）、供应商 8879、账单 `VENDBILL35675`（395762）。2026-10-28 15:30（北京时间）RESTlet 返回 `complete=true/status=OK`，后端校验通过；应收票 11184.68、已收票 0、可收 11184.68、未作废、无发票明细。响应不含脚本修订号，故不能据此证明线上为 `.3`。尚缺子采购精确归属，本次未回写。

# 外部查询接口：按母单查询供应商账单

状态：2026-10-28 已实现并通过本地单元测试，**尚未部署到 NS，也未联调**。入口为 [`netsuite/vendor_bill_query_restlet.js`](../netsuite/vendor_bill_query_restlet.js)，SuiteScript 2.1 RESTlet，只依赖内置 `N/search`、`N/runtime`，上传单个文件即可。用途见[NS 供应商账单回写方案](ns-vendor-bill-writeback-plan.md)第 3.1、3.3 节。

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

## 部署（待 NS 管理员执行）

1. 上传 `vendor_bill_query_restlet.js` 到 File Cabinet 的 SuiteScripts 目录。
2. 新建 RESTlet 脚本记录，建议脚本 ID：`customscript_vendor_bill_query`。
3. 新建部署，建议部署 ID：`customdeploy_vendor_bill_query`，状态设为 Released，部署受众包含系统使用的 M2M 角色。
4. 角色需要查看权限：供应商、采购订单、供应商账单、`customrecord_swc_vendor_invoice_detail`。
5. 部署后先用一个已知母单发起请求，与 NS 页面上该母单的账单、供应商开票平台中的“已收／可收”逐项核对。

后端调用和配置项尚未接入，在“账单 ID 同步与只读对照”（回写方案第 6 节第 1 期）中实现。

## 验证

```bash
node --test netsuite/tests/ns-vendor-bill-query.test.mjs
```

测试用伪造的 `N/search` 覆盖：按母单返回、额度计算与贷项排除、不按日期和税额过滤、已登记满与未审批账单照常返回、多母单状态、请求校验、金额与结果异常、检索超限与异常码。

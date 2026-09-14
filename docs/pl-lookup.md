# PL 单联查

> 当前前端：旧“记录校对与写回”和“PL 单联查”页面已移除，下文涉及这些页面的操作仅为历史说明。后端接口与配置继续保留；当前页面 `/pl-reconciliation` 只提供实时查询和导出。

后续用户确认的固定 15 列上下拼表样式见 [存储执行方案第6.1节](document-storage-execution-plan.md#61-用户确认的拼表版式待实现)。当前页面仍为通用来源明细列表，未实现跨行单价与采购汇总规则。

## 已实现

登录后选择“PL 单联查”导航，输入 PL 单号。接口复用当前账户的 NS M2M 认证，精确查询 PL → 子采购订单 → 采购货品行，以及采购单引用的报关单 → 报关明细。报关明细再次校验 PL，按报关单内部 ID、PL、公司归组，每条来源行只出现一次。

本功能属于 business 模块，实时读取与本地保存复用 `pl_reader.py`。已新增独立MySQL保存和本地查询入口，详见 [PL保存说明](pl-storage.md)。没有数据表迁移，没有 NS 写入、商品自动配对、金额分摊或单价计算。金额以源记录十进制文本返回，币种单独展示。它是当前系统的模块，不是 NS 原生已保存搜索。

## 配置

### 本项目已核实的映射

2026-09-14 已将当前沙箱 `5939865-sb1` 的真实字段配置到本机根目录 `.env` 的 `NETSUITE_PL_LOOKUP`，并保留、补齐 `NETSUITE_RECORD_TYPES`。可读副本见 [完整映射 JSON](netsuite-pl-lookup.json)；这个 JSON 文件供查阅和配置复制，后端不会自动加载它，实际生效来源仍是环境变量。`.env.local` 和进程环境变量会覆盖 `.env`，其他服务器需要单独配置并重启。

| 数据 | 记录类型 | 关键关联字段 |
| --- | --- | --- |
| PL 主表 | `customrecord_swc_packing` | 单号 `name` |
| 子采购订单 | `customrecord_swc_subpo` | PL `custrecord_swc_subpo_plnum`；报关单 `custrecord_swc_subpo_baoguannum`；公司 `custrecord_swc_subpo_class` |
| 采购货品行 | `customrecord_swc_subpo_item` | 所属采购单 `custrecord_swc_subpo_main` |
| 报关单 | `customrecord_swc_declare_record` | 真实报关号 `custrecord_swc_realno`；申报日期 `custrecord315` |
| 报关明细 | `customrecord_swc_delare_detail` | 所属报关单 `custrecord_swc_relate_record`；PL `custrecord_swc_packing_no`；公司 `custrecord_swc_company` |

两侧公司引用均核实为 `classification`。`delare` 是来源实际拼写，不要改成 `declare`。本次联查不使用 `customrecord_swc_declare_line` 或 PL 货品明细表。

来源口径：采购数量取 `custrecord_swc_subpo_item_qty`，当前可见单位取报关单位 `custrecord_swc_subpo_item_bgunit`；报关数量和单位取 `custrecord_swc_quantity/unit`。样本两侧单位都是原始代码 `20`，尚未解析中文单位，也未证明所有订单的采购单位与报关单位一致；采购报关数量另存 `declaration_quantity`，不可据此配置直接启用跨单位匹配或金额计算。报关本次申报数量、单位另存 `declared_quantity/declared_unit`。单价和金额均保留各自来源值，不推算或分摊。报关币种保留来源显示值 `US Dollar`（当前保存到 `currency_code`，尚未转换为 ISO 代码），采购币种未返回则不填默认币种。

真实报关号和申报日期在样本中缺失，页面显示空值，不用 `CD000074` 或销售订单号替代。保存时这两项采用明确的空值配置，详见 [保存字段说明](pl-storage.md#保存字段配置)。

### 通用模板

服务器环境变量 `NETSUITE_PL_LOOKUP` 使用一个 JSON 对象；可以在 `.env` 中单引号包裹为一行。以下所有 `customrecord_example_*`、`custrecord_example_*` 都是占位符，**不是已确认的 NS 字段**。替换后将五个记录类型同时加入现有 `NETSUITE_RECORD_TYPES`，重启后生效。不要向浏览器提交记录类型、SQL、筛选表达式或凭证。

```json
{
  "pl": {
    "type": "customrecord_example_pl",
    "number": "name"
  },
  "purchase": {
    "type": "customrecord_swc_subpo",
    "pl": "custrecord_example_pl",
    "customs": "custrecord_example_customs",
    "company": "custrecord_example_company",
    "fields": {
      "purchase": "name",
      "parent": "custrecord_example_parent_po",
      "vendor": "custrecord_example_vendor",
      "currency": "custrecord_example_currency"
    }
  },
  "purchase_line": {
    "type": "customrecord_example_purchase_line",
    "parent": "custrecord_example_purchase",
    "fields": {
      "name": "custrecord_example_product_name",
      "quantity": "custrecord_example_quantity",
      "unit": "custrecord_example_unit",
      "price": "custrecord_example_tax_price",
      "amount": "custrecord_example_line_amount"
    }
  },
  "customs": {
    "type": "customrecord_example_customs",
    "fields": {
      "declaration": "custrecord_example_real_number",
      "date": "custrecord_example_declaration_date"
    }
  },
  "customs_line": {
    "type": "customrecord_example_customs_line",
    "parent": "custrecord_example_customs",
    "pl": "custrecord_example_pl",
    "company": "custrecord_example_company",
    "fields": {
      "sales": "custrecord_example_sales_order",
      "origin": "custrecord_example_origin",
      "name": "custrecord_example_product_name",
      "spec": "custrecord_example_spec",
      "quantity": "custrecord_example_quantity",
      "unit": "custrecord_example_unit"
    }
  }
}
```

`fields` 左侧是页面固定列名，右侧是 NS REST 详情真实返回的字段名；不配置的显示为“—”，不会从其他同名字段猜测。父记录字段先映射，明细字段后映射；只配置明细金额，避免把整单金额重复展示到每一行。`pl` 和 `company` 输出由关联字段统一产生。

必须先验证：PL 单号字段可精确过滤；采购单 PL、采购明细 parent、报关明细 parent 均在 REST 元数据标记为 `x-ns-filterable`。关联字段必须返回 `{ "id": "数字", "refName": "显示名称" }`，不能是自由文本或多选；两侧公司字段应引用相同公司记录类型，否则分组键不可比较。报关侧只返回列表链接并不代表详情权限齐全。

## 接口

- `GET /api/ns/pl-lookup/config`：需要登录，返回 `ready` 和中文 `reason`；配置缺失不尝试 NS 请求。
- `POST /api/ns/pl-lookup`：需要现有登录身份与来源校验（或现有服务身份）；请求 `{"pl":"PL2510310001","page":1}`。PL 允许 1—80 位字母、数字、下划线、短横线。页码 1—12，后端每页 50 行。
- 响应：`pl`、`rows`（来源 source、明细 id、关联组 group、文本字段 values）、`total`、`page`、`hasNext`、`warnings`、UTC `queriedAt`。输入错误按现有中文校验接口返回；配置缺失 503，重复 PL 409，读取失败 502 或现有详情错误码。

NS 列表按每页 100 条读取；单类最多 300 条索引、本次最多 300 条不同记录详情，超限报错，不返回看似完整的截断结果。详情按类型和内部 ID 在本请求内去重。分页重复或后续空页也报错。页面翻页重新实时查询，无跨请求缓存；源数据同时变化时不保证快照一致性。

未找到采购单不会独立扫描全量报关单；没有采购引用的报关单不在本次联查范围。无公司数据单独显示，报关公司与采购不同的行保留在不同组，不静默丢弃。真实报关号为空不以 CD 记录名称替代。

## 验证与待联调

### PL＋公司核对接口

`POST /api/ns/pl-comparison` 使用现有身份和来源校验，请求 `{"pl":"PL2510280002","company":"上海毅鑫实业有限公司"}`。PL 必填，限制同上；公司最长 120 字符，可留空，匹配公司内部 ID 或名称关键词。首尾空白在后端清理，未知字段拒绝。额外要求映射 `company_record_type` 已配置，并确认两侧公司引用同一记录类型。

此接口从 PL 查询采购单及货品行，同时按 PL 独立查询报关明细、读取所属报关单，不要求存在采购引用。它和上面的旧 `/pl-lookup` 接口范围不同。归组键使用 PL 内部 ID＋公司记录类型＋公司内部 ID；缺失公司 ID 的源行独立展示并提示，避免同名误合并。明细身份去重、数量和金额不交叉展开，不重新汇总；任一必要读取失败、索引不一致或超限，整次失败，不返回部分 Excel。

响应包含 `pl/company/account/queriedAt/source/groups/warnings/download`。每组含 `id/pl/company/summary/status/customs/purchases`；每行含来源记录 `id`、单头 `headId`、`currency` 与 15 列字符串 `cells`。含税单价固定“待确认”，金额保留源十进制字符串。无数据时 `groups=[]`、`download=null`。

`download` 包含 `filename/mediaType/contentBase64`，Excel 为合并核对、来源明细两张表，来自同次响应；下载不再次请求 NS，不接受浏览器回传业务金额。文本按文本写入，超过 Excel 15 位有效精度的数字以文本保留。采购和报关可能使用不同币种，来源明细保留币种，不做自动金额比较。接口只读，不保存数据库或修改 NS。多个 NS GET 请求不提供事务快照保证。

页面为 `/pl-reconciliation`，公司筛选在后端完成。当前来源是 NS 自定义记录 REST，尚未读取搜索 839/954 的 GROUP/MAX/SUM 汇总。测试文件 `backend/tests/test_pl_comparison.py` 覆盖公司隔离、独立报关读取、异常中止、精度、公式文本、Excel 范围及身份/参数校验。

自动测试覆盖相同报关单引用去重、跨 PL 过滤、不同公司分组、源金额精度、缺失关联、缺失配置和白名单、分页、非法输入及身份要求。测试使用假 NS，不表示真实接口已通过。

2026-09-14 本机真实只读联调：经现有本机会话和 Vite 代理调用 `POST /api/ns/pl-lookup`，`PL2510280002` 返回 HTTP 200，共 3 行，无后续页。子采购单 `YE-HD250928-Y409-1` 的货品行 801、802 数量为 55、8，行金额为 10692.0、1373.76；报关明细 129 的原数量为 63，源金额为 1799.61、币种为 US Dollar。它们属于同一 PL 和公司 3。未进行币种换算、自动匹配或 NS 写入。

其他 PL、多个公司、跨单位及权限不足场景仍需真实联调；单个样本通过不代表整个账户所有记录都具备完整字段。

2026-09-14 新核对页经本机会话及真实 M2M 验证：`PL2510280002`＋`上海毅鑫实业有限公司` 返回一个公司分组、1 行报关＋2 行采购；浏览器实际下载 Excel，并检查两张工作表的 3 条来源行与页面一致、含税单价均待确认。该样本未返回真实报关号、申报日期及采购币种，未补造这些值；单位仍为 NS 原始代码 `20`，尚未转换显示名称。已检查加载、非法 PL 错误、不存在 PL 的空结果、重置及旧地址跳转。此验证没有保存业务库或写入 NS。

技术依据：[NS REST 集合筛选](https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/section_1545222128.html)。

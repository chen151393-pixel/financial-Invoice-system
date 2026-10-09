# PL拉取、MySQL保存与页面操作

> 当前前端：旧“记录校对与写回”和“PL 单联查”页面已移除，下文涉及这些页面的操作仅为历史说明。后端接口与配置继续保留；当前页面 `/pl-reconciliation` 只提供实时查询和导出。

当前已实现页面、后端完整读取／事务保存、本地查询和重复拉取去重。保存验收使用假NS与独立MySQL 8.4.9；2026-09-14 本机已配置真实沙箱映射，通过只读联查和存储字段转换检查，本次未保存真实NS单据。不会创建NS已保存搜索，也不会写回NS。

## 页面入口

构建并启动后端，登录系统，点击“PL 单联查”。页面提供：

1. **查询本地数据**：输入PL，从MySQL读取已保存快照；不调用NS。
2. **从 NS 拉取并保存**：完整读取子采购订单、货品行及关联报关单的全部明细，再原子保存；完成后自动显示当前PL本地结果。
3. **仅查询 NS**：保留原实时联查，不写MySQL。

数据库或映射不完整时保存按钮禁用并展示原因，可重新检查。保存结果分别显示采购／报关的新增、更新及明细计数。已有来源记录每次保存计为“更新”，即使内容未变；第二次拉取的“新增”应为0。网络断开不代表保存回滚，先查询本地数据核实。

```powershell
npm.cmd run build
npm.cmd start
```

现有网页外壳仍有记录校对／NS回写模块，其写入开关只控制NS回写；本功能只读取NS、写入独立MySQL业务库。

## 保存字段配置

复用 [PL联查配置](pl-lookup.md) 的五类记录、引用字段与白名单，并添加 `company_record_type` 和各记录的 `storage_fields`。

`company_record_type` 表示采购公司与报关明细公司共同引用的记录类型。例如确认均引用 classification 后才填写 `classification`；不能凭公司显示名称推断。

`storage_fields` 左侧是六表SQL中的目标字段，右侧是NS详情JSON的实际顶层字段。以下只是追加映射示例，所有 `custrecord_example_*` 均需替换，不能直接用于真实NS：

```json
{
  "purchase": {
    "storage_fields": {
      "order_no": "name",
      "parent_order_no": "custrecord_example_parent_order",
      "supplier_name": "custrecord_example_vendor",
      "currency_code": "custrecord_example_currency"
    }
  },
  "purchase_line": {
    "storage_fields": {
      "declaration_name": "custrecord_example_declaration_name",
      "quantity": "custrecord_example_quantity",
      "unit_name": "custrecord_example_unit",
      "declaration_quantity": "custrecord_example_bg_quantity",
      "declaration_unit": "custrecord_example_bg_unit",
      "amount": "custrecord_example_line_amount"
    }
  },
  "customs": {
    "storage_fields": {
      "record_no": "name",
      "declaration_no": "custrecord_example_real_number",
      "declaration_date": "custrecord_example_date"
    }
  },
  "customs_line": {
    "storage_fields": {
      "declaration_name": "custrecord_example_name",
      "specification": "custrecord_example_spec",
      "origin_place": "custrecord_example_origin",
      "quantity": "custrecord_example_quantity",
      "unit_name": "custrecord_example_unit"
    }
  }
}
```

将这些字段合并到原 `NETSUITE_PL_LOOKUP` JSON对应记录块，保留 `type`、`pl`、`parent`、`company` 等配置；示例片段本身不是完整可运行配置。顶层再添加已经确认的 `company_record_type`。配置在 `.env`，修改后重启后端。

最低必需映射：采购单 `order_no`；采购行 `declaration_name/quantity/unit_name/amount`；报关单 `declaration_no/declaration_date`；报关行 `declaration_name/specification/origin_place/quantity/unit_name`。完整允许字段见 `backend/modules/business/entity.py` 中 `STORAGE_FIELDS`，禁止配置主键、租户或本地外键。

映射已配置但源响应不含该字段时默认保存失败，避免拼错字段后清空原数据；明确返回null则保留NULL。未映射可选字段保存NULL，原始单头和全部明细仍保存在 `source_data`。

本机使用的 [完整映射](netsuite-pl-lookup.json) 已核对元数据及实际样本。报关主表的 `custrecord_swc_realno`（真实报关号）和 `custrecord315`（申报日期）存在于元数据且允许空，但样本 74 未返回。因此在 `customs` 块显式配置 `"omitted_as_null": ["declaration_no", "declaration_date"]`。这仅允许两个已配置来源映射、数据库也允许空的目标字段在响应省略时保存NULL；后续若源字段省略，会将原值同步为空。它不豁免映射校验或已返回值的日期校验，也不允许用于采购金额、数量等其他字段。新增适配必须先核实源字段，不能将任意缺字段响应视为完整单据。

日期要求YYYY-MM-DD；映射的来源更新时间要求带时区；金额用Decimal精确读取，超精度报错，不静默舍入。不使用显示用 `fields` 反推存储口径，不把整单金额当作行金额。

## 关联、事务与去重

- NS只执行GET。`pl_reader.py`由实时联查与保存共用；保存报关单时保留其他PL的明细，并解析它们的PL号码。本地查询只筛选目标PL。
- 每次保存先取得MySQL命名锁，作用域为当前业务库、当前身份、NS账户。同范围另一个PL保存请求返回409。锁从NS读取前持有到MySQL提交后，不使用长时间行锁包裹HTTP，也不新增锁表或复用NS回写锁。
- 采购、报关主表按租户、NS账户、来源内部ID查找；明细按父单和 `记录类型:来源行ID` 更新。本地主键稳定，不使用数组下标。
- 当前 `tenant_id` 为后端认证owner的SHA256，不接受浏览器传入。相同登录身份重拉更新原数据；后台管理员与服务密钥身份各自隔离，不自动共享单据。
- 整次PL涉及的主从数据在一个短事务中提交。先报关后采购，采购外键指向已解析的本地报关单ID。原始JSON小数编码为字符串。
- 完整读取后停用该父单缺失的旧明细，重现的行恢复有效并沿用ID。读取、映射或保存失败时不清除原数据；未找到采购单也不把旧本地采购单标记为删除。
- 当前不独立扫描没有采购引用的报关单；未提供NS快照一致性保证，来源在读取期间变动仍需业务核对。若配置来源更新时间，拒绝早于本地版本的覆盖。

本地查询在可重复读事务中取得总数及本页明细，按PL／公司归组，报关在前、采购在后。每页50条明细，大组可能跨页；尚未实现按组分页、商品一一配对、金额汇总、跨行单价及最终固定15列版式。

## 接口

所有接口使用现有登录／服务身份，POST沿用现有来源与请求校验。

| 接口 | 请求与结果 |
| --- | --- |
| GET /api/business/pl-storage/config | 返回 allowed、reason、localAllowed、database；数据库和保存映射决定可用状态 |
| POST /api/business/pl-sync | `{"pl":"PL2510310001"}`；返回pl、purchase、customs、warnings、savedAt、message |
| POST /api/business/pl-documents/query | `{"pl":"PL2510310001","page":1}`；返回现有PlResult形状，每页50行 |

保存计数为 `created/updated/linesCreated/linesUpdated`，只在提交成功后返回。校验失败400或422、配置失败503、并发占用／旧版本冲突409、NS读取失败502。数据库连接或提交错误返回503并提示先查询本地核实；不返回密码、连接串和源JSON。

## 验收

2026-09-14：在隔离MySQL 8.4.9及假NS上通过重复保存、ID稳定、金额精度、其他PL明细保留、身份隔离、失败回滚、移除行停用及恢复、账户锁拦截和HTTP接口验证。全后端91项通过，1项独立MySQL回写测试未配置而跳过。

前端构建、类型检查、变更文件ESLint和后端lint通过。全仓ESLint被其他任务的 `outputs/.../.support/build-ns-mapping.mjs` 两个未使用变量阻塞，未修改该文件或质量规则。

浏览器实际验证了登录导航、空数据、首次保存、重复保存新增为0、自动本地查询及非法PL中文错误；窄屏检查页面没有横向溢出，表格在内部滚动。页面验收使用假NS与专用测试库，临时服务和测试MySQL已关闭。

2026-09-14 配置后复核：运行中的后端返回联查 `ready=true`、保存配置 `allowed=true`，MySQL六表可见；通过正式接口只读拉取 `PL2510280002` 的3条明细。使用已读取的真实完整样本和当前MySQL反射表结构验证了主从字段、Decimal金额、公司关联及两个报关空字段的转换，全程未写业务库。本次后端测试104项通过，6项独立MySQL测试因未配置专用测试库而跳过，后端lint通过；不代表已完成真实保存或MySQL 8.0并发验收。

运行本组MySQL测试需先在专用实例创建六表测试库，库名以 `_pl_test` 结尾，再设置 `PL_STORAGE_TEST_URL` 执行 `pytest backend/tests/test_pl_storage.py`；测试仅清理自己随机身份的数据。禁止指向实际业务库。

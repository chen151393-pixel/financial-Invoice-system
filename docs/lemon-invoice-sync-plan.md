# 柠檬云进项发票接入与运维

状态：2026-10-16 已实现本地手动 API 拉取与保存；尚未在正式柠檬云环境联调或部署。原接入方案由本文替代。入口为 `/sync/lemon`，沿用当前工作台登录和已有账号绑定。

## 使用与部署

部署本次代码后，在目标服务器执行 `npm.cmd run db:upgrade`、`npm.cmd run build` 并重启后端。新迁移 `0018_sync_lemon_runs` 依赖现有迁移链的 `0017_task_external_groups`，新增同步记录表和绑定表的所选账套字段，不删除已有数据。升级需使用完整迁移链，不能只复制最后一个文件。本次仅对隔离测试库验证迁移，没有升级真实业务库或远程服务器。

继续使用[已有账号绑定](lemon-account-binding.md)的服务器配置；不需要在前端填写或保存 Token。仍使用一个 API worker。反向代理的请求超时应允许一次完整拉取（客户端总分页预算 120 秒，另有认证和账套查询耗时）；超时后先“刷新同步状态”，不要自动重发保存。

1. 管理员打开“数据同步 → 柠檬云”，确认已有账号绑定。
2. 点击“查询授权账套”，选择账套并点击“使用此账套”；后端重新验证访问权限后持久保存选择。
3. 填写起止开票日期，点击“拉取并保存”。日期为 `YYYY-MM-DD`，覆盖起止当天，年份 1900～2100，单次最多 366 天、2000 张。
4. 查看真实的读取、其他类型跳过、新增、更新版本、重复跳过和明细待补齐数量，再进入现有发票台账。刷新后仍显示最近一次同步结果。

首次建议选择较小日期范围验证权限和字段；本系统仅保存账套内已录入的人民币进项票，不调用税局取票。仅新增业务类型为“采购固定资产”的发票；已有来源记录业务类型改变仍更新版本，并标为待核实，不能静默保留旧可用状态。

## 官方协议

协议依据[授权接口文档](https://open2.ningmengyun.com/Content/h5/ApiDecription.html)和[财务接口文档](https://open2.ningmengyun.com/Content/h5/AccApiDecription.html)。真实应用权限、账套版本和响应字段仍须在目标环境联调。

| 步骤 | POST 地址 | 认证及参数 |
| --- | --- | --- |
| 应用全局令牌 | `/api/OAuth2/AccessToken/GetAppAccessToken` | 复用已有绑定客户端，正文 `appId`、`appSecret` |
| 正式用户令牌 | `/api/OAuth2/Token/GetSpecificUserToken` | 全局 Bearer；查询参数 `userid=已绑定手机号`、`isOem=false` |
| 查询账套 | `/api/Settings/AccountSet/GetAccountSets` | 用户 Bearer；读取 `Data.rows` 的 `AsId`、`AsName` |
| 查询进项票 | `/api/Invoice/Invoice/GetInvoice` | 用户 Bearer，独立请求头 `asid`；查询参数见下方 |

```http
POST $ACCAPI_HOST/api/Invoice/Invoice/GetInvoice?invoiceCategory=10080&startDate=2026-10-01&endDate=2026-10-16&invoiceStatus=0&page=1&rows=100
Authorization: Bearer <正式用户Token>
asid: <已授权账套编号>
```

请求参数在 URL 查询串中；不使用历史原型的 JSON 日期参数，也不把全局 Token 当用户 Token。每次操作重新获取用户 Token，只在服务端当前调用中保存，不返回浏览器、不入库。账套查询使用官方专业版接口；其他产品版本或服务商专属接口尚未适配。

发票读取 `State=1000` 且 `Data.List` 为列表的响应，按 `page=1,2,...`、`rows=100` 查询直到空页。不假定 `Count` 是总数，也不将不足 100 条视为结束。第 21 页非空、重复来源 ID、缺失 ID、分页或网络失败均拒绝整批保存；单页最多 4 MiB。数字分页不是不可变快照，上游同时增删数据可能造成漏读，重复扫描日期范围只能去重，不能证明上游快照完整。定时回扫与增量游标尚未实现。

## 模块与接口

`integrations/lemon/invoice_client.py` 只负责正式认证、HTTP 和分页。`sync` 管理管理员身份、账套选择、日期、持久请求和结果；`invoice` 负责业务范围、金额、同票身份和版本保存。

| 本地接口 | 请求 | 返回 |
| --- | --- | --- |
| `GET /api/sync/lemon/invoices/configuration` | 无 | `query/sync` 的 `allowed/reason`、`selected`、`latest` |
| `POST /api/sync/lemon/accounts/query` | JSON `{}` | `items: [{asid,name}]`，不含令牌 |
| `POST /api/sync/lemon/account` | JSON `{asid}` | 重新校验权限后的配置 |
| `POST /api/sync/lemon/invoices/pull-save` | JSON `{requestId,asid,startDate,endDate}` | 持久请求与已提交统计；`requestId` 为 UUID |
| `GET /api/sync/lemon/runs/{requestId}` | 无 | 当前身份/应用范围内的原请求结果，不触发外部拉取 |

操作权限仅来自认证身份，浏览器不能提交发票正文或自行指定操作者。选账套和开始同步先锁定绑定行，同一身份/应用范围最多一个未结束请求；重用同一 `requestId` 返回原状态，改变参数返回 409。运行中不允许切换账套。

外部读取在数据库事务之外。读取完毕取得现有账本锁，在同一短事务中发布 `LemonInvoicesFetched`；invoice 订阅者校验和保存，再发布 `LemonInvoicesStored` 回执；sync 订阅者标记完成。订阅只在 `app.py` 装配，任一订阅失败整体回滚。只有提交成功才返回完成统计；不通过跨模块 DAO 写入。

## 字段、去重和版本

- `InvoiceId` 为稳定来源 ID；API 账套命名空间是 `open2:` 加服务器环境与 `asid` 的 SHA-256，不使用手机号区分同一账套，也不与 Excel 固定命名空间 `lemon` 混用。
- `Code`、`Number` 构成同票键；号码必须是数字文本，保留前导零。来源 ID 改票号、同票键改来源 ID、批内重复均整批拒绝。
- `InvoiceDateText` / `InvoiceDate` 必须为 ISO 开票日期且在请求范围内；不使用认证日期代替。
- `Amount`、`Tax`、`AdValoremTaxTotals` 分别映射未税额、税额、含税额，按 Decimal 精确解析，最多两位小数并验证守恒。不从展示文本计算金额。
- 进项票的 `Name`、`TaxpayerNumber` 映射供应商及税号；购买方未提供则为空。币种按已确认范围写入 CNY，来源规则为 `lemon_cny_v1`。
- `IsInvalid` 的 0/1/2 分别为正常/作废/红冲；3（部分红冲）及未知值标为 unknown。负金额票不能当普通蓝票。
- 相同票头内容跳过版本新增；改变追加不可变版本和原始证据，复用 `version_service` 以及 `InvoiceChanging/InvoiceChanged/InvoicesImported` 事件。未知或作废状态不能绕过匹配约束。
- API 与 Excel 的同代码/号码在两个导入方向均拒绝冲突；现有 Excel 尚无可核实 API 账套，不能自动跨渠道合并或重复增加额度。当前不能通过再次导入同票 Excel 自动补齐 API 明细。

列表接口没有商品明细。保存 `detail_status=pending` 和零条新明细，不用 `VerifiedBills`、`VerifiedInvoices` 伪造商品行。现有版本写入器保留已存在的逻辑明细与历史占用；票头变化仍使完整性待核实。现有匹配订阅要求明细完整，因此这些新 API 票不会生成逐行候选。详情接口新增 `detailStatusLabel`，前端展示真实完整性状态。

## 结果未知与恢复边界

上游明确失败或业务校验失败记录为 failed，发票整批不保存。数据库异常、进程中断保留 running；重启不会清除记录或自动重跑。先刷新或按请求编号查询；若已 completed，以原结果为准。

若长期 running，管理员须核实该请求对应进程已结束、数据库提交状态与关联票据后再人工处置；当前没有自动解锁或继续执行接口。不要删除同步记录、批量改状态或盲目发起新请求。发票保存与 completed 回执在同一事务，能作为核实原提交结果的依据。

## 验证与未完成项

协议测试覆盖正式用户 Token、Bearer/asid、查询串分页、Decimal、异常响应、重复页和页数上限。集成测试覆盖权限、日期、账号隔离、整批回滚、两种渠道冲突、去重、版本和重启后不重试。MySQL 隔离库验证同请求并发、运行中切账套/新请求拒绝、精确金额与事件回滚；测试不修改正式库。

本地浏览器以假上游和隔离数据验证账套选择、日期、拉取、重复跳过、刷新持久化、现有台账、桌面和窄屏。构建或隔离测试通过不等于正式接口联调通过。

仍未接入：商品明细与稳定行身份、跨来源同票合并补全、附件、定时同步、税局取票、多 worker 共享会话，以及中断请求的管理端恢复。真实用户 Token、账套权限及上游字段须部署后实际验证。

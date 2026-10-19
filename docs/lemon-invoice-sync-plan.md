# 柠檬云进项发票接入与运维

状态：2026-10-16 已实现本地手动 API 拉取与保存；尚未在正式柠檬云环境联调或部署。原接入方案由本文替代。入口为 `/sync/lemon`，沿用当前工作台登录和已有账号绑定。

## 使用与部署

部署本次代码后，在目标服务器执行 `npm.cmd run db:upgrade`、`npm.cmd run build` 并重启后端。新迁移 `0018_sync_lemon_runs` 依赖现有迁移链的 `0017_task_external_groups`，新增同步记录表和绑定表的所选账套字段，不删除已有数据。升级需使用完整迁移链，不能只复制最后一个文件。本次仅对隔离测试库验证迁移，没有升级真实业务库或远程服务器。

继续使用[已有账号绑定](lemon-account-binding.md)的服务器配置；不需要在前端填写或保存 Token。仍使用一个 API worker。反向代理的请求超时应允许一次完整拉取（客户端总分页预算 120 秒，另有认证和账套查询耗时）；超时后先“刷新同步状态”，不要自动重发保存。

1. 管理员打开“数据同步 → 柠檬云”，确认已有账号绑定。
2. 点击“查询授权账套”，后台自动发现专业版服务并携带服务 ID 查询账套，无需手填。选择账套并点击“使用此账套”；后端重新验证访问权限后持久保存选择。有专业版服务时展示专业版账套；没有发现专业版服务时保留默认账套列表。
3. 填写起止开票日期，点击“拉取并保存”。日期为 `YYYY-MM-DD`，覆盖起止当天，年份 1900～2100，单次最多 366 天、2000 张。
4. 查看真实的读取、其他类型跳过、新增、更新版本、重复跳过和明细待补齐数量，再进入现有发票台账。刷新后仍显示最近一次同步结果。

首次建议选择较小日期范围验证权限和字段；本系统仅保存账套内已录入的人民币进项票，不调用税局取票。仅新增业务类型为“采购固定资产”的发票；已有来源记录业务类型改变仍更新版本，并标为待核实，不能静默保留旧可用状态。

## 官方协议

协议依据[授权接口文档](https://open2.ningmengyun.com/Content/h5/ApiDecription.html)和[财务接口文档](https://open2.ningmengyun.com/Content/h5/AccApiDecription.html)。真实应用权限、账套版本和响应字段仍须在目标环境联调。

| 步骤 | POST 地址 | 认证及参数 |
| --- | --- | --- |
| 应用全局令牌 | `/api/OAuth2/AccessToken/GetAppAccessToken` | 复用已有绑定客户端，正文 `appId`、`appSecret` |
| 正式用户令牌 | `/api/OAuth2/Token/GetSpecificUserToken` | 全局 Bearer；查询参数 `userid=已绑定手机号`、`isOem=false` |
| 查询默认账套 | `/api/Settings/AccountSet/GetAccountSets` | 用户 Bearer；读取 `Data.rows` 的 `AsId`、`AsName`，为权限查询提供真实账套上下文 |
| 发现专业版服务 | `/api/Settings/Permission/GetAllPermissions` | 用户 Bearer；有默认账套时携带首个真实编号的 `asid` 请求头；读取 `Data.rows[].ServiceId` 并去重 |
| 查询专业版账套 | `/api/Settings/AccountSet/GetAccountSets?serviceId=SERVICEID` | 用户 Bearer；依次查询已发现的非零服务 ID，读取 `AsId`、`AsName` |
| 查询进项票 | `/api/Invoice/Invoice/GetInvoice` | 用户 Bearer，独立请求头 `asid`；查询参数见下方 |

```http
POST $ACCAPI_HOST/api/Invoice/Invoice/GetInvoice?invoiceCategory=10080&startDate=2026-10-01&endDate=2026-10-16&number=&invoiceType=0&invoiceStatus=0&name=&page=1&rows=100
Authorization: Bearer <正式用户Token>
asid: <已授权账套编号>
```

请求参数在 URL 查询串中；不使用历史原型的 JSON 日期参数，也不把全局 Token 当用户 Token。每次操作重新获取用户 Token，只在服务端当前调用中保存，不返回浏览器、不入库。专业版服务发现与查询由后台完成；其他产品或服务商专属接口尚未适配。

发票读取 `State=1000` 且 `Data.List` 为列表的响应，按 `page=1,2,...`、`rows=100` 查询直到空页。不假定 `Count` 是总数，也不将不足 100 条视为结束。第 21 页非空、重复来源 ID、缺失 ID、分页或网络失败均拒绝整批保存；单页最多 4 MiB。数字分页不是不可变快照，上游同时增删数据可能造成漏读，重复扫描日期范围只能去重，不能证明上游快照完整。定时回扫与增量游标尚未实现。

## 模块与接口

### 专业版服务自动发现（2026-10-19）

查询、选择及拉票前的权限复核统一调用 `LemonAccountService.authorized_accounts()`。先读取默认账套，再读取用户全部账套权限中的 `ServiceId`，逐个携带 `serviceId` 查询专业版账套。服务 ID 只来自上游，不从手机号、账套 ID、编号前缀或前端参数推算；不缓存跨账号令牌或服务。

有非零服务 ID 时只返回专业版结果，专业版空列表不回退免费版。没有专业版服务时才返回默认账套。服务去重、账套按 ID 去重；不同服务返回同一 ID 的名称不一致则报错。权限或任一服务查询失败时整次失败，不返回部分结果；最多 1000 条权限、50 个专业版服务和 1000 个合并后账套，超过上限报错，不截断。

权限接口的字段表用 `AsId`，示例用 `as_id`，两者均接收；`ServiceId` 按官方整数定义校验，0、缺省或 null 表示未提供专业版服务。默认账套为空时不伪造 `asid`，尝试用户级 `GetAllPermissions`；官方文档仍列有 `asid` 请求头，该无默认账套场景能否在生产环境使用须真实联调，若上游拒绝则显示错误。

本次不改前端契约和数据库结构。部署后重启后端，重新查询并选择专业版账套即可；不会自动把原已选免费版账套替换为某个专业版账套。新增 `account_permissions` 脱敏日志阶段。隔离测试覆盖自动发现、多服务、重复服务、空结果、异常、查询/选择/拉票一致性及撤权后阻止拉票；尚未在用户真实账号上验证能返回截图中的 6 个账套。

### 本地接口

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

## 读取失败诊断（2026-10-16）

本地请求校验未通过会返回 400，具体查看浏览器响应中的中文原因；起止日期颠倒、超过范围等错误返回具体日期提示。返回 502 时，响应现在明确指出获取用户授权、查询授权账套或查询进项发票的阶段，并区分上游 HTTP 状态、超时、网络传输、无效 JSON 与业务拒绝。

服务器日志新增 `lemon_read_failed`，只记录 `operation`（user_token/accounts/invoices）、异常类别、`upstream_status`、页码、整数 `State/SubState` 与耗时；不记录手机号、账套、URL 查询串、Token、上游 Msg 或正文。`upstream_status=403` 表示上游 HTTP 拒绝，不能仅凭它断言是账号权限还是网关策略；具体仍须按阶段核查应用权限或网关。`invalid_json` 表示响应无法按 JSON 解析；`timeout` 表示客户端等待超时。上述诊断不会自动重试。

Docker 部署更新本次后端代码并重建 app 后，可用 `docker compose logs --since=10m app` 查找 `lemon_read_failed`。旧版只保留了 `request_failed ... status=502`，无法从旧日志恢复已经丢弃的上游状态；诊断补丁本身不代表已修复真实上游故障。


## 发票查询 404 修复（2026-10-16）

远端日志显示 `operation=invoices upstream_status=404 page=1`，前置用户授权和账套查询已通过。客户端原先省略了文档 URL 中的 `number`、`invoiceType`、`name`；已改为每页显式发送 `number=`、`invoiceType=0`、`name=`，不调整域名、绑定或数据库。

在官方生产地址进行了不携带 Token/账套的只读协议对照：原参数返回 404；补齐三个键（invoiceType 为 0）返回 401；只补 invoiceType 或只补两个文本键仍为 404。该结果验证缺参数时上游无法选择查询接口，完整参数进入授权检查；401 是无凭证探测的预期结果，不代表真实用户授权失败，也不证明已成功取得真实发票。0 作为本次未指定票种的请求值，实际返回范围仍须在授权联调中核对；不能凭此声称所有票种已验证。

协议测试逐页核对完整查询串，包括两个空字符串键，避免 HTTP 客户端或后续整理再次省略。该修复无需数据库迁移；真实账套需部署后重新执行一次小范围拉取验证。

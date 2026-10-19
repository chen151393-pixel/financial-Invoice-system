# 柠檬云进项发票接入与运维

状态：已实现默认版及专业版账套手动 API 拉取与保存。2026-10-19 专业版已通过真实账号只读拉取及隔离 SQLite 保存验证，结果见下方。入口为 `/sync/lemon`，沿用当前工作台登录和已有账号绑定。代码本地验证不表示远端已部署。

## 使用与部署

部署本次代码后，在目标服务器执行 `npm.cmd run db:upgrade`、`npm.cmd run build` 并重启后端。新迁移 `0018_sync_lemon_runs` 依赖现有迁移链的 `0017_task_external_groups`，新增同步记录表和绑定表的所选账套字段，不删除已有数据。升级需使用完整迁移链，不能只复制最后一个文件。本次仅对隔离测试库验证迁移，没有升级真实业务库或远程服务器。

继续使用[已有账号绑定](lemon-account-binding.md)的服务器配置；不需要在前端填写或保存 Token。仍使用一个 API worker。反向代理的请求超时应允许一次完整拉取（客户端总分页预算 120 秒，另有认证和账套查询耗时）；超时后先“刷新同步状态”，不要自动重发保存。

1. 管理员打开“数据同步 → 柠檬云”，确认已有账号绑定。
2. 点击“查询授权账套”，后台自动取得官方财务服务入口返回的专业版服务 ID 并查询账套，无需手填。选择账套并点击“使用此账套”；后端重新验证访问权限后持久保存选择。仅当上游明确确认没有专业版服务时才查询默认账套；发现失败不回退。拉票时自动按所选账套版本选择对应接口。
3. 填写起止开票日期，点击“拉取并保存”。日期为 `YYYY-MM-DD`，覆盖起止当天，年份 1900～2100，单次最多 366 天、2000 张。
4. 查看真实的读取、其他类型跳过、新增、更新版本、重复跳过、明细完整和待补齐/待核实数量，再进入现有发票台账。刷新后仍显示最近一次同步结果。

首次建议选择较小日期范围验证权限和字段；本系统仅保存账套内已录入的人民币进项票，不调用税局取票。API 默认选择“采购固定资产”和“采购支出”，可手动多选 `businessTypeText`；未勾选的新票跳过。已有来源记录的业务类型被上游改到所选范围外时仍更新版本并标为待核实；仅取消勾选不会修改已入库发票。Excel 导入范围保持原有固定资产规则。

### 业务类型多选与结果提示

`GET /api/sync/lemon/invoices/configuration` 返回后端 `defaultBusinessTypes` 和 `businessTypeOptions`。选项由默认两类、最近记录的选中类型和真实返回的 `availableBusinessTypes` 合并提供，不将其当作完整柠檬云字典。首次只展示默认两类，其他实际出现的类型在拉取完成后补充，用户可勾选后重新拉取。

拉取请求新增 `businessTypes: ["采购固定资产", "采购支出"]`，按 `businessTypeText` 去除首尾空白后的文本精确匹配。后端校验至少一项、最多 50 项、每项最多 255 字符，拒绝空白、非文本和重复项；不传则使用默认两类。前端只管理勾选并提交，不执行筛选或统计。

筛选快照复用 `sync_lemon_runs.result` JSON 中的 `businessTypes` 保存，无需表结构迁移：运行中先保存条件，失败时保留，完成时写入包含相同条件的统计。响应将条件独立提供为 `businessTypes`；运行中和失败时 `result` 仍为 null。相同请求编号的账套、日期和业务类型集合必须一致，顺序变化不视为新条件。旧记录无快照时按原“采购固定资产”范围解释，不套用新默认值。

全部跳过明确提示“本次未保存发票”，无结果明确提示“未查到”，全部重复明确提示“均已存在且未变化”；只有新增或更新时 `saved=true`。后端也会在查询历史记录时按原统计修正旧成功文案，不改写历史数据。最近一次同步展示当次条件，不随表单当前勾选变化。

2026-10-19 真实只读＋隔离 SQLite 验证：账套 200896951，2026-09-01 至 2026-10-19，7 张全部为“采购支出”。仅固定资产时 7 张全部跳过、`saved=false`；默认两类时新增 7 张；重复拉取 7 张未变化、`saved=false`。最终票头 7、版本 7、商品行 0。未写生产库或上游，临时库已删除。下文 78 张/15 张是仅选择固定资产时的历史验证记录。

## 官方协议

协议依据[授权接口文档](https://open2.ningmengyun.com/Content/h5/ApiDecription.html)和[财务接口文档](https://open2.ningmengyun.com/Content/h5/AccApiDecription.html)。真实应用权限、账套版本和响应字段仍须在目标环境联调。

| 步骤 | POST 地址 | 认证及参数 |
| --- | --- | --- |
| 应用全局令牌 | `/api/OAuth2/AccessToken/GetAppAccessToken` | 复用已有绑定客户端，正文 `appId`、`appSecret` |
| 正式用户令牌 | `/api/OAuth2/Token/GetSpecificUserToken` | 全局 Bearer；查询参数 `userid=已绑定手机号`、`isOem=false` |
| 查询默认账套 | `/api/Settings/AccountSet/GetAccountSets` | 用户 Bearer；仅在确认没有专业版服务时读取 `Data.rows` 的 `AsId`、`AsName` |
| 查询进项票 | `/api/Invoice/Invoice/GetInvoice` | 用户 Bearer，独立请求头 `asid`；查询参数见下方 |

```http
POST $ACCAPI_HOST/api/Invoice/Invoice/GetInvoice?invoiceCategory=10080&startDate=2026-10-01&endDate=2026-10-16&number=&invoiceType=0&invoiceStatus=0&name=&page=1&rows=100
Authorization: Bearer <正式用户Token>
asid: <已授权账套编号>
```

请求参数在 URL 查询串中；不使用历史原型的 JSON 日期参数，也不把全局 Token 当用户 Token。每次操作重新获取用户 Token，只在服务端当前调用中保存，不返回浏览器、不入库。此表的进项票接口用于默认账套；专业版账套查询流程见下一节，其他产品或服务商专属接口尚未适配。

发票读取 `State=1000` 且 `Data.List` 为列表的响应，按 `page=1,2,...`、`rows=100` 查询直到空页。不假定 `Count` 是总数，也不将不足 100 条视为结束。第 21 页非空、重复来源 ID、缺失 ID、分页或网络失败均拒绝整批保存；单页最多 4 MiB。数字分页不是不可变快照，上游同时增删数据可能造成漏读，重复扫描日期范围只能去重，不能证明上游快照完整。2026-10-19 已接入可配置每日日期回扫，见[后台同步说明](lemon-background-sync.md)；修改时间增量游标仍未实现。

## 模块与接口

### 专业版服务自动发现（2026-10-19）

真实联调复现：同一个有效用户 Token 查询默认账套返回 2 个；默认账套的 `GetAllPermissions` 未提供非零服务 ID；带专业版账套编号查询则返回 HTTP 401，正文为空。即使给 `open2/GetAccountSets` 传入从官方服务入口取得的真实专业版服务 ID，仍返回同样的 2 个默认账套。因此移除上一版基于该权限接口发现专业版服务的实现；不能将此 401 断言为手机号错误、绑定失效或应用权限未开通。

查询、选择及拉票前复核统一调用 `LemonAccountService.authorized_accounts()`。新的 `integrations/lemon/professional_accounts.py` 使用[官方统一登录说明](https://open2.ningmengyun.com/Home/EmbeddingLogin)及[官方财务网页](https://j6.ningmengyun.com/)公开代码中实际使用的只读协议：

| 步骤 | 请求 | 处理 |
| --- | --- | --- |
| 建立临时会话 | `GET https://api.ningmengyun.com/api/AuthorizationCookie.ashx?token=用户Token` | 仅在本次调用的独立 Cookie 容器中保存会话 |
| 确认专业版服务 | `GET https://wbgate.ningmengyun.com/wb/plan/haveProServiceInfo` | `statusCode=true` 且 `data=false` 才允许默认账套查询 |
| 取得财务服务上下文 | `GET https://wbgate.ningmengyun.com/wb/redirect/info?appId=1060&virtualAppId=1062&productType=acc` | 读取真实 `serviceId` 和 `appasid`；不访问返回的跳转 URL。1060/1062 是网页财务产品入口标识，不是本系统应用密钥 |
| 查询专业版账套 | `GET https://jproapi.ningmengyun.com/api/AccountSetOnlyAuth/TopInfoV2?serviceId=...&appasid=...` | 要求 `state=1000`；仅将 `data.accountList` 中 `asid/asname` 映射给浏览器 |

服务 ID 不从手机号、账套编号或前端参数推算。当前查询范围是官方财务入口返回的服务，已真实验证一个服务下的 6 个账套；尚未验证同一账号多个专业版服务的完整枚举。专业版列表为空不回退默认版；缺失服务、异常状态、重复账套、超过 1000 个账套或单次响应超过 4 MiB 均报错。每次请求独立会话、不持久保存 Cookie、不跟随重定向，不记录 Token、加密账套或上游正文。成功日志为 `lemon_accounts_read source=professional count=...`；失败日志仅含固定阶段、HTTP 状态或异常类型。

这些服务和账套地址来自官方网页的实际调用，并非旧 open2 文档承诺的稳定接口；已按 2026-10-19 真实响应验证，官方升级可能需要适配。只支持当前已验证的生产环境，不自动把测试环境凭据发往生产环境。

不改前端接口契约或数据库结构，也不自动替换已选账套。部署需要重建镜像并更新运行容器后重新查询。隔离 API 测试覆盖选择、撤权、会话隔离、异常不回退及专业版发票保存。

### 专业版进项发票（2026-10-19）

协议依据[官方专业版网页](https://jpro6.ningmengyun.com)当前公开脚本中的 `PurchasePagingList` 调用和授权账号实测。它是网页会话接口，不能按 open2 的 Bearer/asid 协议调用。每次拉取重新建立独立临时会话，复核专业版账套列表，并使用**所选账套**对应的 `appAsId`，而不是服务入口的默认账套上下文。

```http
POST https://jproapi.ningmengyun.com/api/Invoice/PurchasePagingList?pageIndex=1&pageSize=100&serviceId=<自动发现>&appasid=<所选账套加密上下文>
appasid: <所选账套加密上下文>
Cookie: <本次官方 SSO 会话，仅驻内存>
Content-Type: application/json

{"startDate":"2026-07-31","endDate":"2026-10-19","invoiceStatus":"0","invoiceType":"0","invoiceVoucherStatus":"0","invoiceIssueDateStatus":"0","invoiceBillStatus":"0"}
```

- 成功响应要求 `state=1000`，`data.data` 为列表、`data.count` 为非负整数发票总数。实测每页末尾附一条合计，终止页可能仅有合计；只排除满足零编号、零类别、空代码/号码、空日期和 `businessTypeText=合计` 的末行。缺编号的其他行一律报错。
- 每页最多 100 张，继续请求至无发票页；逐页核对稳定总数、预期行数和唯一发票 ID。总数变化、缺页、重复、超过 2000 张、超时或任一页失败时整批不保存。单页响应上限 4 MiB。总数校验不能保证上游并发修改时的不可变快照；同总数的替换仍可能无法识别。
- 小驼峰字段按首字母大写规范化后复用 invoice 校验；JSON 小数按 `Decimal` 解析，票号仍为字符串。专业版 `isInvalid` 的 0/1/2 分别为正常/作废/已红冲，3 部分红冲保留未知待核实。业务范围、日期、金额平衡检查均由 invoice 执行。
- 来源记为 `lemon_professional`，命名空间为 `professional:` 加 `SHA256(配置环境|asid)`，与默认版及 Excel 隔离。复用同一事件事务、不可变版本及来源冲突检查，不新增平行发票表。商品明细在下节补全后生成待审核建议。

本次真实验证范围：用户指定专业版账套，2026-07-31 至 2026-10-19，接口读取 78 张；隔离 SQLite 新增 15 张“采购固定资产”，排除其他业务类型 63 张。再次用每页 20 张读取全部分页，78 张总数一致，15 张已存票全部未变化；最终票头 15、版本 15、商品行 0。同请求编号再次执行返回原结果。未写入上游数据或生产数据库，临时库验证后删除。模拟协议测试与真实联调结果分别记录，不将测试替身视作上游成功。

### 本地接口

`integrations/lemon/invoice_client.py` 只负责正式认证、HTTP 和分页。`sync` 管理管理员身份、账套选择、日期、持久请求和结果；`invoice` 负责业务范围、金额、同票身份和版本保存。

| 本地接口 | 请求 | 返回 |
| --- | --- | --- |
| `GET /api/sync/lemon/invoices/configuration` | 无 | `query/sync` 的 `allowed/reason`、`selected`、`latest` |
| `POST /api/sync/lemon/accounts/query` | JSON `{}` | `items: [{asid,name}]`，不含令牌 |
| `POST /api/sync/lemon/account` | JSON `{asid}` | 重新校验权限后的配置 |
| `POST /api/sync/lemon/invoices/pull-save` | JSON `{requestId,asid,startDate,endDate}` | 持久请求与已提交统计；`requestId` 为 UUID |
| `GET /api/sync/lemon/runs/{requestId}` | 无 | 当前身份/应用范围内的原请求结果，不触发外部拉取 |

操作权限仅来自认证身份，浏览器不能提交发票正文或自行指定操作者。选账套和开始同步先锁定绑定行，同一身份/应用范围的同一账套最多一个未结束请求；重用同一 `requestId` 返回原状态，改变参数返回 409。手动请求运行中不允许切换账套；后台任务使用冻结范围，不依赖页面选择。

外部读取在数据库事务之外。读取完毕取得现有账本锁，在同一短事务中发布 `LemonInvoicesFetched`；invoice 订阅者校验和保存，再发布 `LemonInvoicesStored` 回执；sync 订阅者标记完成。订阅只在 `app.py` 装配，任一订阅失败整体回滚。只有提交成功才返回完成统计；不通过跨模块 DAO 写入。

## 字段、去重和版本

- `InvoiceId` 为稳定来源 ID；API 账套命名空间是 `open2:`（默认版）或 `professional:`（专业版）加服务器环境与 `asid` 的 SHA-256，不使用手机号区分同一账套，也不与 Excel 固定命名空间 `lemon` 混用。
- `Code`、`Number` 构成同票键；号码必须是数字文本，保留前导零。来源 ID 改票号、同票键改来源 ID、批内重复均整批拒绝。
- `InvoiceDateText` / `InvoiceDate` 必须为 ISO 开票日期且在请求范围内；不使用认证日期代替。
- `Amount`、`Tax`、`AdValoremTaxTotals` 分别映射未税额、税额、含税额，按 Decimal 精确解析，最多两位小数并验证守恒。不从展示文本计算金额。
- 进项票的 `Name`、`TaxpayerNumber` 映射供应商及税号；购买方未提供则为空。币种按已确认范围写入 CNY，来源规则为 `lemon_cny_v1`。
- `IsInvalid` 的 0/1/2 分别为正常/作废/红冲；3（部分红冲）及未知值标为 unknown。负金额票不能当普通蓝票。
- 相同票头及商品明细内容跳过版本新增；改变追加不可变版本和原始证据，复用 `version_service` 以及 `InvoiceChanging/InvoiceChanged/InvoicesImported` 事件。未知或作废状态不能绕过匹配约束。
- API 与 Excel 的同代码/号码在两个导入方向均拒绝冲突；现有 Excel 尚无可核实 API 账套，不能自动跨渠道合并或重复增加额度。当前不能通过再次导入同票 Excel 自动补齐 API 明细。

列表接口没有商品明细。专业版在列表后调用只读详情补全；默认版保存 `detail_status=pending` 和零条新明细。不用 `VerifiedBills`、`VerifiedInvoices` 伪造商品行。现有版本写入器保留不完整/歧义票的原逻辑明细与占用，完整明细才进入既有匹配事件。详情接口 `detailStatusLabel` 展示真实完整性状态。

## 结果未知与恢复边界

上游明确失败或业务校验失败记录为 failed，发票整批不保存。数据库异常、进程中断保留 running；重启不会清除记录或自动重跑。先刷新或按请求编号查询；若已 completed，以原结果为准。

若长期 running，管理员须核实该请求对应进程已结束、数据库提交状态与关联票据后再人工处置；当前没有自动解锁或继续执行接口。不要删除同步记录、批量改状态或盲目发起新请求。发票保存与 completed 回执在同一事务，能作为核实原提交结果的依据。

## 验证与未完成项

协议测试覆盖正式用户 Token、Bearer/asid、查询串分页、Decimal、异常响应、重复页和页数上限。集成测试覆盖权限、日期、账号隔离、整批回滚、两种渠道冲突、去重、版本和重启后不重试。MySQL 隔离库验证同请求并发、运行中切账套/新请求拒绝、精确金额与事件回滚；测试不修改正式库。

本地浏览器以假上游和隔离数据验证账套选择、日期、拉取、重复跳过、刷新持久化、现有台账、桌面和窄屏。构建或隔离测试通过不等于正式接口联调通过。

仍未接入：默认版商品明细、上游稳定行编号的核实、跨来源同票合并补全、附件、税局取票、多 worker 共享会话，以及中断请求的管理端恢复。2026-10-19 已真实验证用户 Token、专业版账套查询、进项票分页和隔离库保存；远端部署、生产库保存与多专业版服务枚举未验证。本次 SQLite 验证不替代 MySQL 并发验收。

## 读取失败诊断（2026-10-16）

若页面出现 `options is not iterable`，先检查配置接口是否包含数组 `businessTypeOptions`、`defaultBusinessTypes`，以及最近同步记录的 `businessTypes`。前端热更新而后端仍运行旧进程时会缺少这些字段。前端现已在配置、选账套及同步结果响应入口校验，缺失或格式异常时显示中文恢复提示，不将异常数据交给多选组件，也不自动重发保存。本地 Windows 开发脚本关闭了 Python 自动重载，修改后端后须重启后端服务；Docker 部署须重新构建并重建 app 容器。

本地请求校验未通过会返回 400，具体查看浏览器响应中的中文原因；起止日期颠倒、超过范围等错误返回具体日期提示。返回 502 时，响应现在明确指出获取用户授权、查询授权账套或查询进项发票的阶段，并区分上游 HTTP 状态、超时、网络传输、无效 JSON 与业务拒绝。

服务器日志新增 `lemon_read_failed`，只记录 `operation`（user_token/accounts/invoices）、异常类别、`upstream_status`、页码、整数 `State/SubState` 与耗时；不记录手机号、账套、URL 查询串、Token、上游 Msg 或正文。`upstream_status=403` 表示上游 HTTP 拒绝，不能仅凭它断言是账号权限还是网关策略；具体仍须按阶段核查应用权限或网关。`invalid_json` 表示响应无法按 JSON 解析；`timeout` 表示客户端等待超时。上述诊断不会自动重试。

Docker 部署更新本次后端代码并重建 app 后，可用 `docker compose logs --since=10m app` 查找 `lemon_read_failed`。旧版只保留了 `request_failed ... status=502`，无法从旧日志恢复已经丢弃的上游状态；诊断补丁本身不代表已修复真实上游故障。


## 发票查询 404 修复（2026-10-16）

远端日志显示 `operation=invoices upstream_status=404 page=1`，前置用户授权和账套查询已通过。客户端原先省略了文档 URL 中的 `number`、`invoiceType`、`name`；已改为每页显式发送 `number=`、`invoiceType=0`、`name=`，不调整域名、绑定或数据库。

在官方生产地址进行了不携带 Token/账套的只读协议对照：原参数返回 404；补齐三个键（invoiceType 为 0）返回 401；只补 invoiceType 或只补两个文本键仍为 404。该结果验证缺参数时上游无法选择查询接口，完整参数进入授权检查；401 是无凭证探测的预期结果，不代表真实用户授权失败，也不证明已成功取得真实发票。0 作为本次未指定票种的请求值，实际返回范围仍须在授权联调中核对；不能凭此声称所有票种已验证。

协议测试逐页核对完整查询串，包括两个空字符串键，避免 HTTP 客户端或后续整理再次省略。该修复无需数据库迁移；真实账套需部署后重新执行一次小范围拉取验证。

## 专业版商品明细与匹配（2026-10-19）

协议来自[官方专业版网页](https://jpro6.ningmengyun.com/)当前公开脚本 `index-3c772723.js` 的详情读取函数及商品表单字段。使用同一已选账套的临时会话：

```text
GET https://jproapi.ningmengyun.com/api/Invoice?invoiceType=<列表种类>&invoiceId=<列表编号>&serviceId=<自动发现>&appasid=<所选上下文>
```

要求 `state=1000` 且 `data.invoiceData.invoiceEntries` 为完整数组。读取仅针对本次选择的业务类型；范围外已入库发票仍按原规则传播类型变更失效。单票一万行、明细阶段 120 秒上限；任何读取失败、超限、错票或金额不一致均整批不保存。外部读取不占数据库事务，Cookie 和上下文不落盘。

| 官方商品字段 | 本地字段与规则 |
| --- | --- |
| name / model / unit | 品名 / 规格 / 单位；文本长度按现有表限制 |
| quality | 数量，Decimal 最多 8 位小数，不以默认值补缺失 |
| amount / tax | 未税金额 / 税额；分别求和校验票头，含税行金额为两者精确相加 |
| taxRate | 百分数转小数；-100（免税）、-101（不征税）保留原始码，本地数值税率为空 |
| sn | 不用作稳定行身份；沿用品名、规格、单位身份与既有歧义保护 |

无已核实的购买方、单价字段，保持未知。空数组、缺少匹配所需品名/单位/正数量/正含税金额保留 pending；重复身份行换版时不能唯一承接则 failed，历史占用不释放。重复相同票不新增版本，重排不改变逻辑 ID。原有票头可重新拉取同账套、同日期范围补全，无迁移、不新增第二套发票或匹配表。

保存后复用 InvoicesImported → matching 建议；所有建议仍须人工确认。确认、撤销、发票换版、作废及红冲继续通过既有 AllocationChanged 更新任务进度。发票先入库、子采购后审核时，在发票比对页“重新生成建议”。

同步结果增加 `completeDetails`（明细完整票数），`pendingDetails` 为待补齐/待核实票数，均来自保存后投影；历史结果无新字段时按原票头阶段解释。前端显示真实计数与匹配入口。接口仍为原 `pull-save`，请求字段不变；本次没有新增迁移。

默认版 open2 文档尚无已核实的明细接口，维持 pending 并明确展示限制。真实专业版明细尚未联调：本机当前没有可用绑定。协议、金额、隔离账本及匹配链路使用假上游测试，不将其描述为生产验收。

### 列表补拉与空明细排查（2026-10-19）

进项发票列表新增单张与当前页批量“重新拉取商品明细”，每次最多 100 张。请求只提交本地发票 ID 与 requestId；服务端读取原来源，校验当前账套并复用原分页、明细、保存和建议事件。请求及结果仍保存在 `sync_lemon_runs`，不新增迁移。接口与失败规则见 [sync 模块](../backend/modules/sync/README.md)。

已有空票头收到不完整商品行时，保存来源行供展示，仍保持 pending；已有逻辑行和历史分配继续保留。空响应不编造明细。同步与补拉结果新增逐票 `detailIssues`，区分“上游空商品行”“缺少匹配字段”“身份歧义”，历史无诊断数据时不推测。

本次浏览器只读检查：服务器原同步结果为 50 张重复、50 张待补齐；柠檬云同一账套“商品明细”页在 2026-07-01 至 2026-10-19 范围显示 0 条。未取得这批票的原始明细响应，不能据此断言每张原票均无商品，也没有把本地修改部署到服务器或触发生产补拉。

验证：后端全量 901 通过、40 跳过；另在随机隔离 MySQL 库执行补拉竞争及既有明细账本测试，5 项通过。前端构建、lint、类型检查与测试通过。隔离数据库和假上游浏览器验证单张、批量、缺单位仍展示商品行、空明细原因以及小屏换行；这不代表生产明细已经补齐。

本次验证：后端全量 858 项通过、35 项因未提供对应专用环境跳过；另用本地随机隔离 MySQL 库通过商品明细、同步与匹配共 13 项测试，覆盖并发去重、换版复核及事件回滚。后端 lint、架构检查、前端 build/lint/typecheck/test:web 通过；补充统计与匹配入口断言后，页面相关 9 项测试通过。使用真实组件和合成数据检查 1280px 桌面、390px 小屏的提示、统计换行与链接键盘焦点；这次静态预览不代表真实账号的浏览器端到端提交已验证。

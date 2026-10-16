# 柠檬云已有账号绑定

本次实现属于 `sync` 模块。页面入口为 `/sync/lemon`，绑定已有柠檬云账号与服务器配置的 open2 应用；不是用柠檬云替代工作台登录。账号绑定、Excel 发票导入和 API 手动拉票是独立状态。已支持选账套按日期手动拉票，见[接入说明](lemon-invoice-sync-plan.md)；商品明细和定时任务仍未接入。

## 服务器准备

在服务器私有环境中配置（不要填写到前端或提交真实凭据）：

```dotenv
APP_ORIGIN=https://invoice.yesion.net
ADMIN_USERNAME=admin
ADMIN_PASSWORD=填写工作台管理员密码
LEMON_OPEN2_APP_KEY=填写柠檬云分配的数字appId
LEMON_OPEN2_APP_SECRET=填写应用密钥
LEMON_OPEN2_HOST=https://open2.ningmengyun.com
LEMON_OPEN2_REDIRECT_URI=https://invoice.yesion.net/api/lemon/oauth/callback
```

`APP_KEY` 沿用项目配置名，值实际是 open2 的数字 `appId`，不是 LemonClaw API Key。应用编号、密钥、环境及回调登记请联系柠檬云对接人员。回调须与 `APP_ORIGIN` 完全同域、使用 HTTPS，登记完整地址；不能只填域名，不能附加查询参数或末尾斜杠。

在部署的目标业务库执行 `npm.cmd run db:upgrade`，绑定迁移为 `0016_sync_lemon_bindings`，手动拉票另需升级至 `0018_sync_lemon_runs`，再构建前端并重启 API。迁移保留已有业务数据。这里描述部署步骤，不表示已对线上执行。

反向代理须把 `/api/` 转发到此后端，并为 `/sync/lemon` 提供前端入口。回调路径不能被外层登录页拦截；临时浏览器 Cookie 和随后管理员确认提供绑定边界。访问日志应对回调隐藏查询字符串，避免记录 `code`。API 默认不记录正文、密码、授权码和令牌。

当前身份会话及待授权流程在单进程内存中，运行一个 API worker。绑定结果持久化。未完成的授权最多保留 10 分钟，服务重启后需重新授权；多实例部署须先改为共享的一次性授权存储。

## 前端操作

1. 打开“数据同步 → 柠檬云”，或直接访问 `/sync/lemon`。
2. 公网访问且未登录时，先输入**本系统工作台**用户名、密码；不是柠檬云密码。本机满足现有回环限制时自动建立工作台会话。
3. 在“绑定已有柠檬云账号”填写已有账号手机号，点击“前往柠檬云授权”。若配置未齐，按钮禁用并显示后端原因。
4. 在柠檬云官方页面登录并授权，系统通过登记回调返回本页。不要直接打开回调地址开始绑定。
5. 检查待绑定手机号，再填写**柠檬云账号密码**并点击“确认绑定此账号”。官方 `LinkUserToApp` 要求密码，所以回到本系统后仍有一次明确确认；密码只用于当次请求，不写入数据库或浏览器存储。
6. 页面显示“已有账号已绑定”才表示收到明确成功结果。若提示结果未知，使用“核实已有绑定”，系统查询官方绑定关系；不会盲目再次提交。无法核实时联系柠檬云确认，不直接清库重试。

如果账号原先已绑定同一应用，可填写手机号发起流程后返回本页，点“核实已有绑定”，由官方查询结果恢复本地状态。绑定成功后继续使用下方 Excel 导入，自动同步仍不可用。

## 接口契约

除固定回调外，入口均要求管理员会话；修改请求还校验同源。服务密钥不能用于绑定。

| 接口 | 请求 | 结果 |
| --- | --- | --- |
| `GET /api/sync/lemon/binding` | 无 | 状态、脱敏手机号、最近确认时间、回调地址，以及 begin/confirm/verify/sync 的 allowed/reason |
| `POST /api/sync/lemon/binding/start` | `{"mobile":"13800000001"}` | 官方 authorizationUrl，并写入 10 分钟 HttpOnly、Secure、SameSite=Lax 临时 Cookie；重新开始使之前流程失效 |
| `GET /api/lemon/oauth/callback?code=...` | 柠檬云跳转 | 仅接收一次授权码，303 跳转 `/sync/lemon?binding=returned`；失败标记 invalid。两种标记都不代表绑定成功 |
| `POST /api/sync/lemon/binding/confirm` | `{"password":"当次账号密码"}` | 验证原身份和 Cookie，调用官方绑定，返回实际状态 |
| `POST /api/sync/lemon/binding/verify` | `{}` | 查询当前应用对应 userId 的手机号，核实后返回绑定状态 |

状态为 `unbound / awaiting_authorization / awaiting_confirmation / binding / unknown / bound`。完整手机号只在待确认时展示。用户身份、应用、上游环境均来自服务器；前端不能传 owner、appId 或成功状态。错误响应不回显上游正文或密钥。

官方仅说明回传 `code`，未承诺 `state`；因此实现使用一次性临时 Cookie 关联原浏览器，回调本身不执行绑定。最终绑定必须由原管理员同源 POST 并提交账号密码。主会话仍使用原 Strict 策略。

## 实现与验证

- `backend/integrations/lemon/existing_account.py`：应用全局令牌、已有账号绑定、绑定查询的官方协议。全局令牌不当作用户业务令牌使用。
- `backend/modules/sync/controller/`、`service/`、`dao/`、`entity/`、`dto/`、`policy/`：HTTP、用例、持久状态和校验。原 NS controller/service/dto 移到同名层目录，兼容原导入入口。
- `frontend/src/modules/sync/LemonBindingPanel.tsx`：状态和操作；应用层复用 identity 的 `SessionProvider`、`RequireSession` 与 invoice 的 Excel 导入。
- `sync_lemon_bindings` 不保存密码、授权码或令牌。提交前以条件更新争用执行权，网络结果未知保留 unknown，进程中断保留 binding；重启不能清除它们。
- `integrations/lemon/invoice_client.py` 获取正式用户 Token 并查询账套、发票。旧未装配的认证/配置/来源/映射原型已删除，历史见 Git；绑定继续复用 `existing_account.py`。

`test_lemon_binding.py` 使用假上游验证真实 HTTP 边界、来源与身份、一用回调、超时、重启、失败及官方协议；`test_lemon_binding_database.py` 验证迁移与条件更新，MySQL 竞争需要配置隔离测试服务器，跳过不代表通过。前端会话复用和失败不自动重试由 `lemon-binding.test.mjs` 覆盖。没有真实应用凭据时无法宣称真实绑定联调成功。

协议依据：[已有账号授权绑定](https://open2.ningmengyun.com/Home/AccountAuthLink)、[授权说明](https://open2.ningmengyun.com/Home/AccountAuthInfo)、[open2 接口描述](https://open2.ningmengyun.com/Content/h5/ApiDecription.html)。

## 页面操作说明

绑定区左侧展示后端返回的真实状态与可操作项，右侧提供“填写手机号 → 官方登录 → 返回确认”的步骤。配置缺失时默认展开管理员说明并显示原因；配置完成、服务重启后点击“刷新状态”。已绑定或结果未知时不显示重新绑定表单，按后端允许的“核实已有绑定”查询。绑定后需在下方查询账套、保存选择并手动拉票，账号绑定本身不代表已拉取发票。绑定响应的 `sync.allowed` 保持 false，拉票操作以 `/api/sync/lemon/invoices/configuration` 的账套级 `allowed/reason` 为准；页面继续保留 Excel 导入。

2026-10-16 核对官方[已有账号](https://open2.ningmengyun.com/Home/AccountAuthLink)及[授权概述](https://open2.ningmengyun.com/Home/AccountAuthInfo)：需申请 appid/appsecret 并登记回调；官方登录返回 code 后仍需由后端调用 LinkUserToApp。该教程明确 userId 与 mobile 相同，password 为待绑定账号密码。测试域名和示例应用编号不可直接作为生产配置。当前页面检查与隔离测试不代表真实账号绑定已验收。

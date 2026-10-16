# 柠檬云已有账号授权回调

## 已实现范围

已实现公开回调入口、登录后的配置查询、管理员发起授权，以及同一浏览器一次性回调上下文。归属 `sync` 模块；授权链接构造复用 `integrations/lemon/auth.py`。

**当前只接收回调，不完成账号绑定、不保存授权码、不换取 Token、不拉发票。** `callbackReceived=true` 表示收到带有格式合法 code 的回调请求，不证明上游授权有效。所有响应均明确区分 `callbackReady` 和 `accountBound`，收到回调仍返回 `accountBound=false`。

前端 `/sync/lemon` 保留 Excel 导入页面，目前没有新增授权设置表单或绑定按钮。发起授权接口为后续界面接入预留，可在已登录管理员会话中使用。不是调用模板即可认为账号已授权。

## 给客服登记的地址

生产环境公开入口固定为：

```text
https://invoice.yesion.net/api/lemon/oauth/callback
```

客服应登记未带查询参数的完整地址。正式域名由服务器 `APP_ORIGIN` 确定，不读取请求的 Host、X-Forwarded-Host，也不接受浏览器提交任意 redirect_uri。`/sync/lemon` 是业务页面，不是此回调路由。

服务器配置：

```dotenv
APP_ORIGIN=https://invoice.yesion.net
LOCAL_BROWSER_ACCESS=false
# 拿到客服分配的正式 AppId 后填写；不要复制文档示例账号。
LEMON_OPEN2_APP_KEY=
```

沿用项目已有管理员密码、业务数据库和监听配置。AppId 可以暂时留空；访问回调入口仍可检查就绪状态，发起授权则明确返回 503。当前回调接收不使用 AppSecret，无需为这一步提交或展示密钥。

更新代码后重新构建并重启服务。Docker 部署依照[部署说明](docker-deploy.md)，例如现有 Compose 部署使用：

```bash
docker compose up -d --build
curl -i https://invoice.yesion.net/api/lemon/oauth/callback
```

预期 HTTP 200，JSON 中 `callbackReady=true`、`callbackReceived=false`、`accountBound=false`。这是入口可达检查，不是授权测试，也不需要携带 code 或登录。

如果部署使用 Nginx，保留项目已有 `/api/` 转发，将该路径转到 FastAPI 并保留查询参数，不能被前端 `try_files` 接管。不要新建另一套后端。为避免授权码进入代理日志，建议在现有 server 内为回调设置精确 location：

```nginx
location = /api/lemon/oauth/callback {
    # 地址替换为当前 /api/ location 正在使用的后端监听地址。
    proxy_pass http://127.0.0.1:3000;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
    access_log off;
}
```

`proxy_pass` 不带 URI 后缀，保留完整原路径及查询参数。修改后执行 `nginx -t` 并使用当前服务的方式重载。端口 3000 只是示例，不代表云服务器实际端口。Python 应用现有 access_log=false 和统一中间件不记录查询参数；云网关、WAF 等日志也不应记录授权码。

## 接口与流程

| 接口 | 身份与请求 | 实际响应 |
| --- | --- | --- |
| `GET /api/lemon/oauth/callback` | 公开，无参数 | 就绪 JSON，绝不表示账号已绑定 |
| `GET /api/lemon/oauth/configuration` | 沿用认证身份 | callbackUrl、callbackReady、bindingReady=false、authorization.allowed/reason |
| `POST /api/lemon/oauth/authorize` | 管理员浏览器会话；同源 Origin；JSON `{"mobile":"实际购买手机号"}` | authorizationUrl、callbackUrl、expiresIn=600、bindingReady=false |
| `GET /api/lemon/oauth/callback?code=...` | 发起浏览器的独立回调 cookie；不要求发送 Strict 的 ns_session | 接收结果，accountBound=false；删除一次性 cookie |

1. 管理员登录后向 authorize 提交手机号，后端校验身份和手机号格式，从服务端配置获取 AppId 并生成官方页面链接；服务密钥不能代替管理员浏览器发起。
2. 响应设置单独 HttpOnly 的 `lemon_callback_context` cookie，仅作用于回调路径、有效 10 分钟；公网使用 Secure + SameSite=Lax，原管理员 ns_session 继续使用 Strict。
3. 浏览器打开返回的 authorizationUrl，在柠檬云输入账号密码。链接仅含官方约定的 appId、mobile、redirect_uri，全部由 URL 编码生成，不含密码或 AppSecret。
4. 平台返回 code。后端检查字段长度、非法字符、重复及多余参数、浏览器上下文、有效期和发起人会话；同一上下文只消费一次，不回显或保存 code。
5. 本阶段返回“已接收授权回调；账号绑定尚未接入”，不调用外部绑定接口。真正绑定功能上线后需要重新授权。

上下文保存于单 API 进程内存，沿用现有 identity 的部署限制。重启、多进程或更换实例后旧上下文失效，返回明确错误，需重新发起。无 cookie、过期、重复回调返回 400；发起人注销或会话过期返回 401；权限或同源不符返回 403。字段校验错误只返回固定中文说明。

公开回调无参数的 GET 不消费已有授权上下文。对于合法 code，消费发生在身份复核之前，避免失效会话反复尝试。替换同一浏览器的授权会使原上下文失效。

## 官方契约与下一阶段

依据[已有账号授权](https://open2.ningmengyun.com/Home/AccountAuthLink)及[记账接口文档](https://open2.ningmengyun.com/Content/h5/AccApiDecription.html)：

- 授权页面：`/OAuthPage/OAPage/Index`，参数为 `appId`、`mobile`、`redirect_uri`；文档只保证回调 `code`，不保证透传 OAuth state。
- 全局应用 Token：`POST /api/OAuth2/AccessToken/GetAppAccessToken`，JSON 中为 appId/appSecret，返回 Data.access_token；expires_in 单位为分钟。
- 账号绑定：`POST /api/OAuth2/LinkUser/LinkUserToApp`，带全局 Bearer Token，JSON 含 appId/appSecret/code/mobile/orgId/userId/password；必须验证 State 和 Data，不能收到 code 就标记成功。

下一阶段须实现显式绑定确认、上游授权核验、安全凭据管理、持久绑定及审计、结果未知时先核实再操作。当前 cookie 仅把请求与发起浏览器关联，不能替代上游核验，也不能直接复用于自动绑定的 CSRF 保护。已有 Token 客户端模板未接入此次路由，其标准 OAuth 假设不能用于生产绑定。

## 验证

针对性测试：`backend/tests/test_lemon_callback.py`。验证公开探测、服务端域名、官方授权参数、浏览器身份、SameSite 行为、输入、过期、重放、注销、重启失效和脱敏响应；使用隔离 SQLite 仅装配既有应用，不验证 MySQL 并发或真实柠檬云。

后端检查按项目规范运行 `npm.cmd run test:api`、`npm.cmd run lint:api`。本阶段未接真实凭据、未执行云服务器部署或正式账号绑定。

# Python 后端与 MySQL 8.0

> 当前前端：旧“记录校对与写回”和“PL 单联查”页面已移除，下文涉及这些页面的操作仅为历史说明。后端接口与配置继续保留；当前页面 `/pl-reconciliation` 只提供实时查询和导出。

## 技术与启动关系

| 部分 | 当前实现 |
| --- | --- |
| 前端 | React＋TypeScript＋Vite，`web/` |
| 业务接口 | Python＋FastAPI，`backend/` |
| NS 网络请求 | HTTPX 客户端，连接池与超时控制，禁止跟随重定向和自动写入重试 |
| M2M | PyJWT＋cryptography，PS256/384/512 或匹配的 ES256/384/512 |
| 数据库 | SQLAlchemy 2＋PyMySQL，MySQL 8.0；本地验证可使用 SQLite |
| 表结构迁移 | Alembic，`backend/migrations/` |
| 运行服务 | Uvicorn，默认一个进程、端口 3000 |

文中的 NS 指 NetSuite；M2M 指机器对机器认证；Token 指访问令牌。框架名称、接口路径、字段名和配置项保留原文，以便与代码对应。

前端调用的 `/api/*` 路径及 JSON 格式与此前版本一致。`npm start` 通过 `scripts/python.mjs` 调用项目 `.venv` 中的 Python，也可直接使用 Python 启动，不要求 Node 运行业务后端。同步 HTTPX 和数据库调用放在 FastAPI 的同步路由中，由框架在线程池中执行。

## 本地启动（Windows PowerShell）

开发联动入口为 `npm.cmd run dev`，同时启动 Vite 和 Python。端口读取根目录 `.env`、`.env.local`、进程环境变量，后者优先；`PORT` 配置后端（默认 3333），`WEB_PORT` 配置前端（默认 5173）。启动器自动按前端端口设置 `APP_ORIGIN`，Vite 代理按后端端口同步。Windows 下启动器移除 `--reload`，避免 Uvicorn 重载广播 Ctrl+C 导致联动退出；修改后端代码后手动重启，前端热更新保留。主动 `Ctrl+C` 停止本次启动的服务，端口占用时不自动结束已有进程。以下 `npm start` 流程为构建后运行方式。

需要 Python 3.11+、前端构建所需 Node.js 22.13+。依赖的实际验证版本锁定在 `backend/requirements.txt`，直接依赖约束在 `requirements.in`。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
npm.cmd install
```

首次配置时，把根目录 `.env.example` 复制为 `.env`；如果已有 `.env` 或 `.env.local`，补齐其中配置，不要覆盖凭证。后端读取 `.env`、`.env.local`、进程环境变量，后者优先级更高。Docker 同样依次读取 `.env` 和 `.env.local`，后者覆盖前者；兼容只保留其中一个文件，详见 [Docker 部署说明](docker-deploy.md)。

```dotenv
APP_ORIGIN=http://localhost:3000
HOST=127.0.0.1
PORT=3000
BUSINESS_MYSQL_HOST=127.0.0.1
BUSINESS_MYSQL_PORT=3306
BUSINESS_MYSQL_DATABASE=financial_invoice_business
BUSINESS_MYSQL_USER=你的数据库用户名
BUSINESS_MYSQL_PASSWORD='你的数据库密码'
ADMIN_USERNAME=admin
LOCAL_BROWSER_ACCESS=true
# 原密码登录API需要此项；本机自动进入不使用该密码。
ADMIN_PASSWORD=
NETSUITE_WRITE_ENABLED=false
```

前端已移除登录表单和退出按钮。设置 `LOCAL_BROWSER_ACCESS=true` 后，页面通过 `POST /api/session/local` 自动建立原管理员身份的会话；要求服务器绑定本机地址、APP_ORIGIN为本机地址，并校验实际来源IP、Host及Origin。未启用时页面显示连接错误，不自动绕过后端。原密码登录API继续保留，使用该API时 `ADMIN_PASSWORD` 必须为非空值并校验用户名、密码、来源和失败次数。NS 侧已经配置的客户端标识（Client ID）、证书标识（Certificate ID）、角色和证书映射直接复用。服务器还需填写：

- NETSUITE_ACCOUNT_ID（账户标识）、NETSUITE_CLIENT_ID（客户端标识）、NETSUITE_CERTIFICATE_ID（证书标识）。
- NETSUITE_PRIVATE_KEY_PATH：服务器私钥路径，不放前端或公开目录。Windows 路径建议使用正斜线。
- NETSUITE_JWT_ALGORITHM：与私钥类型及证书匹配。当前使用 SuiteTalk REST，权限范围（`scope`）应包含 `rest_webservices`。
- NETSUITE_RECORD_TYPES：允许访问的真实记录类型，英文逗号分隔。
- NETSUITE_WRITE_FIELDS：每种记录允许写入的顶层字段。例如 `{"vendorBill":["memo","externalId"]}` 只展示配置格式，不代表创建供应商账单（Vendor Bill）所需的完整字段。

旧模板中的 `NETSUITE_ENVIRONMENT`、`NETSUITE_REST_BASE_URL`、`NETSUITE_ENTITY_ID`、`NETSUITE_ROLE_ID`、`NETSUITE_SUBSIDIARY_ID` 不参与当前 Python 后端的配置读取。请求地址由 `NETSUITE_ACCOUNT_ID` 构造；权限来自 NS 侧的证书、集成及角色映射。业务单据的子公司等字段仍须按实际要求明确填写，不能依赖旧配置项自动设置。

```powershell
npm.cmd run build
npm.cmd run db:upgrade
npm.cmd start
```

打开 http://localhost:3000。数据库未迁移时会拒绝启动并提示迁移命令。`NETSUITE_WRITE_ENABLED=false` 允许认证、读取和预览，禁止创建及更新。

直接使用 Python 的等价命令：

```powershell
.\.venv\Scripts\python.exe -m backend.manage upgrade
.\.venv\Scripts\python.exe -m backend
```

Linux/macOS 使用 `.venv/bin/python`。后台生产机可以只安装 Python、后端文件和前端构建产物 `dist/web/`。

## 前后端独立开发

根目录 `.env.local` 可设置 `PORT=5174`、`WEB_PORT=5173`，分别控制后端和前端端口；两个端口不能相同，必须为 1–65535 的整数。Vite 转发 `/api` 时保留浏览器 Host。分开启动使用 `npm.cmd run dev:api` 与 `npm.cmd run dev:web`，同样自动读取端口并同步来源和代理。浏览器访问 `http://localhost:前端端口`，不要改用 IP 地址或后端端口。修改配置后需要重启开发服务。开发地址仅注入子进程，`npm start` 仍按显式 `APP_ORIGIN` 配置运行。

## 接口运行日志排查

后端终端输出 `ns_api` 接口日志：成功请求输出 INFO `request_completed`，接口 4xx 使用 WARNING、5xx 使用 ERROR，包含 HTTP 方法、路由模板、状态码和耗时（毫秒，计至响应头发出）。使用 `npm.cmd run dev` 联动启动时，前后端日志显示在同一个控制台。未知路由或路由匹配前被拒绝的请求显示 `<unmatched>`。非预期异常额外记录异常类型。

NS 接入层使用 `ns_api.netsuite` 输出 `ns_request_failed`，区分 `token`（认证）、`record`（记录）、`restlet`（脚本）调用，记录上游状态码或网络异常类型（如 `ConnectError`、`ReadTimeout`）及耗时。日志不记录查询参数、路径参数、令牌、私钥、请求/响应正文及异常原文；不增加自动重试。

Uvicorn 的完整访问日志仍关闭，避免将查询参数写入日志。上述失败日志不依赖访问日志开关，默认输出到后端终端，由部署环境负责收集。如果 Vite 提示 `ECONNREFUSED 127.0.0.1:3000`，说明未连接到后端；检查运行 `npm.cmd run dev:api` 的终端中启动异常和监听地址。这类未到达后端的请求只能在代理侧看到错误。

## 接入 MySQL 8.0

正式后端统一读取 `BUSINESS_DATABASE_URL` 或 `BUSINESS_MYSQL_*`；两种方式不能混用。审核、开票任务、供应商群、采购报关、发票、匹配以及保留的回写和审计表共用一个数据库及连接池。不配置业务库时正式启动明确失败，不回退到 SQLite。

```dotenv
BUSINESS_MYSQL_HOST=127.0.0.1
BUSINESS_MYSQL_PORT=3306
BUSINESS_MYSQL_DATABASE=financial_invoice_business
BUSINESS_MYSQL_USER=你的数据库用户名
BUSINESS_MYSQL_PASSWORD='你的数据库密码'
```

分项密码使用原文；若使用完整 URL，删除分项配置并对密码进行 URL 编码。旧 `DATABASE_URL` 不覆盖业务连接，仅支持显式历史迁移与隔离测试。账户、网络和 TLS 由部署环境管理。

已有库核对基础表与发票扩展后运行 `npm.cmd run db:upgrade`。该命令在同一库协调 `backend/business_migrations` 与 `backend/migrations`，保留 `business_alembic_version` 和 `alembic_version` 两个版本表；`db:business:upgrade` 是兼容入口。启动只核对版本，不执行迁移、同步、NS 写入或状态恢复。迁移账号需要建表及索引权限，运行账号需要业务读写及两个版本表读取权限。

目标库尚无应用版本表时，部署工具按当前实体定义补齐应用表；仅允许接管结构一致的既有 `finance_supplier_groups`。先比较既有结构，再创建缺失表，核对最终字段、主键、索引、唯一约束、外键及 InnoDB 引擎后才登记应用版本。已有应用版本表则正常执行历史增量迁移。发现其他未登记历史表或结构差异时停止，不能盲目 stamp 或删表重试。MySQL DDL 不能整批回滚，中途失败须检查实际结构后处理。

共用连接池不自动合并所有事务。保留现有审核、审计、任务同事务及匹配、占用同事务；跨用例事务仍由 Service 显式传递同一个 Connection。

## 历史应用库合入业务库

切换连接不会自动复制历史记录。先停止全部 API 和任务进程，备份旧 SQLite 及目标 MySQL，核对源库应用版本与当前代码一致，再执行：

```powershell
npm.cmd run db:upgrade
.\.venv\Scripts\python.exe -m backend.manage import-application --services-stopped --source-database-url "sqlite:///./data/ns-python.sqlite"
npm.cmd start
```

复制按外键依赖顺序在目标库一个事务中进行，保留原主键、身份/账套、审核快照、任务、旧 PDF、合同归档路径、通知历史、审计及回写状态和锁。同主键同内容可重跑；同主键不同内容整笔回滚。提交前逐字段核对全部源记录；不覆盖目标额外记录，不删除源文件，不调用 NS 或企微，也不把 executing/unknown 改成普通失败。

`--services-stopped` 是维护操作声明，不会自动终止进程。切换前必须实际停止写入；恢复旧服务前需处理切换后新增数据，不能只改回旧连接。原 Node 数据库不属于本工具支持的源结构。

2026-10-09 本机切换已完成：105 份审核快照、26 条审核头、3 个开票任务、3 条合同记录、3 条通知版本及3条审核审计迁入业务 MySQL，复制前后逐字段一致。切换前既有15张业务表的数据摘要保持一致；原SQLite文件保留，备份位于本机 data/database-transfer-20261009-201646（不入Git）。后端已重启，业务库状态、任务列表与全部详情、供应商群及发票列表接口返回200。本机结果不代表其他部署环境已切换。

## 单域名 HTTPS

```text
浏览器 / 飞书 → https://你的域名
                  ├─ /        → 构建后的 React 页面
                  └─ /api/*   → Python FastAPI → M2M → NS
                                      ↓
                                  MySQL 8.0
```

后端可以直接提供 HTTPS，不要求反向代理：

```dotenv
APP_ORIGIN=https://你的真实域名
HOST=0.0.0.0
PORT=443
TLS_CERT_PATH=C:/secure/tls/fullchain.pem
TLS_KEY_PATH=C:/secure/tls/private.key
```

需要公司公网 443 入站及域名解析，证书路径按实际系统修改。证书续期后重启加载。若已有公司 HTTPS 反向代理，TLS 路径留空、HOST=127.0.0.1、PORT=3000，APP_ORIGIN 仍为公网 HTTPS 域名即可。配置开机启动、日志收集、数据库备份由服务器服务管理器处理，npm start 本身不会注册系统服务。

## 写入约束与恢复

当前本机浏览器自动建立管理员会话，无需输入密码；owner仍为 `user:ADMIN_USERNAME`，不会改变原数据归属。远程地址不允许使用本机入口，转发头不作为本机证明；公网部署必须关闭LOCAL_BROWSER_ACCESS并另行提供经过认证的访问入口，当前前端不提供远程登录表单。服务调用仍使用独立 SERVICE_API_KEY（至少32位）；浏览器使用HttpOnly／SameSite=Strict会话Cookie，变更请求继续校验Origin。生产 HTTPS 下的 Cookie 设置 `Secure` 属性。NS 访问令牌和私钥不会返回浏览器。

NS 回写（预览、执行、未知结果保护、`recover` 恢复命令）已移至 `archive/writeback` 分支；主线保留 `ns_previews`、`ns_target_locks`、`ns_audit` 的表和数据，不再有代码读写。

默认单个 Uvicorn 进程；会话和登录限流保存在内存，不要直接用多进程部署。后续扩容前应先外置会话和限流。完整分页同步、自动发票匹配、多角色审批、飞书用户登录和自定义 RESTlet 适配仍需按业务补齐。

## 接口与测试

通过 `npm.cmd start` 或 `npm.cmd run dev:api` 启动时，终端记录 API 成功请求的 `request_completed`（INFO），以及失败请求的 `request_failed`（4xx 为 WARNING、5xx 为 ERROR），包含方法、路由模板、状态码和响应头发出前的耗时。日志不包含查询值、正文、令牌或原始异常内容。Uvicorn 原始访问日志保持关闭，避免重复输出及原始 URL 泄露。修改启动日志配置后须停止并重新启动命令，仅热重载业务文件不会更新父进程日志配置。

| 接口 | 用途 |
| --- | --- |
| GET /api/health | 不暴露配置的健康检查 |
| POST /api/session/local | 仅本机同源浏览器自动建立会话 |
| POST /api/session；DELETE /api/session | 保留的密码登录／退出API，当前前端不调用 |
| GET /api/ns/status；POST /api/ns/connect | 配置状态／M2M 验证 |
| GET /api/openapi.json | 登录后读取接口协议 |

`npm.cmd test` 构建前端并运行 Python 测试，不使用真实 NS 凭证。`npm.cmd run lint:api` 检查代码，`npm.cmd run db:sql:mysql` 输出 MySQL 迁移 SQL 供审阅。测试覆盖签名、访问令牌缓存、防重定向、登录、防跨站请求伪造（CSRF）和权限隔离。

真实 MySQL 8.0 集成测试为可选项：通过进程环境变量 MYSQL_TEST_URL 指向一个 **预先创建、没有表、名称以 ns_test_ 开头** 的专用 MySQL 8.0 测试库，再运行 `npm.cmd run test:api`。测试不会自动删除该库；没有提供连接配置时明确跳过，SQL 编译检查不能替代真实数据库联调。

技术依据：[FastAPI 同步路由与线程池](https://fastapi.tiangolo.com/async/)、[SQLAlchemy 的 MySQL 与 PyMySQL 支持](https://docs.sqlalchemy.org/en/20/dialects/mysql.html)、[PyJWT 使用说明](https://pyjwt.readthedocs.io/en/stable/usage.html)、[Alembic 数据库迁移教程](https://alembic.sqlalchemy.org/en/latest/tutorial.html)。

NS 协议依据：[M2M 的 JWT 请求令牌结构](https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/section_162790605110.html)、[创建记录](https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/section_1545141395.html)、[更新记录](https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/section_1545142173.html)、[外部标识使用说明](https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/section_156334828635.html)。

## P0模块化重构

当前模块职责、兼容入口与目录见[后端模块说明](../backend/README.md)。既有表结构和迁移保留；无调用方的 `/api/ns/*` 接口与回写接口已删除。

运行 `npm.cmd run check` 完成本地质量检查。尚未生成OpenAPI TypeScript客户端、部署CI或配置远程分支保护，不将本地检查描述为远程强制门禁。

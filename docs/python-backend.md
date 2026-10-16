# Python 后端与 MySQL 8.0

> 当前前端：旧“记录校对与写回”和“PL 单联查”页面已移除，下文涉及这些页面的操作仅为历史说明。后端接口与配置继续保留；当前页面 `/pl-reconciliation` 只提供实时查询和导出。

## 技术与启动关系

| 部分 | 当前实现 |
| --- | --- |
| 前端 | React＋TypeScript＋Vite＋react-router，`frontend/`（独立 package.json） |
| 业务接口 | Python＋FastAPI，`backend/` |
| NS 网络请求 | HTTPX 客户端，连接池与超时控制，禁止跟随重定向和自动写入重试 |
| M2M | PyJWT＋cryptography，PS256/384/512 或匹配的 ES256/384/512 |
| 数据库 | SQLAlchemy 2＋PyMySQL，MySQL 8.0；本地验证可使用 SQLite |
| 表结构迁移 | Alembic：新迁移链 `backend/migrations/`（版本表 `schema_version`）；旧迁移链代码已删除，旧库表不动 |
| 运行服务 | Uvicorn，默认一个进程、端口 3000 |

文中的 NS 指 NetSuite；M2M 指机器对机器认证；Token 指访问令牌。框架名称、接口路径、字段名和配置项保留原文，以便与代码对应。

前端调用的 `/api/*` 路径及 JSON 格式与此前版本一致。`npm start` 通过 `scripts/python.mjs` 调用项目 `.venv` 中的 Python，也可直接使用 Python 启动，不要求 Node 运行业务后端。同步 HTTPX 和数据库调用放在 FastAPI 的同步路由中，由框架在线程池中执行。

## 本地启动（Windows PowerShell）

开发联动入口为 `npm.cmd run dev`，同时启动 Vite 和 Python。端口读取根目录 `.env`、`.env.local`、进程环境变量，后者优先；`PORT` 配置后端（默认 3333），`WEB_PORT` 配置前端（默认 5173）。启动器自动按前端端口设置 `APP_ORIGIN`，Vite 代理按后端端口同步。Windows 下启动器移除 `--reload`，避免 Uvicorn 重载广播 Ctrl+C 导致联动退出；修改后端代码后手动重启，前端热更新保留。主动 `Ctrl+C` 停止本次启动的服务，端口占用时不自动结束已有进程。以下 `npm start` 流程为构建后运行方式。

需要 Python 3.11+、前端构建所需 Node.js 22.13+。依赖的实际验证版本锁定在 `backend/requirements.txt`，直接依赖约束在 `requirements.in`。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
npm.cmd run setup
```

`npm.cmd run setup` 在 `frontend/` 中按锁文件安装前端依赖；根目录 `package.json` 只是命令入口，不安装依赖。

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
# 所有浏览器均需账号密码登录；填写非空密码后重启后端。
ADMIN_PASSWORD=
NETSUITE_WRITE_ENABLED=false
```

所有业务页面统一显示账号密码登录入口，登录后继续原页面，右上角提供退出。账号读取 `ADMIN_USERNAME`（默认 admin），`ADMIN_PASSWORD` 必须为非空值，无默认密码；后端校验账号、密码、来源及失败次数。本机免密入口 `POST /api/session/local` 保留一个版本并固定拒绝，旧 `LOCAL_BROWSER_ACCESS` 配置不再读取。NS 侧已经配置的客户端标识（Client ID）、证书标识（Certificate ID）、角色和证书映射直接复用。服务器还需填写：

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

Linux/macOS 使用 `.venv/bin/python`。后台生产机可以只安装 Python、后端文件和前端构建产物 `frontend/dist/`。

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

分项密码使用原文；若使用完整 URL，删除分项配置并对密码进行 URL 编码。旧 `DATABASE_URL` 已不读取；隔离测试通过显式 engine 注入。账户、网络和 TLS 由部署环境管理。

创建空 MySQL 数据库并配置连接后运行 `npm.cmd run db:upgrade`，只执行新迁移链和 `schema_version`；已有新库同样向前升级。`db:business:upgrade` 为兼容别名。启动只核验新版本，不要求旧六表、旧版本表，不自动迁移、同步或清除状态。运行账号读取 schema_version，迁移账号另需 DDL 权限。

新迁移链的 MySQL 版本字段使用 `VARCHAR(128)`，以容纳完整迁移名。升级工具在迁移锁内自动扩宽已存在的短 `schema_version.version_num` 字段，保留版本值和业务记录，不缩短已有较长字段，不修改两张旧版本表。如果此前已经因版本名过长而中断，MySQL 可能保留该步已经执行的 DDL；须先核对实际字段与版本记录，不能直接删表或盲目重跑。

`0010`—`0015` 是分模块中文备注迁移：覆盖 26 张业务表、422 个字段，不更改数据或字段约束。SQL 快照位于 `backend/migrations/comments_20261015/`，部署时须随迁移文件一起打包；快照独立于运行时实体，后续业务改动不能改写这些历史文件。SQLite 不支持列备注，执行时只推进版本；MySQL 的备注由 `INFORMATION_SCHEMA.COLUMNS.COLUMN_COMMENT` 与 `TABLES.TABLE_COMMENT` 查看。已有库执行 `npm.cmd run db:upgrade` 后生效；仍处于更早版本的库会先执行原有迁移，不能把整个升级视为只补备注。

`0005`—`0009` 分模块增加依据、任务后继、发票版本和分配复核字段。已有 v2 历史保留，无法从原快照准确恢复的标记待复核，原占用不释放；新版本迁移拒绝降级删除证据。结构 SQL（`db:sql:mysql` / `schema-sql`）仅供审阅，不执行数据回填，部署必须在线运行 upgrade。MySQL DDL 不能整体回滚，中断后应核对实际字段和版本，不能盲目重跑或 stamp。

关联写共用账本命名锁和发布方事务。需要修复任务投影时可运行 `python -m backend.manage rebuild-ledger`，由 matching 按持久台账发布绝对合计；不会自动核实待复核记录。正常启动不运行该修复。

## 历史应用库数据

旧数据为测试数据，按 2026-10-10 的决定不迁移；原 `import-application` 导入命令已删除。旧 SQLite 文件（默认 `data/ns-python.sqlite`）不再被读取，是否保留由管理员决定。

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

本机和远程浏览器均通过账号密码登录；owner 仍为 `user:ADMIN_USERNAME`，不会改变原数据归属。会话有效期 8 小时，退出立即撤销，后端重启需要重新登录；业务请求收到 401 时页面回到登录界面。公网部署须配置真实 HTTPS APP_ORIGIN，浏览器地址和 APP_ORIGIN 必须一致。服务调用仍使用独立 SERVICE_API_KEY（至少32位）；浏览器使用HttpOnly／SameSite=Strict会话Cookie，变更请求继续校验Origin。生产 HTTPS 下的 Cookie 设置 `Secure` 属性。NS 访问令牌和私钥不会返回浏览器。

NS 回写（预览、执行、未知结果保护、`recover` 恢复命令）已移至 `archive/writeback` 分支；主线保留 `ns_previews`、`ns_target_locks`、`ns_audit` 的表和数据，不再有代码读写。

默认单个 Uvicorn 进程；会话和登录限流保存在内存，不要直接用多进程部署。后续扩容前应先外置会话和限流。完整分页同步、自动发票匹配、多角色审批、飞书用户登录和自定义 RESTlet 适配仍需按业务补齐。

## 接口与测试

通过 `npm.cmd start` 或 `npm.cmd run dev:api` 启动时，终端记录 API 成功请求的 `request_completed`（INFO），以及失败请求的 `request_failed`（4xx 为 WARNING、5xx 为 ERROR），包含方法、路由模板、状态码和响应头发出前的耗时。日志不包含查询值、正文、令牌或原始异常内容。Uvicorn 原始访问日志保持关闭，避免重复输出及原始 URL 泄露。修改启动日志配置后须停止并重新启动命令，仅热重载业务文件不会更新父进程日志配置。

| 接口 | 用途 |
| --- | --- |
| GET /api/health | 不暴露配置的健康检查 |
| GET /api/session | 检查登录状态，无会话返回 401 |
| POST /api/session；DELETE /api/session | 全系统账号密码登录／退出 |
| POST /api/session/local | 旧客户端兼容入口，固定拒绝免密登录；一个版本后移除 |
| GET /api/ns/status；POST /api/ns/connect | 配置状态／M2M 验证 |
| GET /api/openapi.json | 登录后读取接口协议 |

`npm.cmd test` 构建前端并运行 Python 测试，不使用真实 NS 凭证。`npm.cmd run lint:api` 检查代码，`npm.cmd run db:sql:mysql` 输出 MySQL 迁移 SQL 供审阅。测试覆盖签名、访问令牌缓存、防重定向、登录、防跨站请求伪造（CSRF）和权限隔离。

真实 MySQL 测试设置 `BUSINESS_MIGRATION_TEST_SERVER_URL=mysql+pymysql://测试用户@127.0.0.1:端口/mysql` 后运行 `npm.cmd run test:api`。测试随机创建专用数据库并在结束后删除，仅可使用隔离测试实例。未配置时跳过，不以 SQLite 声称并发通过。

技术依据：[FastAPI 同步路由与线程池](https://fastapi.tiangolo.com/async/)、[SQLAlchemy 的 MySQL 与 PyMySQL 支持](https://docs.sqlalchemy.org/en/20/dialects/mysql.html)、[PyJWT 使用说明](https://pyjwt.readthedocs.io/en/stable/usage.html)、[Alembic 数据库迁移教程](https://alembic.sqlalchemy.org/en/latest/tutorial.html)。

NS 协议依据：[M2M 的 JWT 请求令牌结构](https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/section_162790605110.html)、[创建记录](https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/section_1545141395.html)、[更新记录](https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/section_1545142173.html)、[外部标识使用说明](https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/section_156334828635.html)。

## P0模块化重构

当前模块职责、兼容入口与目录见[后端模块说明](../backend/README.md)。既有表结构和迁移保留；无调用方的 `/api/ns/*` 接口与回写接口已删除。

运行 `npm.cmd run check` 完成本地质量检查。尚未生成OpenAPI TypeScript客户端、部署CI或配置远程分支保护，不将本地检查描述为远程强制门禁。

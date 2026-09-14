# Python 后端与 MySQL 8.0

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

需要 Python 3.11+、前端构建所需 Node.js 22.13+。依赖的实际验证版本锁定在 `backend/requirements.txt`，直接依赖约束在 `requirements.in`。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
npm.cmd install
```

首次配置时，把根目录 `.env.example` 复制为 `.env.local`；如果已有 `.env.local`，补齐其中配置，不要覆盖凭证。后端读取 `.env`、`.env.local`、进程环境变量，后者优先级更高。

```dotenv
APP_ORIGIN=http://localhost:3000
HOST=127.0.0.1
PORT=3000
DATABASE_URL=sqlite:///./data/ns-python.sqlite
ADMIN_USERNAME=admin
ADMIN_PASSWORD=请替换为实际后台密码
NETSUITE_WRITE_ENABLED=false
```

上述密码只是占位说明，不是预置账号密码。`ADMIN_PASSWORD` 必须填写非空值，不设最短字符数限制；登录仍校验用户名、密码、请求来源和失败次数。NS 侧已经配置的客户端标识（Client ID）、证书标识（Certificate ID）、角色和证书映射直接复用。服务器还需填写：

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

设置 `APP_ORIGIN=http://localhost:5173`，分别在两个终端运行 `npm.cmd run dev:api` 与 `npm.cmd run dev`。Python 后端监听 3000，Vite 监听 5173 并转发 `/api`；浏览器只访问 5173。部署前把 APP_ORIGIN 改回正式域名。

## 接入 MySQL 8.0

由数据库管理员预先建立专用数据库和用户；此项目不会创建或修改数据库账号。数据库使用 utf8mb4，表迁移明确指定 InnoDB、utf8mb4 和 utf8mb4_bin，事务写入与任务锁使用同一个数据库。

修改服务器 `.env.local`：

```dotenv
DATABASE_URL=mysql+pymysql://invoice_user:URL_ENCODED_PASSWORD@127.0.0.1:3306/ns_invoice?charset=utf8mb4
```

把账户、密码、地址及库名替换为真实值。密码中的 `@`、`#`、`%` 等字符需要 URL 编码。例如密码中的 `@` 写为 `%40`。不要把连接串放在前端、公开文档或 Git 中。跨主机数据库连接按公司要求配置网络权限及 TLS。

执行 `npm.cmd run db:upgrade` 后再启动后端。迁移账号需要建表和索引权限；运行时账号需要业务表读写权限及读取 alembic_version 权限。本次表结构：

| 表 | 用途 |
| --- | --- |
| ns_previews | 绑定账户及操作者的不可变预览、原记录快照、执行状态和结果 |
| ns_target_locks | 按 NS 账户和目标记录唯一约束，实现持久执行锁 |
| ns_audit | 预览、取得执行权、成功、结果未知（`unknown`）与离线恢复记录 |
| alembic_version | 已应用的表结构版本 |

锁实现使用标准唯一约束和事务，不依赖 SQLite 的部分索引。大 JSON 快照在 MySQL 使用 LONGTEXT，时间戳使用 BIGINT。后续增加金额业务列应明确小数位，采用 Decimal/DECIMAL；当前接口不计算金额，仅传递和比较字段。

**修改 DATABASE_URL 只切换数据库，不会复制已有数据。** 本地 SQLite 的任务记录和旧 Node `data/ns.sqlite` 都不会自动导入 MySQL。正式切换前要停止写入、备份、核对执行中及结果未知（`unknown`）的任务，再设计数据导入，不能把新空库当成已有任务已完成。原 Node 的 DATABASE_PATH 已停用；仅保留旧变量时会明确提示设置 DATABASE_URL。

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

当前为单管理员登录，服务调用使用独立 SERVICE_API_KEY（至少 32 位）；网页登录使用带 `HttpOnly` 属性的会话 Cookie，变更请求校验请求来源（`Origin`）。生产 HTTPS 下的 Cookie 设置 `Secure` 属性。NS 访问令牌和私钥不会返回浏览器。

预览有效期 15 分钟。创建使用 POST 方法和稳定的外部标识（`externalId`）；更新只接受内部标识（Internal ID），使用 PATCH 方法。预览通过 GET 方法读取记录并验证字段白名单，不意味着 NS 全部业务规则已通过。执行先持久占用目标，再读取并核对 NS，成功后在同一数据库事务中保存结果、释放锁并写审计。

写入失败或超时后标记为“结果未知”（`unknown`），不会自动重试；写入后结果持久化失败时保留“执行中”（`executing`）状态和锁，同样禁止再次提交。正常启动接口服务不会重置其他进程留下的执行状态。

如果服务异常中断，**停止所有接口服务和任务进程后**运行：

```powershell
.\.venv\Scripts\python.exe -m backend.manage recover --services-stopped
```

该命令把当前 NS 账户的“执行中”（`executing`）任务标记为“结果未知”（`unknown`），保留目标锁，不发起 NS 请求。再通过 NS 记录、外部标识（`externalId`）或日志核对结果。当前没有自动解除“结果未知”状态的接口。

本地数据库锁不能阻止 NS 内扫描任务或其他系统在检查后修改同一记录，因此仍需挑选不被现有任务处理的测试单。跨系统原子版本检查需要 NS 端协作，当前没有实现。

默认单个 Uvicorn 进程；会话和登录限流保存在内存，不要直接用多进程部署。后续扩容前应先外置会话和限流。完整分页同步、自动发票匹配、多角色审批、飞书用户登录和自定义 RESTlet 适配仍需按业务补齐。

## 接口与测试

| 接口 | 用途 |
| --- | --- |
| GET /api/health | 不暴露配置的健康检查 |
| POST /api/session；DELETE /api/session | 登录／退出 |
| GET /api/ns/status；POST /api/ns/connect | 配置状态／M2M 验证 |
| GET /api/ns/records/:type；GET /api/ns/records/:type/:id | 前 50 条索引／指定记录 |
| POST /api/ns/preview | 操作类型（`operation`）、记录类型（`type`）、记录标识（`id`，更新时必填）、拟写入内容（`payload`） |
| POST /api/ns/execute | 预览标识（`previewId`）、确认标记（`confirm=true`）；禁止附加替换写入内容 |
| GET /api/ns/jobs；GET /api/ns/jobs/:id | 当前身份、当前 NS 账户的任务 |
| GET /api/openapi.json | 登录后读取接口协议 |

`npm.cmd test` 构建前端并运行 Python 测试，不使用真实 NS 凭证。`npm.cmd run lint:api` 检查代码，`npm.cmd run db:sql:mysql` 输出 MySQL 迁移 SQL 供审阅。测试覆盖签名、访问令牌缓存、防重定向、登录、防跨站请求伪造（CSRF）、权限隔离、预览、并发锁、超时和离线恢复。

真实 MySQL 8.0 集成测试为可选项：通过进程环境变量 MYSQL_TEST_URL 指向一个 **预先创建、没有表、名称以 ns_test_ 开头** 的专用 MySQL 8.0 测试库，再运行 `npm.cmd run test:api`。测试不会自动删除该库；没有提供连接配置时明确跳过，SQL 编译检查不能替代真实数据库联调。

技术依据：[FastAPI 同步路由与线程池](https://fastapi.tiangolo.com/async/)、[SQLAlchemy 的 MySQL 与 PyMySQL 支持](https://docs.sqlalchemy.org/en/20/dialects/mysql.html)、[PyJWT 使用说明](https://pyjwt.readthedocs.io/en/stable/usage.html)、[Alembic 数据库迁移教程](https://alembic.sqlalchemy.org/en/latest/tutorial.html)。

NS 协议依据：[M2M 的 JWT 请求令牌结构](https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/section_162790605110.html)、[创建记录](https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/section_1545141395.html)、[更新记录](https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/section_1545142173.html)、[外部标识使用说明](https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/section_156334828635.html)。

## P0模块化重构

当前模块职责、兼容入口与目录见[后端模块说明](../backend/README.md)。既有表结构、迁移和/api/ns/*调用方式保留。

新增辅助接口：`POST /api/ns/query`接收type、id、mode（list/detail），后端校验查询；`POST /api/ns/preview-text`接收operation、type、id、payloadText，后端解析并校验编辑内容；`GET /api/ns/jobs/{id}/view`返回原预览字段及stateLabel、actions.execute.allowed/reason。旧execute接口仍在提交时重做校验，前端allowed不是写入授权。

运行 `npm.cmd run check` 完成本地质量检查。尚未生成OpenAPI TypeScript客户端、部署CI或配置远程分支保护，不将本地检查描述为远程强制门禁。

# NS 发票对账系统

使用后端 M2M 凭证连接 NetSuite，完成“拉取记录 → 人工校对 → 生成预览 → 确认写回”。前后端独立开发和构建，部署时共用一个域名。

## 当前架构

| 部分 | 技术与职责 |
| --- | --- |
| 前端 | React＋TypeScript＋Vite，展示记录和校对结果 |
| 后端 | Python＋FastAPI，提供 `/api/*` 接口及构建后的前端页面 |
| NS 接入 | HTTPX 调用 SuiteTalk REST；PyJWT＋cryptography 完成 M2M 签名 |
| 数据库 | SQLAlchemy＋PyMySQL 支持 MySQL 8.0；本地验证可使用 SQLite |
| 数据库迁移 | Alembic 管理表结构版本 |

`npm start` 启动的是 Python 后端。Vite 用于前端开发和打包，正式运行时不需要单独启动 Vite 服务。后端支持直接提供 HTTPS，也可接入公司已有反向代理。

## 本地启动

需要 Python 3.11+ 和 Node.js 22.13+。在项目根目录使用 Windows PowerShell 执行：

```powershell
npm.cmd install
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
```

首次配置时，参照 [.env.example](.env.example) 配置 `.env`；已有配置时补齐缺项即可。在 `.env` 设置 `LOCAL_BROWSER_ACCESS=true`，填写 NS 账户及 M2M 配置、允许访问的记录类型和写入字段。私钥只提供服务器路径，实际写入先保持 `NETSUITE_WRITE_ENABLED=false`。

数据库由 `DATABASE_URL` 指定，本地默认使用 `data/ns-python.sqlite`。MySQL 8.0 连接格式、凭证说明及配置示例见 [Python 后端与 MySQL 配置](docs/python-backend.md)。

```powershell
npm.cmd run build
npm.cmd run db:upgrade
npm.cmd start
```

打开 [本地系统](http://localhost:3000)，首页进入 PL 采购报关核对，提交查询时自动建立本机会话，无需输入账号密码。按 `Ctrl+C` 停止服务。Linux/macOS 使用 `npm` 和 `.venv/bin/python`，详细步骤见后端文档。

## 开发与检查

前后端独立开发时，将 `APP_ORIGIN` 设为 `http://localhost:5173`，在两个终端分别运行 `npm.cmd run dev:api` 和 `npm.cmd run dev`，浏览器访问 [前端开发入口](http://localhost:5173)。

| 命令 | 用途 |
| --- | --- |
| `npm.cmd test` | 构建前端并运行 Python 测试，使用模拟 NS |
| `npm.cmd run lint:api` | 检查 Python 代码 |
| `npm.cmd run check` | 一次执行lint、类型、架构边界、格式、构建与测试 |
| `npm.cmd run typecheck` | 独立TypeScript严格类型检查 |
| `npm.cmd run check:architecture` | 检查模块依赖及前端请求/演示边界 |
| `npm.cmd run format:web` / `format:api` | 统一格式化前端 / Python |
| `npm.cmd run format:check` | 只检查格式，不修改文件 |
| `npm.cmd run db:upgrade` | 应用数据库迁移 |
| `npm.cmd run db:sql:mysql` | 输出 MySQL 建表脚本供审阅 |
| `npm.cmd run db:business:check` | 只读检查独立六表 MySQL 业务库连接 |

## 目录与文档

| 路径 | 用途 |
| --- | --- |
| `web/` | 当前前端入口与 Vite 配置 |
| `backend/` | Python 接口、M2M 认证、数据库迁移和测试 |
| `docs/python-backend.md` | NS 配置、MySQL 8.0、HTTPS 部署、接口及任务恢复的详细说明 |
| `scripts/` | 启动辅助脚本，`python.mjs` 让 npm 命令调用 Python |
| `app/` | 原有界面原型，由当前前端的 `/demo` 页面复用 |

访问 `/demo` 可查看模拟的发票工作台、匹配和异常处理页面。演示数据及连接状态不代表真实 NS 状态，演示按钮不会操作 NS。

已接入 [PL 采购报关核对](http://localhost:5173/pl-reconciliation)：输入 PL 和申报公司后，通过后端 M2M 读取真实采购与报关明细，按 PL＋公司上下展示并导出本次查询的 Excel。旧 `/demo?view=pl` 地址会转到正式入口，原 PL 演示数据和静态导出已移除。当前来源为 NS 自定义记录 REST 接口，尚未接入搜索 839/954 的 GROUP/MAX/SUM 汇总；见 [核对模块说明](web/modules/reconciliation/README.md)。

历史 Vinext 原型保留 `dev:prototype`、`build:prototype` 和 `test:prototype` 脚本。`.openai/hosting.json` 仍被原型构建引用；Cloudflare 仅供这条原型预览链路使用，不属于 Python 后端的部署要求。未接入的 ChatGPT 登录、D1/Drizzle 示例及旧 Node 后端已移除，现有业务数据和 Python 数据库迁移继续保留。

`.next/`、`.vinext/`、`.wrangler/`、`.ruff_cache/` 是工具生成目录，可在相关进程停止后清理，后续运行对应工具时可能重新生成。`.venv/` 和 `node_modules/` 是已安装的运行依赖，不作为无用文件删除。

## 当前能力与边界

旧“记录校对与写回”和“PL 单联查”页面及导航已删除，首页进入 `/pl-reconciliation`。后端仍保留 PL 联查能力：复用 NS 读取链路，按 PL 联查采购及关联报关明细。本机沙箱映射已配置，并通过 `PL2510280002` 的真实只读联查；其他部署仍需配置环境变量。映射可读副本见 [完整字段 JSON](docs/netsuite-pl-lookup.json)，配置方式与验证边界见 [PL 单联查说明](docs/pl-lookup.md)。不依赖已保存搜索，不做自动商品匹配或金额分摊。

另有 [NS Suitelet 两份搜索实时联查方案](docs/ns-suitelet-realtime-plan.md)及本地独立脚本与部署说明（`SuiteScripts/pl_lookup/README.md`，按忽略规则不纳入此仓库）：已提供六个 NS 脚本文件、配置模板及本地模拟测试，首次打开为空表单，PL 必填，按 PL 读取采购与报关明细并归组展示，支持复用本次查询缓存导出 Excel；不接入现有系统，尚未在 NS 部署或验收。

独立六表 MySQL 业务库已接入连接检查、按PL保存采购报关及本地查询。使用 `BUSINESS_MYSQL_*` 配置，与现有 `DATABASE_URL` 分开；不会自动建表或迁移。相关后端接口保留；“PL 单联查”前端入口已移除，当前核对页不提供本地保存操作。配置及验收见 [PL保存说明](docs/pl-storage.md) 和 [业务MySQL](docs/mysql/README.md#接入本地-mysql)。

后端保留记录查询、预览、确认创建或更新，以及持久任务和重复提交拦截；对应旧前端页面已移除。自动发票匹配、完整分页同步、具体业务字段映射、已有 RESTlet 适配尚未接入。

本版本按单个后端进程运行。真实 NS 与 MySQL 8.0 联调尚未完成；写入结果未知时必须人工核对，不能自动重试。切换数据库不会自动迁移已有任务，详细约束及恢复方法见 [后端文档](docs/python-backend.md)。

## 模块化开发

已按P0方案整理真实运行链路，见[后端模块说明](backend/README.md)、[完整架构方案](docs/architecture-plan.md)、[前端统一规范](docs/frontend-conventions.md)与[AI协作规范](AGENTS.md)。新功能进入对应模块；Controller处理接口，Service处理业务和事务，DAO处理SQL，Mapper处理对象转换。

原型演示已按视图拆入app/demo并按需加载；正式前端不再加载原型模拟数据。发票与子采购单多对多分配规则已写入方案，真实匹配业务尚待后续实施。

前端现已统一导航与页面框架：PL 核对和七个演示模块使用同一菜单、页头和布局，页面标注真实／演示数据来源。首页仍进入 PL 核对，原 `/demo?view=...` 地址继续可用。

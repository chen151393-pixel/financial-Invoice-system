# NS 发票对账系统

React + TypeScript + Vite 前端，Python + FastAPI + SQLAlchemy + Alembic 后端。系统围绕 NS 采购报关来源、财务审核、开票跟进、发票导入和本地匹配组织；正式运行由 FastAPI 提供 API 与构建后的前端页面。

## 从哪里开始

| 需要了解什么 | 入口 |
| --- | --- |
| 目标架构与开发规则（分步实施中） | [架构设计 v2](docs/architecture/README.md) |
| 目录归属、启动入口、配置和依赖 | [项目目录与架构地图](docs/project-structure.md) |
| 页面 → 接口 → Service → 数据表及未衔接部分 | [系统整体链路与实现关系](docs/system-chain.md) |
| 配置、部署、数据库、方案和模块文档 | [文档索引](docs/README.md) |
| Linux ECS Docker 部署 | [Docker 部署说明](docs/docker-deploy.md) |
| 编码约束与分层规则 | [协作规范](AGENTS.md)、[架构方案](docs/architecture-plan.md) |
| 界面与前端工程规范 | [设计基准](design.md)、[前端统一规范](docs/frontend-conventions.md) |
| 历次功能、数据补拉和验收记录 | [历史实施记录](docs/history/implementation-notes.md) |

## 当前能力与边界

以下描述代码接入情况；不表示目标环境已完成迁移、NS 脚本部署或真实联调。

| 入口 | 当前实现 | 主要边界 |
| --- | --- | --- |
| `/sync/ns` | NS 分页读取；子采购和报关可补齐来源并保存 | 没有持久定时同步队列；依赖来源接口及字段配置 |
| `/pl-reconciliation`（默认首页） | 通过 NS 共用脚本实时查询采购报关依据 | 只读对照，页面查询不自动入库或审核 |
| `/finance-reconciliation` | 本地来源核对、整单人工审核、不可变快照 | 审核通过不等于获得完整可分配开票额度 |
| `/invoice-followup` | 审核后生成任务、合同共享盘归档、供应商群配置、通知草稿和人工发送登记 | 企微自动发送、任务收票与收齐判断未接入 |
| `/sync/lemon`、`/invoices` | Excel 预览、确认导入、发票查询 | 仅导入“采购固定资产”；柠檬云 API 未接入 |
| `/matching?invoiceId=本地主键` | 发票与子采购的整票关联或数量分配 | 尚未绑定审核获批范围；确认不写 NS |
| `/api/ns/preview`、`/execute`、`/jobs` | 独立的通用回写 API，保留预览、持久锁与未知结果保护 | 尚未由匹配生成业务回写方案；旧正式页面已移除 |
| `/demo?view=...` | 工作台、异常、系统对账、回写等原型 | 模拟数据与操作不代表正式业务能力 |

审核、匹配、人工通知登记、NS 执行是不同状态。当前缺口和建议衔接顺序统一维护在[系统链路](docs/system-chain.md)，各模块规则见[文档索引](docs/README.md)。

## 目录速览

```text
项目根目录/
├── web/                     正式 React 前端：app 装配、modules 业务、shared 公共能力
├── backend/                 FastAPI：core、modules、integrations、两套迁移和测试
├── app/                     原型页面与演示资源；仍被 /demo 按需加载
├── scripts/                 本地启动、检查脚本与待部署的 NS RESTlet
├── tests/                   Node 测试与虚构样例
├── docs/                    当前说明、设计方案、MySQL 资料与历史记录
├── public/                  前端静态资源
└── worker/                  Vinext 原型的 Cloudflare 入口
```

正式构建使用 `web/vite.config.ts`，产物为 `dist/web`；根 `vite.config.ts`、`next.config.ts`、`worker/` 和 `.openai/hosting.json` 属于原型链路。两套配置及旧 Python 导入路径的保留原因见[目录地图](docs/project-structure.md)。

## 本地启动

需要 Python 3.11+ 和 Node.js 22.13+。在项目根目录使用 Windows PowerShell 执行：

```powershell
npm.cmd install
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
```

首次配置时，参照 [.env.example](.env.example) 配置 `.env`；已有配置时补齐缺项即可。在 `.env` 设置 `LOCAL_BROWSER_ACCESS=true`，填写 NS 账户及 M2M 配置、允许访问的记录类型和写入字段。私钥只提供服务器路径，实际写入先保持 `NETSUITE_WRITE_ENABLED=false`。

正式运行统一读取 `BUSINESS_DATABASE_URL` / `BUSINESS_MYSQL_*`，审核、开票跟进、供应商群、采购报关、发票与匹配共用一个 MySQL 连接池。旧 `DATABASE_URL` 不覆盖业务配置；SQLite 仅用于隔离测试和历史数据迁移。MySQL 8.0 连接格式、凭证说明及配置示例见 [Python 后端与 MySQL 配置](docs/python-backend.md)。

```powershell
npm.cmd run build
npm.cmd run db:upgrade
npm.cmd start
```

按配置的 `PORT` / `APP_ORIGIN` 访问后端托管页面，首页进入采购报关联查；未改默认配置时可打开[本地系统](http://localhost:3000)。启用本机访问后，提交查询时自动建立本机会话。按 `Ctrl+C` 停止服务。Linux/macOS 使用 `npm` 和 `.venv/bin/python`，详细步骤见后端文档。

已有业务库按[业务库说明](docs/mysql/README.md)核对基础表与发票扩展，`npm.cmd run db:upgrade` 在同一库升级两条历史迁移链；`db:business:upgrade` 是兼容入口。两者都不能代替空库初始化，不要对已有库重跑历史建表 SQL。旧 SQLite 记录须按[历史数据迁移](docs/python-backend.md#历史应用库合入业务库)在服务停止后复制，切换连接不会自动搬数据。

## 开发启动

Windows 下 Python 自动重载已关闭：当前 Uvicorn 重载会发送控制台 Ctrl+C，可能使 npm/Vite 一起退出。修改后端代码后手动重启；前端样式和组件仍可热更新。联动启动中一端异常退出会报告服务名和退出码，另一端继续运行；主动 Ctrl+C 才同时停止两端。

开发时运行 `npm.cmd run dev`，同时启动前端与 Python 后端。启动器和 Vite 统一读取根目录配置，优先级为进程环境变量 > `.env.local` > `.env` > 默认值。`PORT` 是后端端口（未配置时 3333），`WEB_PORT` 是前端端口（未配置时 5173）。例如在已有 `.env.local` 中设置：

```dotenv
PORT=5174
WEB_PORT=5173
```

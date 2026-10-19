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
| 编码约束与分层规则 | [协作规范](AGENTS.md)、[架构方案](docs/history/architecture-plan.md) |
| 界面与前端工程规范 | [设计基准](design.md)、[前端统一规范](docs/frontend-conventions.md) |
| 历次功能、数据补拉和验收记录 | [历史实施记录](docs/history/implementation-notes.md) |

## 当前能力与边界

以下描述代码接入情况；不表示目标环境已完成迁移、NS 脚本部署或真实联调。

| 入口 | 当前实现 | 主要边界 |
| --- | --- | --- |
| `/login` | 单管理员账号密码登录、退出及会话失效跳转 | 账号来自服务器配置；会话保存在单进程内存中 |
| `/sync/ns` | NS 分页读取；子采购和报关可补齐来源并保存 | 没有持久定时同步队列；依赖来源接口及字段配置 |
| `/workbench`（默认首页） | [发票工作台](docs/invoice-workbench.md)：待办处理、任务进度、供应商待收金额与已开票趋势 | 仅汇总已入库数据，口径见页面说明；超期暂不展示 |
| `/pl-reconciliation` | 通过 NS 共用脚本实时查询采购报关依据 | 只读对照，页面查询不自动入库或审核 |
| `/review`（原 `/finance-reconciliation`） | 已同步报关单与关联子采购逐级核对、整单人工审核，冻结子采购行的开票数量、单位与含税金额 | 来源变化后需重新审核 |
| `/tasks`（原 `/invoice-followup`） | 审核通过自动按供应商×采购公司×币种生成任务、审核后自动下载合同并归档到共享盘、供应商群配置、通知版本和人工发送登记 | 收票进度由发票比对通过的分配自动汇总，完成后任务自动结束；已接入企微群发提交与回执，仍需群主确认；默认关闭，启用前须完成定向验收 |
| `/suppliers`、`/suppliers/external-groups` | 供应商档案、七列外部群 Excel 导入预览、确认绑定及后续人工关联 | 群资料来自文件或企微查询；导入文件不代表实时核验，不发送通知 |
| `/sync`、`/sync/lemon`、`/invoices` | 全授权账套后台拉票、持久任务记录、每日计划、Excel 导入及发票查询 | [后台同步说明](docs/lemon-background-sync.md)；全部范围限当前已发现财务服务，计划默认关闭；专业版已接商品明细，默认版明细仍待补齐 |
| `/matching`、`/matching/:invoiceId` | 比对建议审核队列、逐项比对、人工通过 / 驳回 / 取消、人工分配、版本复核与原子替换；通过后自动更新任务收票进度 | 子采购币种待核实时不能通过；不写 NS |

审核、匹配、人工通知登记是不同状态。NS 回写（预览、执行、未知结果保护、`recover` 恢复命令）已移至 `archive/writeback` 分支；主线保留 `ns_previews`、`ns_target_locks`、`ns_audit` 的表和数据，不再有代码读写。当前缺口和建议衔接顺序统一维护在[系统链路](docs/system-chain.md)，各模块规则见[文档索引](docs/README.md)。

## 目录速览

```text
项目根目录/
├── frontend/                React 前端：独立 package.json；src/ 下为 app 路由与装配、modules 业务、shared 公共能力
├── backend/                 FastAPI：core、modules、integrations、迁移和测试
├── netsuite/                需上传到 NS 的 RESTlet 脚本及其 Node 测试
├── scripts/                 本地联动启动（dev.mjs）与 Python 运行器
├── docs/                    当前说明、架构设计、MySQL 资料与历史记录
└── package.json             命令入口，不含依赖；前端命令转到 frontend/
```

正式构建使用 `frontend/vite.config.ts`，产物为 `frontend/dist`，由后端托管。原型（`app/`、`worker/`、`/demo`）已删除。

## 本地启动

需要 Python 3.11+ 和 Node.js 22.13+。在项目根目录使用 Windows PowerShell 执行：

```powershell
npm.cmd run setup
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
```

首次配置时，参照 [.env.example](.env.example) 配置 `.env`；已有配置时补齐缺项即可。设置工作台账号 `ADMIN_USERNAME`（默认 admin）与非空密码 `ADMIN_PASSWORD`，本机及远程访问均需登录；填写 NS 账户及 M2M 配置、允许访问的记录类型和写入字段。私钥只提供服务器路径，实际写入先保持 `NETSUITE_WRITE_ENABLED=false`。

正式运行统一读取 `BUSINESS_DATABASE_URL` / `BUSINESS_MYSQL_*`，审核、开票跟进、供应商群、采购报关、发票与匹配共用一个 MySQL 连接池。旧 `DATABASE_URL` 已不读取；SQLite 仅用于隔离测试和预览。MySQL 8.0 连接格式、凭证说明及配置示例见 [Python 后端与 MySQL 配置](docs/python-backend.md)。

```powershell
npm.cmd run build
npm.cmd run db:upgrade
npm.cmd start
```

按配置的 `PORT` / `APP_ORIGIN` 访问后端托管页面，首页进入发票工作台；未改默认配置时可打开[本地系统](http://localhost:3000)。打开页面后使用配置的工作台账号密码登录，右上角可退出；会话有效期 8 小时，后端重启后需重新登录。按 `Ctrl+C` 停止服务。Linux/macOS 使用 `npm` 和 `.venv/bin/python`，详细步骤见后端文档。

`npm.cmd run db:upgrade` 只执行 `backend/migrations` 新迁移链，支持空库初始化及已有新表升级；无需历史六表。`0005`—`0009` 保存版本、回填既有 v2 记录；缺少可还原证据的历史占用进入待复核。旧库表和数据不删除、不迁移，`db:business:upgrade` 是同一命令的兼容入口。查表与迁移的对应关系见[表与迁移对照](docs/mysql/schema-map.md)，新增迁移后用 `npm.cmd run db:map` 重新生成。

## 开发启动

Windows 下 Python 自动重载已关闭：当前 Uvicorn 重载会发送控制台 Ctrl+C，可能使 npm/Vite 一起退出。修改后端代码后手动重启；前端样式和组件仍可热更新。联动启动中一端异常退出会报告服务名和退出码，另一端继续运行；主动 Ctrl+C 才同时停止两端。

开发时运行 `npm.cmd run dev`，同时启动前端与 Python 后端。启动器和 Vite 统一读取根目录配置，优先级为进程环境变量 > `.env` > 默认值；不再加载 `.env.local` 或其他模式环境文件。`PORT` 是后端端口（未配置时 3333），`WEB_PORT` 是前端端口（未配置时 5173）。例如在已有 `.env` 中设置：

```dotenv
PORT=5174
WEB_PORT=5173
```

合同自动归档需先执行 `npm.cmd run db:upgrade` 升级至 `0021_task_contract_jobs`，再重启后端。新审核生成的任务自动进入持久队列；失败原因在开票资料中展示，可点击“保存到共享盘”重试。升级前已有任务不批量补下载，可在原任务页手动保存。Windows 直接运行必须将 `.env` 的 `NETSUITE_SUBPO_ARCHIVE_ROOT` 设置为实际可写的绝对目录或 UNC 路径；`/mnt/invoice-contracts` 仅适用于已挂载共享盘的 Linux 环境。

# Python 后端目录说明

真实入口是 `app.py:create_app`，启动命令保持 `python -m backend`。应用工厂只装配依赖、注册路由与管理生命周期。

全仓配置、正式前端与原型的区别见[目录与架构地图](../docs/project-structure.md)；专题和模块文档见[文档索引](../docs/README.md)。

整体调用链、统一数据库及待衔接部分见[系统整体链路与实现关系](../docs/system-chain.md)。以下按 2026-09-24 当前工作区整理，代码已接入不代表真实环境已经迁移或验收。

```text
backend/
├── core/                    配置、连接、元数据、错误、身份依赖、HTTP中间件、静态文件
├── modules/
│   ├── identity/            登录与会话
│   ├── source/              新：NS 来源读取与保存到新表（分层目录），采购报关联查
│   ├── business/            旧：旧表来源保存与读取，第 4e 步删除
│   ├── sync/                连接、M2M验证、分页拉取与调用业务保存
│   ├── invoice/             Excel发票导入、去重、冲突检查与查询
│   ├── matching/            候选比对、整票关联与数量分配
│   ├── reconciliation/      财务审核、开票任务、合同归档与人工通知登记
│   └── audit/               事务内审核审计；保留的历史回写表定义
├── integrations/            NS认证、HTTP与合同来源适配、共享盘归档
├── migrations/              应用表迁移：审核、开票任务及其资料（含历史回写表）
├── legacy_migrations/       旧迁移链（app、business）及旧应用表首次建表；第 4 步删除
└── tests/                   API、状态、数据库及架构依赖检查
```

模块只为实际职责建层。invoice、matching、reconciliation 已注册正式接口；exception、dashboard 尚无正式后端模块。当前匹配仍直接使用发票与子采购来源，尚未接入审核获批范围；开票任务尚未关联实际收票。NS 回写（预览、执行、未知结果保护、`recover` 恢复命令）已移至 `archive/writeback` 分支；主线保留 `ns_previews`、`ns_target_locks`、`ns_audit` 的表和数据，不再有代码读写。供应商通知已有本地草稿与人工发送登记，自动发送未接入。

正式运行统一读取 `BUSINESS_DATABASE_URL` / `BUSINESS_MYSQL_*`，所有模块复用一个 MySQL 连接池。`npm.cmd run db:upgrade` 在同一库协调两条历史迁移链及各自版本表，`db:business:upgrade` 是兼容入口。SQLite 和显式引擎注入仅供隔离测试、预览与历史迁移。共用连接池不等于所有调用自动共用事务：原有审核/审计/任务、匹配/占用的事务边界保留。业务增量迁移依赖已有基础表，不是空库初始化入口。

旧导入兼容入口 `config.py`、`netsuite.py`、`workflow.py`、`auth.py` 已删除，代码直接引用 `core`、`modules`、`integrations`。`database.py` 仍是 Alembic 和应用表导入工具使用的元数据登记入口，在架构方案第 3 步数据库收口时并入 `core`。

数据库迁移继续使用 `manage.py`，正常启动仅检查迁移版本，不清除任务。配置和部署见[后端配置说明](../docs/python-backend.md)，架构见[架构设计 v2](../docs/architecture/README.md)。

运行 `npm.cmd run check` 完成当前格式、类型、依赖、lint、构建与测试检查。真实MySQL并发和真实NS联调需要单独环境，不由本地通过的检查替代。

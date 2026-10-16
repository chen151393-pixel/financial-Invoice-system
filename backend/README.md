# Python 后端目录说明

入口 `app.py:create_app` 只装配依赖、登记事件订阅与生命周期，启动命令 `python -m backend`。

| 目录 | 职责 |
| --- | --- |
| `core/` | 配置、连接、事件总线、命名锁、错误、身份依赖与静态托管 |
| `modules/identity` | 会话与认证身份 |
| `modules/source`、`modules/sync` | NS 来源读取、保存、分页同步；PL 实时查询 |
| `modules/review` | 财务审核、冻结开票依据和币种证据 |
| `modules/task` | 后继任务、合同、通知、供应商群、差异结束 |
| `modules/invoice` | Excel 导入、不可变发票版本、稳定逻辑行 |
| `modules/matching` | 建议、分配、换算、复核、占用与有效收票台账 |
| `integrations/` | NS、企微、共享盘等外部适配 |
| `migrations/` | 唯一迁移链 `0001`—`0009`，版本表 `schema_version` |
| `tests/` | 规则、API、事务、迁移及 MySQL 并发验证 |

跨模块只经 `public.py` 读取，通过同步事件写入。订阅全部登记在 `app.py:create_events`；审核事件先生成任务，再由 matching 重算绝对合计。相关写操作先取得业务库级账本锁，再按来源、依据、任务、任务行、发票、分配顺序加行锁。外部调用不放在数据库事务内。

4e 已删除旧 business、reconciliation、audit 实现、旧迁移链和过渡导入；旧表和数据仍留在数据库，代码不负责删除。PL 前端仍可用，归属 source。NS 回写仍在 `archive/writeback` 分支，主线不写 NS。

统一使用 `BUSINESS_DATABASE_URL` / `BUSINESS_MYSQL_*`；`create_app(engine=...)` 仅供隔离测试/预览注入。`npm.cmd run db:upgrade` 支持空库及已有新表升级，启动只核验版本。`python -m backend.manage rebuild-ledger` 从持久台账重新发布合计，不自动恢复待复核占用。

部署见[后端配置](../docs/python-backend.md)，设计见[架构](../docs/architecture/README.md)，业务流见[系统链路](../docs/system-chain.md)。检查入口 `npm.cmd run check`；MySQL 测试设置 `BUSINESS_MIGRATION_TEST_SERVER_URL`，仅在随机新建隔离库运行。

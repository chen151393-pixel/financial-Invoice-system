# Python 后端目录说明

真实入口是 `app.py:create_app`，启动命令保持 `python -m backend`。应用工厂只装配依赖、注册路由与管理生命周期。

```text
backend/
├── core/                    配置、连接、元数据、错误、身份依赖、HTTP中间件、静态文件
├── modules/
│   ├── identity/            登录与会话
│   ├── business/            NS业务记录查询
│   ├── sync/                连接配置与M2M验证
│   ├── writeback/           预览、确认、执行、DAO、Mapper、DTO、VO
│   └── audit/               事务内审计
├── integrations/netsuite/   认证签名与HTTP适配
├── migrations/              既有Alembic历史，表结构未变
└── tests/                   API、状态、数据库及架构依赖检查
```

模块只为现有职责建层；invoice、matching、reconciliation等真实业务仍按架构方案后续开发，没有为它们生成空目录。

`config.py`、`database.py`、`netsuite.py`、`workflow.py`与`auth.py`保留旧导入适配，没有第二套业务实现。现有测试、迁移与旧调用方式仍使用这些路径；待调用方和迁移环境统一切换、兼容测试通过后可移除。新代码直接引用core、modules与integrations。

数据库迁移继续使用 `manage.py`，正常启动仅检查迁移版本，不清除任务。配置和部署见[后端配置说明](../docs/python-backend.md)，架构规划见[架构方案](../docs/architecture-plan.md)。

运行 `npm.cmd run check` 完成当前格式、类型、依赖、lint、构建与测试检查。真实MySQL并发和真实NS联调需要单独环境，不由本地通过的检查替代。

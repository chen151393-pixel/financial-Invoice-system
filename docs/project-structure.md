# 项目目录与架构地图

2026-10-15 完成 4d A—D 补强及 4e 代码切换；部署和真实外部联调单独验收。架构与分层标准以[架构设计 v2](architecture/README.md)为准。

| 目录 | 实际用途 |
| --- | --- |
| `frontend/src/app` | React Router、导航、工作区装配 |
| `frontend/src/modules` | identity、source、sync、review、task、invoice、matching |
| `frontend/src/shared` | HTTP、布局、按钮、分页、设计变量 |
| `backend/app.py` | FastAPI 路由与同步事件装配 |
| `backend/core` | 公共配置、连接、锁、事件、认证依赖、中间件 |
| `backend/modules` | 与前端同名的业务模块，按 controller/service/dao/entity/dto/vo 分层 |
| `backend/integrations` | NS、企微、合同共享盘等外部适配 |
| `backend/migrations` | 新表唯一 Alembic 链，`schema_version` |
| `netsuite` | NS 侧脚本及其测试，不是第二套本地后端 |
| `scripts` | 开发启动、Python 运行器 |
| `docs` | 当前架构、配置、专题与历史记录 |

正式前端是 React + TypeScript + Vite，构建到 `frontend/dist`，FastAPI 提供页面和 `/api/*`。开发入口 `npm.cmd run dev`，构建运行入口 `npm.cmd run build`、`npm.cmd start`。

后端统一使用业务 MySQL，测试可显式注入 SQLite。新库运行 `npm.cmd run db:upgrade`；已有新库执行同一命令向前升级。旧 `DATABASE_URL`、旧迁移链、双引擎过渡参数和旧业务模块已移除；数据库中的旧表不自动删除或迁移。

页面、接口及事件顺序见[系统链路](system-chain.md)，配置见[Python 后端](python-backend.md)，各模块入口见[文档索引](README.md)。open2 定时拉票、持久同步调度、企微自动通知、角色权限和 NS 回写不属于本次切换。

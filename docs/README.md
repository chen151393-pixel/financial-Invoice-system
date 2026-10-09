# 文档索引

目标架构与开发规则以[架构设计 v2](architecture/README.md)为准（分步实施中）；现状先读[项目目录与架构地图](project-structure.md)了解文件放在哪里，再读[系统链路](system-chain.md)了解页面、服务、数据和业务缺口。本文只维护导航，模块规则不在此复制。

## 当前实现与开发规范

| 文档 | 用途 |
| --- | --- |
| [架构设计 v2](architecture/README.md) | 目标模块、数据库收口、删除清单、实施顺序 |
| [后端规则](architecture/backend-rules.md)、[前端规则](architecture/frontend-rules.md) | 分层目录、模块解耦、公共能力复用、文件大小 |
| [项目 README](../README.md) | 当前能力、安装、启动与检查命令 |
| [目录与架构地图](project-structure.md) | 实际目录、模块归属、双库边界、兼容入口保留原因 |
| [文件忽略与清理清单](ignored-files.md) | 无需提交的产物、本地数据保留边界与源码保留依据 |
| [系统整体链路与实现关系](system-chain.md) | 页面 → 接口 → Service → 表，当前缺口与衔接顺序 |
| [后端目录说明](../backend/README.md) | Python 组织和兼容导入 |
| [Python 后端配置](python-backend.md) | 环境变量、认证、HTTPS、数据库和任务恢复 |
| [Docker 部署](docker-deploy.md) | Linux ECS 上的镜像构建、数据库迁移和 SSH 隧道访问 |
| [AI 协作规范](../AGENTS.md) | 开发流程、分层边界、清理与验收要求 |
| [设计基准](../design.md)、[前端统一规范](frontend-conventions.md) | 视觉交互与前端工程约定 |

## 业务模块

| 模块 | 后端文档 | 前端文档 |
| --- | --- | --- |
| 身份 | [identity](../backend/modules/identity/README.md) | [会话 API](../web/modules/identity/README.md) |
| NS 来源 | [business](../backend/modules/business/README.md) | [旧入口移除说明](../web/modules/business/README.md) |
| 同步 | [sync](../backend/modules/sync/README.md) | [同步工作区](../web/modules/sync/README.md) |
| 发票 | [invoice](../backend/modules/invoice/README.md) | [导入与列表](../web/modules/invoice/README.md) |
| 匹配 | [matching](../backend/modules/matching/README.md) | [匹配工作区](../web/modules/matching/README.md) |
| 财务审核与开票任务 | [reconciliation](../backend/modules/reconciliation/README.md) | [核对与任务页面](../web/modules/reconciliation/README.md) |
| 通用回写 | [writeback](../backend/modules/writeback/README.md) | [旧入口移除说明](../web/modules/writeback/README.md) |
| 审计 | [audit](../backend/modules/audit/README.md) | 暂无独立正式页面 |

## 集成与数据

| 文档 | 用途与状态 |
| --- | --- |
| [NS 适配器](../backend/integrations/netsuite/README.md) | M2M 与 HTTP 适配层 |
| [PL 共用脚本接入](pl-script-integration.md) | 当前网站与 NS RESTlet 共用查询服务的部署说明 |
| [财务来源读取](finance-source-reader.md) | 报关原始行、Packing、采购关系及同步完整性 |
| [PL 联查](pl-lookup.md)、[字段映射](netsuite-pl-lookup.json) | PL 查询契约、兼容路径与配置依据 |
| [PL 来源保存](pl-storage.md) | 既有本地保存用例与边界 |
| [NS 权限](netsuite-vendor-invoice-permissions.md) | 记录访问权限专题 |
| [MySQL 资料入口](mysql/README.md) | 当前迁移导读与历史基础建表说明 |
| [八张来源表](mysql/eight-table-relations.md) | 母采购、子采购、报关和发票来源关系 |
| [报关关联结果表](mysql/customs-reconciliation-results.md) | 当前独立依据与关联结果表 |
| [发票 Excel 扩展](mysql/invoice-excel-design.md) | 发票来源两表的扩展设计及 SQL 依据 |

SQL 文件位于 `mysql/`，不是统一自动迁移入口。环境升级分别使用 `backend/migrations/` 和 `backend/business_migrations/`；已有库不能重跑历史初始化脚本。

## 设计方案与历史资料

| 文档 | 阅读方式 |
| --- | --- |
| [架构方案](architecture-plan.md) | 分层原则及早期目标；目标目录、worker、接口草案不等于已实现 |
| [审核证据与发票匹配方案](lemon-invoice-matching-plan.md) | 尚待完成的获批范围匹配规则 |
| [完整业务数据库设计](mysql/purchase-customs-invoice-schema-design.md) | 既有字段核实与目标设计，区别已存在表和计划表 |
| [单据存储执行方案](document-storage-execution-plan.md) | 阶段性存储方案；按当前模块实现核对 |
| [PL 关联设计审查](pl-join-design-review.md) | 关联依据的设计评审背景 |
| [早期 Suitelet 方案](ns-suitelet-realtime-plan.md) | 历史设计，当前接入以共用脚本说明为准 |
| [参考项目评审](reference-project-review.md) | 外部项目的参考分析，不是本项目目录或实现 |
| [历史实施记录](history/implementation-notes.md) | 从根 README 移入的功能、数据补拉与验收记录，保留原语境 |
| [原型演示说明](../app/demo/README.md) | 演示交互和虚构数据，不代表正式接口能力 |

新增文档按用途放置：当前实现与专题说明放 `docs/`，业务规则优先更新所属模块 README，数据库资料放 `docs/mysql/`，阶段记录放 `docs/history/`。避免在根 README 持续追加阶段日志或复制另一份架构规范。

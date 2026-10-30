# 文档索引

2026-10-19 更新：柠檬云全账套后台任务及每日计划已实现，NS 定时仍待接入；当前部署与边界见[后台同步说明](lemon-background-sync.md)。下述带日期的验收结论保留历史口径。

2026-10-28 新增[NS 报关单后台同步设计](ns-customs-background-sync-plan.md)：手动补拉、定时计划、逐单失败日志与恢复规则，当前为设计方案，尚未实施。

目标架构与开发规则以[架构设计 v2](architecture/README.md)为准（分步实施中）；现状先读[项目目录与架构地图](project-structure.md)了解文件放在哪里，再读[系统链路](system-chain.md)了解页面、服务、数据和业务缺口。本文只维护导航，模块规则不在此复制。

2026-10-15：当前工作区已实现[数据库设计](architecture/database.md)第 10 节的 A—D 补强，迁移链至 `0015`（`0010`—`0015` 为各模块中文备注迁移）；open2 与定时同步待接入，目标库部署状态须另行核对。现有表和逐字段中文解释见[当前表设计与字段字典](mysql/current-data-dictionary.md)。匹配依据是审核冻结的子采购行，旧“按报关行开票”章节仅作历史。

## 当前实现与开发规范

| 文档 | 用途 |
| --- | --- |
| [架构设计 v2](architecture/README.md) | 目标模块、数据库收口、删除清单、实施顺序 |
| [数据库设计](architecture/database.md) | 初版 24 张表与已追加的两张版本表、币种和状态规则、补强顺序及验收 |
| [表与迁移对照](mysql/schema-map.md) | 自动生成：按模块列出全部表的中文说明、新建与修改迁移、字典链接，以及每个迁移涉及的表；`npm.cmd run db:map` 更新 |
| [当前表设计与字段字典](mysql/current-data-dictionary.md) | 当前 26 张业务表、422 个字段的中文含义、类型、可空性、默认值、关联与实现边界 |
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
| 身份 | [identity](../backend/modules/identity/README.md) | [会话 API](../frontend/src/modules/identity/README.md) |
| NS 来源 | [source](../backend/modules/source/README.md) | [source 前端](../frontend/src/modules/source/README.md) |
| 同步 | [sync](../backend/modules/sync/README.md) | [同步工作区](../frontend/src/modules/sync/README.md) |
| 发票 | [invoice](../backend/modules/invoice/README.md) | [导入与列表](../frontend/src/modules/invoice/README.md) |
| 匹配 | [matching](../backend/modules/matching/README.md) | [匹配工作区](../frontend/src/modules/matching/README.md) |
| 财务审核 | [review](../backend/modules/review/README.md) | [财务核对](../frontend/src/modules/review/README.md) |
| 开票任务 | [task](../backend/modules/task/README.md) | [开票跟进](../frontend/src/modules/task/README.md) |

## 集成与数据

| 文档 | 用途与状态 |
| --- | --- |
| [NS 适配器](../backend/integrations/netsuite/README.md) | M2M 与 HTTP 适配层 |
| [供应商账单只读查询](ns-vendor-bill-query.md) | 版本 3 按母采购内部 ID 批量查询的后端接口与样本核对工具；NS 部署及联调待完成 |
| [PL 共用脚本接入](pl-script-integration.md)、[最新部署说明](../outputs/pl-lookup-example/PL联查最新部署说明.md) | 共用查询服务累计部署清单，含采购行真实报关单号补齐 |
| [财务来源读取](finance-source-reader.md) | 报关原始行、Packing、采购关系及同步完整性 |
| [字段映射](netsuite-pl-lookup.json) | NS 来源读取的字段配置依据 |
| [PL 来源保存](pl-storage.md) | 既有本地保存用例与边界 |
| [NS 权限](netsuite-vendor-invoice-permissions.md) | 记录访问权限专题 |
| [NS 回写部署与验证](ns-writeback-prepare.md) | 已实现整票审核入队、候选查询、方案确认、回写预览与写入；写入脚本待 NS 部署和首笔验收 |
| [NS 供应商账单回写方案](ns-vendor-bill-writeback-plan.md)、[按母单查询账单](ns-vendor-bill-query-api.md) | 后续写入方案与第 0 期统计；只读查询 RESTlet 已部署（线上修订号须部署时核实） |
| [MySQL 资料入口](mysql/README.md) | 当前迁移导读与历史基础建表说明 |
| [八张来源表](mysql/eight-table-relations.md) | 母采购、子采购、报关和发票来源关系 |
| [报关关联结果表](mysql/customs-reconciliation-results.md) | 当前独立依据与关联结果表 |
| [发票 Excel 扩展](mysql/invoice-excel-design.md) | 发票来源两表的扩展设计及 SQL 依据 |

SQL 文件位于 `mysql/`，不是统一自动迁移入口。4e 后仅使用 `backend/migrations/`，由 `db:upgrade` 初始化或向前升级；旧双链已退出代码。已有库不能重跑历史初始化脚本或因方案修订删除 v2 台账。

## 设计方案与历史资料

| 文档 | 阅读方式 |
| --- | --- |
| [架构方案](history/architecture-plan.md) | 分层原则及早期目标；目标目录、worker、接口草案不等于已实现 |
| [发票与已审核子采购行匹配方案](lemon-invoice-matching-plan.md) | 第 0 节为当前修订规则，其余明确标记为历史；版本与换算补强待实施 |
| [柠檬云进项发票接入与运维](lemon-invoice-sync-plan.md) | 已实现正式用户 Token、账套选择、手动拉票、版本保存；部署步骤与明细/正式联调边界 |
| [11 月试用上线执行方案](launch-plan-2026-11.md) | 2026-10 会议需求对照现状、改动关联点、待确认问题与 P0/P1/P2 任务排期（待评审） |
| [柠檬云免费版账套接入方案](lemon-free-edition-plan.md) | 免费版只读核实；open2 拉票修正、两版账套合并、购买方取账套名称已实施；免费版商品明细待调研 |
| [柠檬云后台拉票与每日计划](lemon-background-sync.md) | 全部授权账套队列、持久任务、日期分片、每日回扫、失败重试和迁移部署 |
| [企业微信供应商开票通知接入方案](wecom-supplier-notification-plan.md) | 第一阶段已接入：合同与通知提交、群主确认、目标群回执、幂等与异常恢复；真实定向验收待完成 |
| [完整业务数据库设计](mysql/purchase-customs-invoice-schema-design.md) | 既有字段核实与目标设计，区别已存在表和计划表 |
| [单据存储执行方案](history/document-storage-execution-plan.md) | 阶段性存储方案；按当前模块实现核对 |
| [PL 关联设计审查](history/pl-join-design-review.md) | 关联依据的设计评审背景 |
| [早期 Suitelet 方案](history/ns-suitelet-realtime-plan.md) | 历史设计，当前接入以共用脚本说明为准 |
| [参考项目评审](history/reference-project-review.md) | 外部项目的参考分析，不是本项目目录或实现 |
| [历史实施记录](history/implementation-notes.md) | 从根 README 移入的功能、数据补拉与验收记录，保留原语境 |

新增文档按用途放置：当前实现与专题说明放 `docs/`，业务规则优先更新所属模块 README，数据库资料放 `docs/mysql/`，阶段记录放 `docs/history/`。避免在根 README 持续追加阶段日志或复制另一份架构规范。

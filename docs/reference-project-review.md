# GitHub 与 Linux.do 相似项目审查

审查日期：2026-09-13。

围绕本项目的“NS 拉取 → 校对匹配 → 生成预览 → 人工确认 → M2M 写回”检索。阅读了项目说明、仓库元数据，并抽查认证、数据库、匹配和写入代码；没有安装运行第三方项目，也没有用真实 NS 凭证测试。以下风险是静态代码审查结论，不代表已复现生产事故。

建议保持 React + TypeScript + Vite、Python + FastAPI、MySQL 8.0 路线，按模块吸收设计。当前项目已有不可变预览、持久目标锁、身份隔离和结果未知时停止重试等行为，后续借鉴不能削弱这些约束。模块落点沿用[现有架构方案](architecture-plan.md)。

## 1. 优先参考项目

| 项目 | 相似之处 | 适合借鉴 | 适配成本与结论 |
| --- | --- | --- | --- |
| [invoice-vNext](https://github.com/gruntemannen/invoice-vNext) | 发票审核、NS M2M、供应商账单写入、写入日志 | NS 字段映射、环境区分、写入前预览和执行记录 | 业务接近；TypeScript + AWS 架构与本项目差异大，参考业务设计后用 Python 实现 |
| [FastAPI Best Architecture（FBA）](https://github.com/fastapi-practices/fastapi-best-architecture) | FastAPI、SQLAlchemy、MySQL、后台身份管理 | API / Service / 数据访问分层、登录日志、数据库资源管理 | 后端结构最值得参考；其异步 ORM、Redis 等组件应按需选择 |
| [InvoiceFlow](https://github.com/StephaneWamba/InvoiceFlow) | 采购订单、发票、送货单三方匹配 | 明细对比、差异类别、差异原因与复核界面 | 业务流程有价值；匹配与金额代码有明显限制，不直接作为正式规则引擎 |
| [Payment Reconciliation Dashboard](https://github.com/peelmicro/payment-reconciliation-dashboard) | FastAPI + React + TypeScript + Vite，对账列表与详情 | 候选评分展示、内外部记录对比、异常状态与筛选 | 前端技术接近；面向支付且自称作品展示项目，数据库为 PostgreSQL，适合参考交互和规则组织 |

这些项目分别覆盖部分能力。本次公开检索没有找到能够直接替换本系统、且同时满足 NS M2M、人工校对写回、FastAPI、React 和 MySQL 的完整方案。

## 2. 维护与许可快照

下表的日期是本次查询时默认分支最新提交的日期（UTC），不是所有分支最后推送日期。Star 仅描述社区规模，不作为安全性或生产成熟度的证明。

| 项目 | 审查提交 | 默认分支提交日期 | Star | 许可核验 |
| --- | --- | --- | --- | --- |
| invoice-vNext | [f1093f7](https://github.com/gruntemannen/invoice-vNext/commit/f1093f7f91417c1d41c16f4e3e2f80750b9fa88d) | 2026-08-07 | 0 | 有 MIT LICENSE |
| FBA | [315f8a5](https://github.com/fastapi-practices/fastapi-best-architecture/commit/315f8a55ccfa4e2170c82f8f7db43bff46996133) | 2026-09-07 | 2547 | 有 MIT LICENSE |
| InvoiceFlow | [9065d0b](https://github.com/StephaneWamba/InvoiceFlow/commit/9065d0b4dddaf45a2e6150f7f41c6297a6bf8259) | 2026-01-20 | 0 | README 写 MIT，但本次文件树未找到独立 LICENSE，GitHub 许可元数据为空 |
| Payment Reconciliation Dashboard | [ff78c33](https://github.com/peelmicro/payment-reconciliation-dashboard/commit/ff78c33e40c5fe13f31e0bb54ee7844fdf3e72d9) | 2026-04-21 | 1 | 本次文件树和 README 未找到明确许可证，GitHub 许可元数据为空 |
| jacobsvante/netsuite | [91cb550](https://github.com/jacobsvante/netsuite/commit/91cb5503b892bce8f87e778f8d3e7a2d74d070f1) | 2025-03-06 | 120 | 有 MIT LICENSE；认证不符合本项目的 M2M 路线 |

元数据来源：[invoice-vNext](https://api.github.com/repos/gruntemannen/invoice-vNext)、[FBA](https://api.github.com/repos/fastapi-practices/fastapi-best-architecture)、[InvoiceFlow](https://api.github.com/repos/StephaneWamba/InvoiceFlow)、[Payment Dashboard](https://api.github.com/repos/peelmicro/payment-reconciliation-dashboard)、[Python NetSuite 客户端](https://api.github.com/repos/jacobsvante/netsuite)。复用代码前核对对应版本的许可文件；本次未向本项目引入第三方业务代码。

## 3. 核心代码抽查

### 3.1 invoice-vNext：参考 NS 业务流程，保留本项目的写入保护

其 `netsuite.ts` 实现了 M2M 换取 Token、字段转换和按 external ID 查询/写入，`transactions.ts` 保存请求与执行事件。适合参考供应商、子公司、科目等映射的组织方式，以及 Test / Prod 环境标识。[NS 实现](https://github.com/gruntemannen/invoice-vNext/blob/f1093f7f91417c1d41c16f4e3e2f80750b9fa88d/backend/src/shared/netsuite.ts)、[执行日志](https://github.com/gruntemannen/invoice-vNext/blob/f1093f7f91417c1d41c16f4e3e2f80750b9fa88d/backend/src/shared/transactions.ts)。

发现的高优先级问题：

- **查询失败仍可能继续 PUT。** `upsertNetSuiteRecord()` 第 1966–1996 行只判断 GET 是否成功；非成功响应统一进入 PUT，没有将“记录不存在”与 401、403、429、500 等情况区分。查询失败不能证明记录不存在，这会削弱写入前的重复检查。移植时必须区分明确不存在、明确失败和结果未知。[具体代码](https://github.com/gruntemannen/invoice-vNext/blob/f1093f7f91417c1d41c16f4e3e2f80750b9fa88d/backend/src/shared/netsuite.ts#L1966)。
- **查询到同 external ID 就返回成功。** 第 1971–1985 行没有比对已有记录与待写请求的业务内容。结果核实应同时检查目标身份、关键字段及明细，不能只看 ID 存在。[具体代码](https://github.com/gruntemannen/invoice-vNext/blob/f1093f7f91417c1d41c16f4e3e2f80750b9fa88d/backend/src/shared/netsuite.ts#L1971)。
- **创建执行日志的去重步骤不是原子操作。** 第 160–190 行先检查发票上的任务 ID，再创建随机 ID 的任务，最后更新发票。任务创建的条件针对随机任务键，不是业务 external ID。据此判断，并发请求存在创建多个任务的窗口；本次未进行并发复现。不能用这段逻辑替换本项目已有的持久目标锁。[具体代码](https://github.com/gruntemannen/invoice-vNext/blob/f1093f7f91417c1d41c16f4e3e2f80750b9fa88d/backend/src/shared/transactions.ts#L160)。

其 worker 会将超时等错误交给 SQS 重试；本项目应继续让写入结果不明的任务进入 `unknown` 并等待核实。它还包含自动入账和供应商主数据补写，这些行为超出当前的人工校对写回流程。[worker](https://github.com/gruntemannen/invoice-vNext/blob/f1093f7f91417c1d41c16f4e3e2f80750b9fa88d/backend/src/netsuite-worker.ts#L40)。

### 3.2 FBA：参考分层和公共能力

README 给出 API、Schema、Service、CRUD、Model 的职责对应；数据库代码提供 MySQL / PostgreSQL 驱动选择、连接池和会话管理；认证服务包含密码检查、登录失败处理及登录日志。[分层说明](https://github.com/fastapi-practices/fastapi-best-architecture/blob/315f8a55ccfa4e2170c82f8f7db43bff46996133/README.zh-CN.md)、[数据库实现](https://github.com/fastapi-practices/fastapi-best-architecture/blob/315f8a55ccfa4e2170c82f8f7db43bff46996133/backend/database/db.py)、[认证服务](https://github.com/fastapi-practices/fastapi-best-architecture/blob/315f8a55ccfa4e2170c82f8f7db43bff46996133/backend/app/admin/service/auth_service.py)。

本项目采用已有方案中的 Controller / Service / DAO / Mapper 命名即可，不必为对齐模板再次改名。FBA 使用异步 ORM，本项目目前使用同步 SQLAlchemy Core；适合借鉴事务、连接生命周期和职责划分，不适合逐文件直接替换。其后台登录认证也不能代替 NS 的 M2M 认证模块。

### 3.3 InvoiceFlow：参考差异模型，重新设计匹配规则

其匹配服务支持采购单号、供应商名称和明细描述匹配，差异模型包含数量、价格、缺失项、多余项等分类。[匹配实现](https://github.com/StephaneWamba/InvoiceFlow/blob/9065d0b4dddaf45a2e6150f7f41c6297a6bf8259/backend/src/services/matching.py)、[差异模型](https://github.com/StephaneWamba/InvoiceFlow/blob/9065d0b4dddaf45a2e6150f7f41c6297a6bf8259/backend/src/models/matching.py)。

发现的高优先级问题：

- **采购单号冲突时仍可能按供应商名称匹配。** `_find_matching_invoice()` 第 140–153 行逐张检查发票，当前发票的单号不匹配后仍尝试供应商名称，命中即返回。例如目标 PO100，候选列表第一张属于 PO200 但供应商相同，后面才是 PO100，代码可能先选第一张。应先筛选明确业务关联，冲突不能被名称相似度覆盖。[具体代码](https://github.com/StephaneWamba/InvoiceFlow/blob/9065d0b4dddaf45a2e6150f7f41c6297a6bf8259/backend/src/services/matching.py#L133)。
- **金额计算转成 float，容差也写死。** 第 275–292 行将税额和小计转为浮点，并设置至少 1 个金额单位的容差。应按本项目规范使用 Decimal / DECIMAL，并由明确的币种精度和业务口径决定舍入及容差。[具体代码](https://github.com/StephaneWamba/InvoiceFlow/blob/9065d0b4dddaf45a2e6150f7f41c6297a6bf8259/backend/src/services/matching.py#L273)。

此外，明细匹配使用逐项选择和已使用索引集合，属于一对一匹配；不能直接覆盖本项目可能需要的一票多单、拆分分配或部分开票。[明细匹配代码](https://github.com/StephaneWamba/InvoiceFlow/blob/9065d0b4dddaf45a2e6150f7f41c6297a6bf8259/backend/src/services/matching.py#L594)。

### 3.4 Payment Reconciliation Dashboard：参考对账交互与可解释评分

其规则引擎将币种作为硬性筛选条件，将金额、标识和时间分别评分，并返回评分和匹配类别；界面展示内部与外部记录、差额及对账状态。适合参考“为什么推荐这个候选”的展示方式。[引擎](https://github.com/peelmicro/payment-reconciliation-dashboard/blob/ff78c33e40c5fe13f31e0bb54ee7844fdf3e72d9/apps/api/app/reconciliation/engine.py)、[项目说明](https://github.com/peelmicro/payment-reconciliation-dashboard)。

发现的中优先级问题：**README 与实际规则不一致。** README 写金额差 5% 内加 50 分，日期按天分档；审查版本的代码实际是金额差不超过 50 个最小货币单位加 60 分，时间按 5 分钟、1 小时和 1 天分档。不能照说明中的阈值实现正式对账。[金额规则](https://github.com/peelmicro/payment-reconciliation-dashboard/blob/ff78c33e40c5fe13f31e0bb54ee7844fdf3e72d9/apps/api/app/reconciliation/engine.py#L82)、[时间规则](https://github.com/peelmicro/payment-reconciliation-dashboard/blob/ff78c33e40c5fe13f31e0bb54ee7844fdf3e72d9/apps/api/app/reconciliation/engine.py#L122)。

本项目应由后端返回评分依据、差异和操作许可，前端负责展示。支付记录的卡号、手续费和时间权重不能直接套用于采购发票；评分也不应直接触发 NS 写入。

### 3.5 排除作为 M2M 替代品：jacobsvante/netsuite

这个 Python 客户端覆盖 SOAP、REST 和 RESTlet，但抽查的 REST 认证实际使用 `OAuth1Auth`，需要 consumer key / secret 和 token / token secret。它不提供与当前证书 M2M 配置直接对应的认证实现，所以不建议为了“用了现成 SDK”而替换当前 HTTPX + PyJWT 模块。[认证代码](https://github.com/jacobsvante/netsuite/blob/91cb5503b892bce8f87e778f8d3e7a2d74d070f1/netsuite/rest_api_base.py#L92)。

## 4. Linux.do 上的有效线索

| 帖子 | 核实到的内容 | 对本项目的价值 |
| --- | --- | --- |
| [FastAPI 最佳架构](https://linux.do/t/topic/470425) | 作者介绍 FBA，并链接 GitHub 仓库 | 可沿帖子了解设计背景；具体能力以当前源码为准 |
| [基于 Qwen3VL 的发票识别和结构化提取](https://linux.do/t/topic/1500243) | 作者介绍 Invoice 模型，链接到 [ModelScope 模型页](https://www.modelscope.cn/models/FLYFAI/Invoice)，帖中说明处于测试阶段 | 将来需要从图片提取发票字段时可列入评测；当前直接读取 NS 结构化数据时优先级低 |

本次 Linux.do 公开检索未找到可核验的完整 NS M2M 对账写回系统。OCR 帖子的准确率属于作者或回帖者的经验描述，本次未核验；模型页未返回可读模型卡，因此未确认模型规模、许可证及部署资源要求，不据此推荐生产部署。

## 5. 对当前项目的落地顺序

以下是后续实施建议，本次未执行业务重构。

1. **先完成真实 NS 只读联调。** 核对服务器配置、证书路径、记录类型、角色权限，确认 M2M 换 Token 和记录读取。第三方项目不能代替账户联调。
2. **按现有方案逐步拆分后端。** 参考 FBA 的职责边界，先整理 NS 适配器和 writeback 模块，保留现有 `/api/ns/*` 契约、数据库迁移及写入保护。
3. **实现标准业务数据与字段映射。** 参考 invoice-vNext 的映射组织方式，将原始 NS 记录转换为业务单头和明细；实际写入类型尚需按业务确定，不能直接把第三方的 vendorBill 映射当成公司的配置。
4. **实现后端匹配和异常处理。** 参考 InvoiceFlow 的差异分类与 Payment Dashboard 的结果展示，先处理主体、币种、来源关联等约束，再生成候选和原因。确认时校验可分配数量/金额并持久化占用。
5. **最后接通业务确认写回。** 生成不可变请求快照，确认后执行；保留目标锁与审计。写入响应不明确时核实 NS 结果，不能当普通失败重发。

飞书后续复用同一业务 Service 与域名下的接口。OCR、多角色审批及更复杂的任务调度，在对应需求明确后再补充。

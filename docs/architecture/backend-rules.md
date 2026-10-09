# 后端规则

状态：**已确认（2026-10-09）**。适用于 `backend/` 下的全部代码。总体设计见[架构设计](README.md)。

技术栈固定：Python 3.11 + FastAPI + SQLAlchemy Core + Alembic + MySQL 8。不更换框架，不引入 ORM 模型类。

## 1. 三条基本原则

1. **规则写在所属模块里**。新增或修改业务规则，只改该规则所属模块的代码；不写进 `app.py`、`core/`、`integrations/` 或前端。
2. **不写大文件**。一个文件只负责一个业务对象（一张表、一个资源、一组用例）；超过第 6 节的行数限制就拆分。
3. **模块之间低耦合**。参照 Java 微服务：模块只通过门面（`public.py`）读取彼此的数据，通过事件通知彼此；修改一个模块的内部实现，不需要改其他模块。

## 2. 目录

```text
backend/
├── app.py              只做装配：创建引擎和适配器、构造 Service、注册路由、登记事件订阅、启动调度器
├── __main__.py         启动入口
├── manage.py           运维命令：数据库初始化、升级、导入
├── core/               与业务无关的公共能力（见第 3 节）
├── integrations/       外部系统适配：netsuite/、lemon/、wecom.py、contract_archive.py
├── modules/<module>/   业务模块（见第 4 节）
├── migrations/         主迁移链（之后所有新迁移只写这里）
├── business_migrations/ 业务迁移链，冻结在 0007，只读
└── tests/<module>/     与模块同名的测试目录；core 的测试放 tests/core/
```

依赖方向：`modules` → `core`、`integrations`；`integrations` → `core`；`core` 不依赖任何人。

## 3. 公共能力：优先复用

新增公共代码前，先确认下表中没有可用的实现。公共目录只放**与业务无关、至少两个模块使用**的能力。

| 已有代码 | 用途 | 规则 |
| --- | --- | --- |
| `core/config.py` | 读取配置 `load_settings()` | 新配置项加在这里，不在模块里直接读环境变量 |
| `core/database.py` | 创建引擎 | 第 3 步收口后是唯一的数据库入口 |
| `core/schema.py` | `identifier()`、`document`、`table_options` | 新表的字符串主键、长文本、MySQL 表选项都用它 |
| `core/errors.py` | `ApiError(status, message)` | 所有业务错误都抛它，不自定义异常响应格式 |
| `core/dto.py` | `StrictModel`（禁止多余字段、严格类型） | 所有请求 DTO 继承它 |
| `core/dependencies.py` | `Owner` 当前身份依赖 | 路由取当前身份只用它 |
| `core/middleware.py` | 请求保护、统一错误响应 | 不在路由里自己捕获异常拼响应 |
| `integrations/netsuite/` | NS 认证与请求 | 不在模块里直接发 NS 请求 |
| `integrations/lemon/` | 柠檬云 open2 | 同上 |
| `integrations/wecom.py` | 企微群查询 | 同上 |
| `integrations/contract_archive.py` | 合同共享盘 | 同上 |

计划新增的公共能力（实施时再建，不预建）：

- `core/events.py`：进程内同步事件总线（第 5.2 节）。
- `core/scheduler.py`：定时调用 Service 的运行器（第 9 节）。

## 4. 模块内部结构

参照 Java 分层（controller / service / dao / entity / dto / vo），每层一个目录，**层目录内一个文件对应一个业务对象**：

```text
modules/task/
├── README.md                    职责、拥有的表、门面接口、事件、HTTP 接口、状态说明
├── public.py                    门面：其他模块唯一可导入的文件（含事件契约）
├── controller/
│   ├── task_controller.py
│   ├── document_controller.py
│   └── supplier_group_controller.py
├── service/
│   ├── task_service.py
│   ├── task_line_service.py
│   ├── document_service.py
│   ├── notification_service.py
│   └── supplier_group_service.py
├── dao/                          一张表（或头表 + 行表）一个文件
│   ├── task_dao.py
│   ├── task_line_dao.py
│   ├── document_dao.py
│   ├── notification_dao.py
│   └── supplier_group_dao.py
├── entity/                       一张表一个文件，与 dao 对应
├── dto/                          与 controller 对应
├── vo/                           与 controller 对应
├── mapper/                       按需：行 ↔ VO 的纯转换
└── policy/                       按需：状态机、数量金额规则（纯函数）
```

- 只建用得到的层目录；简单模块可以没有 `mapper/`、`policy/`。
- 同一业务对象在各层的文件名一致：`task_dao.py`、`task_service.py`、`task_controller.py`。看文件名就能找到同一对象的所有代码。
- 现有扁平文件（如 `reconciliation/group_dao.py`、`task_dao.py`）在第 4 步按此结构移动，内容不变。

### 4.1 各层职责

| 层 | 可以做 | 不可以做 |
| --- | --- | --- |
| `controller/` | 声明路由、接收 DTO、取当前身份、调用 Service、返回 VO | 写 SQL、算金额、判断状态、调用外部系统、调用 DAO |
| `dto/` | 必填、类型、长度、格式、范围校验 | 查询数据库 |
| `service/` | 业务用例、事务边界、调用本模块 DAO、调用其他模块门面、发布事件 | 拼 SQL、处理 HTTP 请求对象 |
| `policy/` | 状态机、数量金额规则、可操作判断（`allowed/reason`） | 访问数据库或外部系统 |
| `dao/` | 本模块表的查询、加锁、增删改；参数接收调用方的 `connection` | 提交事务、决定业务状态、调用外部系统、访问其他模块的表 |
| `entity/` | 用 `Table(...)` 显式定义本模块的表 | 定义其他模块的表 |
| `vo/` | 响应结构、金额字符串、`allowed/reason` | 业务计算 |
| `mapper/` | 数据行、业务对象、VO 之间的纯转换 | 查询、校验流程 |
| `public.py` | 暴露只读查询函数、事件契约 | 暴露 DAO、Entity、内部 Service |

## 5. 模块之间

### 5.1 门面调用（只读）

- 只能导入其他模块的 `public.py`，读取依赖方向以[架构设计](README.md)第 3.1 节为准，禁止循环。
- 门面返回普通数据类或字典（相当于微服务的响应 DTO），不返回数据库行对象。
- 门面的签名就是模块之间的契约，修改时同步修改调用方并在 README 中说明。
- 依赖在 `app.py` 中构造并注入 Service，Service 不自行创建其他模块的对象。

### 5.2 事件（写入其他模块的唯一方式）

```python
# review/public.py —— 发布方定义事件契约
@dataclass(frozen=True)
class ReviewApproved:
    account: str
    declaration_id: str
    snapshot_id: str
    revision: int
    purchase_lines: tuple[ApprovedPurchaseLine, ...]

# review/service/review_service.py —— 在自己的事务中发布
with self.engine.begin() as connection:
    review_dao.approve(connection, ...)
    self.events.publish(connection, ReviewApproved(...))

# app.py —— 只在这里登记订阅
events.subscribe(ReviewApproved, task_services.task.on_review_approved)
```

- 订阅方在发布方的事务中同步执行，使用传入的 `connection`；任何一方失败，整个事务回滚。
- 订阅方不能调用外部系统、不能开启新事务。
- 发布方不知道谁在订阅；新增订阅不需要修改发布方。
- 事件名用过去式：`ReviewApproved`、`AllocationChanged`、`SourceChanged`。

### 5.3 检查

`tests/test_architecture.py` 静态检查：只导入 `public.py`、无循环依赖、DAO 只访问本模块表、`core/` 和 `integrations/` 不导入 `modules/`。新增模块或依赖方向时同步更新检查表。

## 6. 文件大小

| 文件 | 上限 |
| --- | --- |
| `dao/*.py` | 200 行 |
| `service/*.py`、`controller/*.py` | 300 行 |
| 其他文件 | 300 行 |
| 单个函数 | 60 行 |

超过上限时按业务对象或用例拆分，不新建 `utils2.py`、`common_service.py`、`helper.py` 之类的杂项文件。

## 7. 事务与外部调用

- 事务只在 Service 中开启：`with engine.begin() as connection:`。DAO 不调用 `commit()`。
- 外部调用（NS、柠檬云、企微、共享盘）不放在数据库事务内。顺序固定：**事务外读取外部数据 → 短事务内重新校验版本并写入**。
- 需要防并发的写操作，在事务内用 `SELECT ... FOR UPDATE` 锁定相关行；按固定顺序加锁：来源 → 审核 → 任务 → 任务行 → 发票 → 分配。
- 写接口带 `requestId` 保证幂等；依赖读取结果的确认操作带读取时返回的 `snapshot`/`revision`，不一致返回 409。

## 8. 数据库

- 一个数据库（业务 MySQL）、一个引擎。每张表只属于一个模块，归属见[架构设计](README.md)第 5.1 节；只有所属模块的 DAO 可以读写。
- 现有表名不变；**新表以模块名开头**：`task_invoice_lines`、`sync_runs`。
- 金额、数量用 `DECIMAL`，Python 中用 `Decimal`，禁止 `float`；接口中以十进制字符串传递。
- 新表在 `entity/` 中显式定义，不用 `autoload_with` 反射；现有反射的表在所属模块重组时改为显式定义。
- 新迁移只写入 `backend/migrations`，文件名 `NNNN_<module>_<说明>.py`；一个迁移只修改一个模块的表；提供 `downgrade`，无法回退时在文件开头写明原因。历史迁移文件不修改、不删除。
- 不删除表或数据来"整理"数据库；停用的表先停止写入，确认无用后再单独迁移删除。

## 9. 定时任务

- `core/scheduler.py` 只负责按配置周期调用 `sync` 模块的 Service，不包含业务逻辑。
- 同一任务同一时间只运行一个实例（数据库锁）。
- 每次运行写入 `sync_runs`（开始、结束、结果、条数、错误）；增量位置写入 `sync_cursors`。
- 页面上的"立即同步"调用同一个 Service。

## 10. 接口

- 路径 `/api/<module>/<资源>`：

  | 模块 | 前缀 |
  | --- | --- |
  | identity | `/api/session`（保持现状） |
  | source | `/api/source` |
  | sync | `/api/sync` |
  | review | `/api/review` |
  | task | `/api/tasks`（供应商群：`/api/tasks/supplier-groups`） |
  | invoice | `/api/invoices` |
  | matching | `/api/matching` |

- 查询用 `GET`，条件复杂时用 `POST /<资源>/query`；动作用 `POST /<资源>/{id}/<动作>`。
- 只返回 VO；金额、数量是十进制字符串；可执行操作返回 `{ allowed, reason }`。
- 列表返回 `{ items, total, page, pageSize }`，分页、筛选、统计都在后端。
- 错误统一为 `{ "error": "中文说明" }`（沿用 `core/middleware.py` 现有格式），需要字段级提示时增加 `fieldErrors`。
- 没有前端或脚本调用的接口不保留。
- 改路径时，旧路径在一个版本内保留并转发到新实现，之后删除。

## 11. 身份

暂不设计登录和角色。沿用现有 `identity` 的单账号与本机会话，路由通过 `Owner` 取得当前身份；数据仍按现有 `owner`/`tenant` 字段存取，不改写历史数据。

## 12. 状态机

- 状态和允许的转换集中定义在所属模块的 `policy/`：

  ```python
  TRANSITIONS = {
      "awaiting_invoice": {"partially_received", "received", "over_invoiced", "superseded"},
      ...
  }
  ```

- 状态只能通过 Service 中的一个函数修改，修改前检查转换表；不在代码中散落写状态字符串。
- 由数据汇总得出的状态（如任务收票进度）不提供手动修改接口。

## 13. 测试与检查

- 测试放 `tests/<module>/`，文件名 `test_<业务对象>_<用例>.py`。
- 金额、状态转换、并发、迁移相关的改动必须有针对性测试。
- 锁、并发、占用测试用 `@pytest.mark.mysql` 在 MySQL 8 上运行；没有 MySQL 时显示为跳过，不能算作通过。
- 提交前运行：

  ```bash
  python -m ruff check backend
  python -m ruff format --check backend
  python -m pytest backend/tests
  ```

## 14. 文档与注释

- 模块 README：职责、拥有的表、门面接口、发布和订阅的事件、HTTP 接口、状态说明。接口或表结构变化时在同一个提交内更新。
- 注释用中文，解释业务原因和边界，不逐行翻译代码。

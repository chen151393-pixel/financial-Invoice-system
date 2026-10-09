# 前端规则

状态：**已确认（2026-10-09）**。适用于 `frontend/` 下的全部代码。总体设计见[架构设计](README.md)；视觉基准仍以根目录 [design.md](../../design.md) 为准。

技术栈固定：React 19 + TypeScript + Vite + `react-router`。样式使用普通 CSS 和设计变量，不使用 Tailwind，不引入全局状态库。

## 1. 三条基本原则

1. **前端不写业务规则**。金额、数量、收票进度、能否操作都由后端计算；新增规则写在后端对应模块。
2. **不写大文件**。一个文件只负责一个页面、一个组件或一个资源的接口；超过第 7 节的行数限制就拆分。
3. **模块之间不互相引用**。模块只依赖 `shared/` 和 `app/paths.ts`；需要其他模块的数据时，由后端在本模块接口中返回。

## 2. 目录

```text
frontend/
├── package.json、vite.config.ts、tsconfig.json、eslint.config.mjs、index.html
├── public/
└── src/
    ├── main.tsx            挂载应用、引入全局样式，不写其他代码
    ├── app/
    │   ├── router.tsx      唯一的路由表：汇总各模块 routes.tsx
    │   ├── navigation.ts   菜单（只列正式页面）
    │   └── paths.ts        全部页面路径常量；跨模块跳转只用这里
    ├── modules/<module>/   业务模块（见第 4 节）
    └── shared/             公共能力（见第 3 节）
```

依赖方向：`app` → `modules` → `shared`。`shared` 不导入 `modules` 和 `app`。

## 3. 公共能力：优先复用

新增公共代码前，先确认下表中没有可用的实现。只有**至少两个模块实际使用**时才提取到 `shared/`，不预建空组件。

| 已有代码 | 用途 |
| --- | --- |
| `shared/api/http.ts` | 唯一的请求函数 `http()` 和 `HttpError`；不另建请求客户端 |
| `shared/components/AppFrame.tsx` | 页面外壳，所有页面都用它 |
| `shared/components/Sidebar.tsx` | 侧栏，菜单由 `app/navigation.ts` 传入 |
| `shared/components/Button.tsx` | 按钮，不在模块里另写按钮样式 |
| `shared/components/Pagination.tsx` | 分页 |
| `shared/styles/tokens.css` | 颜色、字体、间距、圆角变量 |
| `shared/styles/base.css` | 唯一的基础样式重置 |

计划提取（出现第二处使用时再建）：`PageHeader`、`DataTable`、`StatusBadge`、`Modal`、`LoadingState`、`EmptyState`、`ErrorState`、`AmountText`、`useRequest`（请求状态与取消）、`useQueryParams`（URL 查询参数）。

## 4. 模块内部结构

模块名与后端一致：`identity`、`source`、`sync`、`review`、`task`、`invoice`、`matching`。结构与后端对应，一个文件对应一个业务对象：

```text
modules/task/
├── README.md                 页面、调用的接口、主要组件
├── routes.tsx                本模块路由，导出给 app/router.tsx
├── api/                      一个后端资源一个文件，与后端 controller 对应
│   ├── task-api.ts
│   ├── document-api.ts
│   └── supplier-group-api.ts
├── types/                    与后端 vo 对应
│   ├── task.ts
│   └── supplier-group.ts
├── pages/                    一个路由一个页面
│   ├── TaskListPage.tsx
│   ├── TaskDetailPage.tsx
│   └── SupplierGroupsPage.tsx
├── components/               只在本模块使用的组件，组件和样式同名放在一起
│   ├── TaskNotification.tsx
│   └── task-notification.css
└── hooks/                    只在本模块使用的 Hook
    └── useTaskList.ts
```

- 只建用得到的目录。
- 现有扁平文件（如 `reconciliation/api.ts`、`group-api.ts`、`task-types.ts`）在第 4 步按此结构移动。

### 4.1 各类文件职责

| 文件 | 可以做 | 不可以做 |
| --- | --- | --- |
| `pages/*Page.tsx` | 读取路由和 URL 参数、调用 Hook、组合组件、处理加载/空/错误状态 | 直接调用 `http()` 或 `fetch`、计算业务数据 |
| `components/*` | 根据 props 展示、收集输入、触发回调 | 调用接口、判断业务是否允许 |
| `hooks/*` | 调用 `api/`、管理请求状态、取消过期请求 | 计算金额、判断业务是否允许 |
| `api/*` | 调用 `shared/api/http.ts`，声明请求和返回类型 | 转换或计算业务数据 |
| `types/*` | 与后端 VO 一致的类型；状态值到中文的映射表 | 业务规则 |

## 5. 路由与导航

- 使用 `react-router`。各模块在 `routes.tsx` 中导出路由，`app/router.tsx` 汇总；其他地方不能用 `location.pathname` 判断显示哪个页面。
- 路径常量集中在 `app/paths.ts`，跨模块跳转只用这些常量。
- 页面路径：

  | 模块 | 路径 |
  | --- | --- |
  | source | `/source/pl`（采购报关联查） |
  | review | `/review`（财务核对） |
  | task | `/tasks`、`/tasks/:id`、`/tasks/supplier-groups` |
  | invoice | `/invoices`、`/invoices/import` |
  | matching | `/matching`、`/matching/:invoiceId` |
  | sync | `/sync` |

- 首页跳转到 `/review`。
- 旧路径（`/pl-reconciliation`、`/finance-reconciliation`、`/invoice-followup`、`/invoice-followup/supplier-groups`、`/sync/ns`、`/sync/lemon`）在一个版本内重定向到新路径，之后删除。
- 菜单只列正式页面；不保留演示页、示例页、模拟数据。

## 6. 数据请求与前后端边界

- 所有请求经过 `shared/api/http.ts`；接口函数只写在模块的 `api/` 中，函数名以动词开头：`listTasks`、`getTask`、`saveSupplierGroup`。
- 类型字段与后端 VO 一致（camelCase）；金额、数量是 `string`，不转成 `number`。
- 筛选、分页、排序放在 URL 查询参数中，刷新后保持。
- 快速切换条件时，取消或忽略旧请求的结果。
- 按钮是否可用、为什么不可用，只根据后端返回的 `{ allowed, reason }` 显示。
- 表单校验以后端返回的错误为准；前端即时提示不能代替后端校验。
- 状态值翻译为中文的映射表只在模块 `types/` 中写一份，不在多个组件中重复。

## 7. 文件大小

| 文件 | 上限 |
| --- | --- |
| `pages/*.tsx` | 250 行 |
| `components/*.tsx` | 200 行 |
| `api/*.ts`、`hooks/*.ts` | 150 行 |
| 单个 `.css` 文件 | 250 行 |

超过上限时拆分组件或 Hook。一个文件只导出一个主要组件。

## 8. 样式

- 颜色、字号、间距、圆角只用 `tokens.css` 中的变量。
- 模块样式类名以模块名开头（`.task-list`、`.matching-candidate`），不修改全局 `button`、`table`、`input`。
- 每个数据页面都处理加载中、空数据、失败、正常四种状态；状态不能只靠颜色区分。
- 界面文字全部为中文。

## 9. 检查

提交前在 `frontend/` 下运行：

```bash
npm run lint
npm run typecheck
npm run build
npm run check:architecture
```

`check:architecture`（由现有 `scripts/check-web-architecture.mjs` 改造）检查：模块之间不互相导入、`shared` 不导入 `modules`、页面和组件不直接调用 `http()`。

页面布局或交互变化时，在桌面和较窄窗口下检查受影响页面的四种状态和键盘操作。

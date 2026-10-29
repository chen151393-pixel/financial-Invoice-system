# 飞书登录、部门同步与权限方案

状态：**第 1 期已实现，第 2—4 期待实施（2026-10-27 起草，2026-10-28 更新）**。已确认的决定：

| 事项     | 决定                                                                                       |
| -------- | ------------------------------------------------------------------------------------------ |
| 登录     | 日常用飞书授权登录；保留现有 admin 账号密码作为应急入口，可在配置中关闭                    |
| 同步范围 | 管理员指定部门，同步这些部门及其下级的成员；不在范围内的人不能登录                         |
| 角色分配 | 部门对应默认角色，管理员可给个人追加或改角色；人员与部门以飞书为准，系统不维护本地用户档案 |
| 数据范围 | 首期不按人限制数据，只按功能分权限；“采购员只看自己负责的供应商”放到以后                   |

**第 1 期已实现（2026-10-28）**：飞书登录、部门与成员同步、同步范围、部门与个人角色、权限管理页、应急登录开关。用模拟飞书完成了自动化测试与本地浏览器验证，尚未与真实飞书联调。与方案的差异：会话仍在 API 进程内存中（每次请求按数据库校验在职与角色），会话落库放到后续，以免改动全部依赖内存会话的现有测试。实现说明见 [identity 模块](../backend/modules/identity/README.md)。第 2—4 期尚未实施。

飞书接口地址与字段已于 2026-10-28 对照飞书开放平台文档核对。

2026-10-28 同步权限补修：柠檬云绑定、账套和同步任务已接入实时系统管理员角色校验，支持飞书管理员，并复用现有系统同步配置；细粒度权限码仍属第 2 期。手动任务保留实际发起人，定时调度仍以系统应急身份消费。详见 [sync 模块](../backend/modules/sync/README.md#系统管理员访问柠檬云同步2026-10-28)。

## 1. 改造前现状

- `identity` 只有一个管理员账号（`ADMIN_USERNAME` / `ADMIN_PASSWORD`），会话在进程内存里，重启就要重新登录，只能单进程部署。
- 所有登录用户的操作者都是 `user:admin`，审核人、上传人无法区分。
- 67 个写接口都只检查“是否已登录”，没有区分谁能做什么。
- 柠檬云账号绑定、批量拉取等 5 处服务在代码里写死只允许 `user:admin`（`sync/service/lemon_*`、`invoice_account_service.py`），后台柠檬云任务也以 `user:admin` 身份运行。
- `SERVICE_API_KEY` 对应的 `service:feishu` 服务身份是只读接口身份，与本方案的飞书登录无关，保留不变。

## 2. 飞书侧准备（需要飞书管理员操作）

1. 在飞书开放平台创建**企业自建应用**，开启“网页应用”能力。
2. 在“安全设置 → 重定向 URL”中添加 `https://invoice.yesion.net/api/session/feishu/callback`；本地开发另加 `http://localhost:5173/api/session/feishu/callback`。
3. 申请权限：
   - 获取用户基本信息、获取用户 user ID（登录用）；
   - 通讯录：获取部门基础信息、获取部门组织架构信息、获取用户基本信息、以部门维度获取成员（部门同步用）。
   - 不申请手机号、邮箱等敏感字段，系统不保存。
4. 把“通讯录权限范围”设置为至少包含要同步的部门。
5. 发布应用版本，经企业管理员审核通过。
6. 把 App ID、App Secret 填入服务器 `.env`（`FEISHU_APP_ID`、`FEISHU_APP_SECRET`），由你本人填写，不写进代码或文档。另配置 `FEISHU_TENANT_KEY`，用于拒绝其他企业的飞书账号。

## 3. 登录流程

```text
登录页 /login 点击“使用飞书登录”
  → POST /api/session/feishu/start { returnTo }        后端生成一次性 state（10 分钟有效），
                                                       与 returnTo 一起存库，返回飞书授权地址
  → 浏览器跳转飞书授权页 accounts.feishu.cn/open-apis/authen/v1/authorize
  → 飞书回调 GET /api/session/feishu/callback?code&state
      后端：校验 state（一次性、未过期、与浏览器的登录流程 Cookie 一致）
            用 code 换 user_access_token（/open-apis/authen/v2/oauth/token）
            读取用户信息（/open-apis/authen/v1/user_info）
            校验 tenant_key = FEISHU_TENANT_KEY
            查本地同步来的人员：必须存在、在职、在同步范围内、至少有一个角色
            通过 → 签发会话 Cookie，302 回到 returnTo（只接受站内相对路径）
            不通过 → 302 回到 /login，失败原因存在登录流程记录里，
                     登录页调用 GET /api/session/feishu/outcome 显示原因
```

- 登录页保持纯 `/login`，不附加参数（前端规则）。原页面通过路由状态传入，经 `start` 存在后端。
- 飞书的 `user_access_token` 只用于读取一次身份，用完即丢，不保存。
- 应急管理员登录保留现有的失败次数限制，由 `ADMIN_PASSWORD_LOGIN_ENABLED`（默认开启）控制。登录页把它折叠为“管理员应急登录”。
- 后续可选：在飞书工作台内打开时自动免登（网页应用免登），流程同样是用 code 换身份，放到第 4 期。

## 4. 部门与人员同步

- 用应用身份（`tenant_access_token`，`/open-apis/auth/v3/tenant_access_token/internal`）调用通讯录接口：
  - 部门树：`/open-apis/contact/v3/departments/{id}/children?fetch_child=true`
  - 部门成员：`/open-apis/contact/v3/users/find_by_department`
- 管理员在“权限管理”页从飞书部门树中勾选同步范围，例如采购部、财务部，自动包含下级部门。
- 同步方式：页面手动“立即同步”，另加每天一次定时同步，复用同一个 Service。
- 人员离职、被停用或移出同步范围时，标为不可用，并立即作废其全部会话。审核记录等历史数据中的操作者保留，显示为“姓名（已离职）”。
- 同步结果（新增、变更、停用人数，失败原因）记入同步记录。同步失败时不停用任何人，避免因接口故障把所有人踢出。

## 5. 权限设计

### 5.1 角色

角色和权限都写在代码里（`identity/policy/`），首期不支持自定义角色。

| 角色                       | 默认对应部门 | 说明                                                                        |
| -------------------------- | ------------ | --------------------------------------------------------------------------- |
| 系统管理员 `admin`         | 指定个人     | 全部权限，外加人员同步、角色分配、同步计划、柠檬云账号                      |
| 财务主管 `finance_manager` | 指定个人     | 财务专员全部权限，外加关闭任务行（确认已开完含差异）、导出、NS 回写异常处理 |
| 财务专员 `finance`         | 财务部       | 财务核对审核、发票导入与柠檬云拉取、比对审核、发票文件上传、NS 同步         |
| 采购专员 `purchaser`       | 采购部       | 开票任务：准备资料、通知供应商、上传回签合同、维护供应商企微群与通知开关    |
| 只读 `viewer`              | 指定个人     | 所有页面只读                                                                |

一个人可以有多个角色，权限取并集。部门默认角色与个人追加的角色分开保存，个人角色可以覆盖部门默认（例如财务部的某人改为只读）。

### 5.2 权限点与接口

所有已登录且有角色的人都能查看各页面数据（数据范围首期不限）。下表只列写操作：

| 权限点                                | 接口（现有路径）                                                                                                       | admin | 财务主管 | 财务 | 采购 | 只读 |
| ------------------------------------- | ---------------------------------------------------------------------------------------------------------------------- | ----- | -------- | ---- | ---- | ---- |
| `sync.ns.run` NS 同步                 | `/api/ns/connect`、`/api/ns/sync/{kind}/pull(-save)`、`/api/sync/ns/runs`、`/api/sync/ns/progress`、`/api/source` 上传 | ✓     | ✓        | ✓    | —    | —    |
| `sync.plan.edit` 同步计划             | `PUT /api/sync/plan`                                                                                                   | ✓     | ✓        | —    | —    | —    |
| `sync.lemon.run` 柠檬云拉取           | `/api/sync/lemon/invoices/pull-save`、`refresh-details`、`detail-actions`、`/batches` 提交与重试                       | ✓     | ✓        | ✓    | —    | —    |
| `sync.lemon.account` 柠檬云账号       | `/api/sync/lemon/binding/*`、`/account`                                                                                | ✓     | —        | —    | —    | —    |
| `review.approve` 财务核对审核         | `/api/review/declarations/{id}/approve`、`approve-batch`                                                               | ✓     | ✓        | ✓    | —    | —    |
| `invoice.import` 发票导入             | `/api/invoices/import/preview`、`confirm`                                                                              | ✓     | ✓        | ✓    | —    | —    |
| `matching.propose` 生成与新建分配     | `/api/matching/proposals/generate`、`POST /allocations`                                                                | ✓     | ✓        | ✓    | —    | —    |
| `matching.approve` 比对审核           | `allocations/{id}/confirm`、`reject`、`cancel`、`reverify`、`replace`、`confirm-batch`                                 | ✓     | ✓        | ✓    | —    | —    |
| `matching.file.upload` 发票文件       | `/api/matching/invoice-files/upload`                                                                                   | ✓     | ✓        | ✓    | —    | —    |
| `task.handle` 开票任务处理            | 资料准备 `documents/*/prepare`、`declaration-documents/*/prepare`；通知 `notification/*`                               | ✓     | ✓        | ✓    | ✓    | —    |
| `task.signed.upload` 回签合同         | `/api/tasks/signed-contracts/upload`、`upload-jobs/*`                                                                  | ✓     | ✓        | ✓    | ✓    | —    |
| `task.line.close` 关闭任务行          | `/api/tasks/{id}/lines/{line_id}/close`                                                                                | ✓     | ✓        | —    | —    | —    |
| `task.supplier.manage` 供应商通知设置 | `supplier-groups/save`、`profiles/notify`、`external-groups/import/*`、`associate`、`wecom/match`                      | ✓     | ✓        | —    | ✓    | —    |
| `data.export` 导出                    | `/api/matching` 导出等 `*/export`                                                                                      | ✓     | ✓        | ✓    | —    | —    |
| `identity.manage` 人员与权限          | 新增的权限管理接口                                                                                                     | ✓     | —        | —    | —    | —    |

查询类 `POST .../query` 只需登录且有任一角色。表中的分配是首版建议，评审时可以直接改表。

### 5.3 落实方式

- **后端为准**：controller 中每个写接口声明所需权限，例如 `actor: Actor = Depends(require("matching.approve"))`。新增一条架构测试：遍历全部非 GET 路由，未声明权限（且不在查询白名单）的直接失败，避免以后漏加。
- **权限实时生效**：每次请求按会话查当前人员的角色与在职状态。调整角色或停用人员后，下一次请求立即生效，不用等会话过期。
- **前端只做展示**：`GET /api/session` 返回姓名、头像、所属部门、角色和权限点列表。前端据此隐藏导航、禁用按钮并提示“需要 xx 权限”，但不替代后端校验。
- **替换写死的 `user:admin` 判断**：柠檬云账号相关改为检查 `sync.lemon.account`。后台柠檬云任务记录发起人，以发起人身份执行，不再固定为 admin。
- **服务身份**：`service:*` 保持只读，拒绝全部写权限（与现状一致）。

## 6. 操作者标识

- 飞书用户的操作者字符串为 `user:fs:<user_id>`（飞书企业内的 user_id，比 open_id 稳定），应急管理员仍为 `user:admin`，两者不会冲突。
- 现有各表的 `reviewed_by`、`uploaded_by` 等字段继续存操作者字符串，结构不变。各模块的 VO 通过 `identity.public` 把它转换为姓名展示，历史 `user:admin` 显示为“管理员（应急账号）”。
- 现有测试数据中的 `user:admin` 不迁移。

## 7. 数据表（`identity` 模块，新迁移）

| 表                          | 用途                                                                                       |
| --------------------------- | ------------------------------------------------------------------------------------------ |
| `identity_departments`      | 飞书部门：部门 ID、上级、名称、路径、状态、同步时间                                        |
| `identity_users`            | 飞书人员：user_id、open_id、union_id、姓名、头像地址、在职状态、同步时间；不存手机号、邮箱 |
| `identity_user_departments` | 人员与部门的多对多关系                                                                     |
| `identity_sync_scopes`      | 管理员勾选的同步根部门                                                                     |
| `identity_department_roles` | 部门默认角色                                                                               |
| `identity_user_roles`       | 个人追加或覆盖的角色，记录授予人和时间                                                     |
| `identity_sessions`         | 会话：只存令牌的 SHA-256；人员、过期时间、作废时间、来源 IP                                |
| `identity_login_flows`      | 一次性 state、returnTo、过期时间、失败原因                                                 |
| `identity_sync_runs`        | 同步记录                                                                                   |
| `identity_audit`            | 登录成功与失败、角色变更、同步范围变更                                                     |

会话落库后，重启不会把所有人退出，也就不再受“单 API 进程”的限制。登录失败次数限制也一并落库。

## 8. 前端

- 登录页：主按钮“使用飞书登录”，下方折叠“管理员应急登录”；显示后端返回的失败原因，例如“你不在系统使用范围内，请联系管理员”。
- 右上角会话菜单：显示姓名、头像、角色。
- 新页面“权限管理” `/settings/access`（登记在 `app/paths.ts`），只有 `identity.manage` 可见：
  - 同步范围：飞书部门树勾选、立即同步、最近同步结果；
  - 部门角色：每个已同步部门的默认角色；
  - 人员：姓名、部门、生效角色及来源（部门 / 个人），可追加或覆盖角色，不能编辑姓名和部门。
- 页面用统一组件库组合；无权限的按钮显示禁用和原因，不只是隐藏。

## 9. 分期

| 期                 | 内容                                                                                                                                      | 依赖                |
| ------------------ | ----------------------------------------------------------------------------------------------------------------------------------------- | ------------------- |
| 1 飞书登录与同步   | 飞书客户端（integrations/feishu）、登录流程、部门与人员同步、会话落库、应急登录保留；所有有角色的人暂时拥有全部写权限（与现在一致）       | 第 2 节飞书应用就绪 |
| 2 权限落实         | 权限点、角色、`require` 依赖、67 个写接口逐个声明并加架构测试、替换写死的 admin 判断、`/api/session` 返回权限、前端按钮与导航、权限管理页 | 第 1 期             |
| 3 操作者展示与审计 | 各页面审核人、上传人显示姓名；审计查询                                                                                                    | 第 2 期             |
| 4 以后             | 飞书工作台免登、通讯录变更事件订阅、按负责供应商限制数据范围                                                                              | 业务需要时          |

建议第 1、2 期在 11 月 4 日试用前完成：多人试用时必须能区分“谁审核、谁上传”，也不能让采购人员误点财务审核。

## 10. 验证

- 后端用伪造的飞书客户端测试：
  - state 一次性与过期、tenant_key 不符、人员不存在 / 离职 / 无角色；
  - returnTo 只接受站内路径；同步失败不停用人员；
  - 离职后会话立即失效、角色变更立即生效；
  - 权限矩阵逐个接口验证；架构测试检查写接口都已声明权限。
- 前端：登录页各状态、无权限按钮、权限管理页的加载、空数据、失败状态。
- 联调：用飞书测试企业或少数真实账号，在 `invoice.yesion.net` 走一遍完整登录、同步与权限。应用凭证由你本人配置。

# 工作台登录与人员权限

日常使用飞书登录；管理员账号密码作为应急入口，折叠在登录页下方（2026-10-28，方案见 [飞书登录、部门同步与权限方案](../../../../docs/feishu-identity-plan.md)）。

## 路由与文件职责

- `routes.tsx` 注册独立登录页 `/login`，路径集中在 `app/paths.ts`，由 `app/router.tsx` 汇总。
- `pages/LoginPage.tsx`：先向后端读取可用的登录方式（`/api/session/options`）。主按钮“使用飞书登录”向后端发起登录流程后整页跳转到飞书；回跳地址存在后端，登录页地址不带参数。飞书登录失败后回到 `/login`，页面通过 `/api/session/feishu/outcome` 显示失败原因。飞书未配置时直接显示应急表单。
- `components/PasswordLoginForm.tsx`：应急管理员账号密码表单，支持密码显隐、忙碌禁用和失败后的焦点恢复。`pages/login.css` 只作用于登录页。
- `SessionProvider.tsx` 与 `hooks/useSessionState.ts` 统一管理会话检查、登录、退出和 401 失效通知，并保存后端返回的当前登录人（姓名、角色）。
- `RequireSession.tsx` 保护业务路由：未登录或会话失效时替换导航到纯 `/login`，原路径只保存在浏览器路由状态中。
- `login-navigation.ts` 处理登录回跳：外部地址、无效地址、登录页自身均回退首页。后端对飞书登录的回跳地址做同样的校验。
- `SessionMenu.tsx` 通过 `app/WorkspaceFrame.tsx` 装配到侧栏底部，显示姓名首字、姓名、角色和退出。飞书头像是外部图片，页面安全策略只允许本站图片，所以不显示头像。
- `pages/AccessPage.tsx`（`/settings/access`，侧栏“系统 → 人员与权限”）：只有系统管理员可见，接口仍由后端校验。
  - `SyncCard`：立即同步飞书，并显示最近一次同步结果。
  - `DepartmentCard`：勾选同步范围、设置部门默认角色。
  - `UserCard`：人员列表与个人角色调整。
  - `RoleDialog`：选择角色的弹窗。
  - 生效角色由后端计算，页面只展示。

## 接口

`api.ts`：

| 接口                                       | 用途                     |
| ------------------------------------------ | ------------------------ |
| `GET/POST/DELETE /api/session`             | 会话检查、应急登录、退出 |
| `GET /api/session/options`                 | 登录方式                 |
| `POST /api/session/feishu/start`           | 发起飞书登录             |
| `GET /api/session/feishu/outcome`          | 飞书登录结果             |
| `GET /api/identity/access`                 | 人员与权限总览           |
| `POST /api/identity/sync`                  | 立即同步飞书             |
| `PUT /api/identity/scopes`                 | 保存同步范围             |
| `PUT /api/identity/departments/{id}/roles` | 部门默认角色             |
| `PUT /api/identity/users/{id}/roles`       | 个人角色                 |

兼容函数 `openLocalSession` 仅检查现有会话，待业务调用方统一迁移命名后删除。

## 约束

- 密码提交后清空，不存入本地存储，不自动重放凭据。
- 角色、能否登录、能否管理权限全部由后端判定；前端按 `canManageAccess` 隐藏菜单只是展示。
- 人员列表首期一次返回同步范围内全部人员，不分页（采购、财务两个部门规模），人数明显增加后改为后端分页查询。

## 验证

运行构建、类型、lint、`test:web`。路由测试覆盖独立登录地址、站内回跳、外部地址和循环跳转防护，以及“读取登录方式前不展示表单”。

2026-10-28 用本地隔离 SQLite 加模拟飞书在浏览器走通以下内容：

- 应急登录 → 同步部门 → 选择范围、设置部门角色 → 同步成员；
- 退出后用飞书登录，回到原页面，侧栏显示姓名与角色；非管理员看不到菜单，直接访问时显示后端拒绝原因；
- 检查了桌面与 375px 窄屏。

真实飞书授权页尚未联调。

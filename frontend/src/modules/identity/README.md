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
  - `ImportedDirectory`：默认显示有已导入员工的部门和全部已导入员工，切换部门只查本地数据库。空部门由后端从 `importedDepartments` 排除，有下级员工的上级部门保留；未启用、已停用账号仍属于已导入员工。`DepartmentTree` 为本地组织和飞书预览共用导航。
  - `DirectoryPicker`：只有点击“同步飞书”才读取飞书并进入选择模式，支持整部门、单人和跨部门选择。多部门信息折叠展开，底部操作栏吸附在可见区域；读取中保留本地员工列表，读取失败可继续查看。
  - `DirectoryConfirmation`：弹窗展示后端给出的去重人数、导入与移出名单，确认后才保存范围及人员。同步完成回到当前部门的已导入员工，只刷新本地数据，不再次全量拉飞书。“返回已导入员工”退出预览，不改变已保存范围。
  - `UserCard`：跟随当前部门查询已导入人员（含下级），设置部门默认角色及个人角色、启用开关。
  - `RoleDialog`：角色来源与启用状态；保存后立即生效。新导入人员默认待授权。
  - `useDirectorySelection` / `useAccessUsers`：接口与请求状态，旧响应不覆盖新选择。
  - 生效角色由后端计算，页面只展示。

## 接口

`api.ts`：

| 接口                                                 | 用途                             |
| ---------------------------------------------------- | -------------------------------- |
| `GET/POST/DELETE /api/session`                       | 会话检查、应急登录、退出         |
| `GET /api/session/options`                           | 登录方式                         |
| `POST /api/session/feishu/start`                     | 发起飞书登录                     |
| `GET /api/session/feishu/outcome`                    | 飞书登录结果                     |
| `GET /api/identity/access`                           | 人员与权限总览                   |
| `POST /api/identity/directory/previews`              | 读取真实组织，返回短期预览       |
| `POST /api/identity/directory/previews/{id}/members` | 按部门搜索分页、后端计算选中状态 |
| `POST /api/identity/directory/previews/{id}/plan`    | 确认同步范围与移出影响           |
| `POST /api/identity/directory/previews/{id}/sync`    | 原子导入并保存范围，预览 ID 幂等 |
| `GET /api/identity/users`                            | 服务端搜索、部门筛选与分页       |
| `PUT /api/identity/departments/{id}/roles`           | 部门默认角色                     |
| `PUT /api/identity/users/{id}/access`                | 个人角色与启用状态               |

兼容函数 `openLocalSession` 仅检查现有会话，待业务调用方统一迁移命名后删除。

## 约束

- 密码提交后清空，不存入本地存储，不自动重放凭据。
- 角色、能否登录、能否管理权限全部由后端判定；前端按 `canManageAccess` 隐藏菜单只是展示。
- 人员查询与预览成员查询均在后端筛选，每页 50 人。前端只管理用户选择；继承范围、去重人数、是否可启用由后端决定。范围变更后需重新生成确认内容。
- 前后端分批更新的一个版本兼容期内，旧 `/access` 缺少 `importedDepartments` 时使用原 `departments` 并提示后端待更新；不能把缺失字段当成没有部门。新后端明确返回空数组时仍隐藏空部门。切换部门清空旧姓名及页码条件，同部门重复查询仍重新请求；筛选始终调用后端 `/users`，不调用飞书。兼容分支在所有部署均返回新字段后移除。
- 整部门包含下级及未来新增成员，单人按 user_id 持续跟踪，二者去重。左侧部门数量为直属成员数，个人跨部门出现时不能重复导入。
- 新导入人员必须设置角色并启用；已有人员保留设置。业务细粒度权限仍按现有阶段约束，不能将“只读”标签当作所有业务接口已限制写入的承诺。

## 验证

运行构建、类型、lint、`test:web`。路由测试覆盖独立登录地址、站内回跳、外部地址和循环跳转防护，以及“读取登录方式前不展示表单”。

2026-10-28 用本地隔离 SQLite 加模拟飞书在浏览器走通以下内容：

- 应急登录 → 同步部门 → 选择范围、设置部门角色 → 同步成员；
- 退出后用飞书登录，回到原页面，侧栏显示姓名与角色；非管理员看不到菜单，直接访问时显示后端拒绝原因；
- 检查了桌面与 375px 窄屏。

真实飞书授权页尚未联调。

工作区验收使用隔离 API 与模拟飞书，覆盖单人及整部门（含下级）导入、保留当前部门、角色启用、确认弹窗返回、撤销选择、跨部门选择、失败反馈、空搜索，以及 1440px / 390px 布局。2026-10-28 加载流程调整为本地优先：首屏、部门切换及同步完成后的刷新不调用飞书，仅按钮触发读取。浏览器验收不修改正式账号；本次没有新增后端接口或数据库迁移。

# 身份模块（identity）

飞书登录、飞书部门与人员同步、角色与权限管理，以及应急管理员账号密码登录。方案与分期见 [飞书登录、部门同步与权限方案](../../../docs/feishu-identity-plan.md)；本文对应第 1 期（2026-10-28）。

## 文件职责

| 目录                     | 内容                                                                                                                                                                                                                                                                |
| ------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `controller/`            | `session_controller.py` 会话、应急登录、登录方式<br>`feishu_controller.py` 飞书登录发起、回调、结果<br>`access_controller.py` 人员与权限管理                                                                                                                        |
| `service/`               | `session_service.py` 会话签发与每次请求的身份校验<br>`feishu_login_service.py` 飞书授权登录<br>`directory_sync_service.py` 飞书部门与成员同步，`directory_sync_worker.py` 每日定时同步<br>`access_reader.py` 生效角色计算<br>`access_service.py` 同步范围与角色维护 |
| `dao/`                   | 部门、人员、登录流程、同步记录、审计                                                                                                                                                                                                                                |
| `entity/`                | 9 张 `identity_*` 表，见[数据字典](../../../docs/mysql/current-data-dictionary.md)                                                                                                                                                                                  |
| `policy/`                | `role_policy.py` 角色定义<br>`login_policy.py` 操作者标识、回跳地址、在职状态、登录资格<br>`department_policy.py` 部门树计算                                                                                                                                        |
| `dto/`、`vo/`、`mapper/` | 请求、响应与同步记录转换                                                                                                                                                                                                                                            |

飞书接口适配器在 `backend/integrations/feishu.py`。

## 接口

| 接口                                       | 说明                                                                    |
| ------------------------------------------ | ----------------------------------------------------------------------- |
| `GET /api/session`                         | 当前身份：`{authenticated, user: {kind, name, roles, canManageAccess}}` |
| `GET /api/session/options`                 | 未登录可读：`{feishu, password}`，表示是否显示飞书登录、应急登录        |
| `POST /api/session`、`DELETE /api/session` | 应急管理员登录（`ADMIN_PASSWORD_LOGIN_ENABLED=false` 时返回 403）、退出 |
| `POST /api/session/feishu/start`           | 请求 `{returnTo}`；返回飞书授权地址，并设置流程 Cookie                  |
| `GET /api/session/feishu/callback`         | 飞书回调；成功签发会话并 303 回到 `returnTo`，失败 303 回到 `/login`    |
| `GET /api/session/feishu/outcome`          | 本浏览器最近一次飞书登录的状态与失败原因（10 分钟内）                   |
| `GET /api/identity/access`                 | 部门、同步范围、部门角色、人员、最近同步记录（仅系统管理员）            |
| `POST /api/identity/sync`                  | 立即同步飞书（仅系统管理员）                                            |
| `PUT /api/identity/scopes`                 | `{departmentIds}`：同步根部门，含全部下级                               |
| `PUT /api/identity/departments/{id}/roles` | `{roles}`：部门默认角色，下级部门成员继承                               |
| `PUT /api/identity/users/{id}/roles`       | `{roles, customRoles}`：个人角色；`customRoles` 为是时只按个人角色      |

## 关键规则

- **人员以飞书为准**：本地只保存副本，不能新增人员或修改姓名、部门。只有同步范围内、在职、未冻结且至少有一个角色的人才能登录。同步失败时不停用任何人员。
- **飞书登录**：
  - state 一次性、10 分钟有效，并与发起登录的浏览器绑定（流程 Cookie 的哈希）；
  - 飞书用户令牌用完即丢，不保存；
  - 配置 `FEISHU_TENANT_KEY` 时只接受本企业账号；
  - 回跳只接受站内路径。
- **流程 Cookie 使用 SameSite=Lax**：飞书回跳是跨站顶层导航，Strict 不会随回调发送。流程 Cookie 只用于绑定浏览器，不能代替会话；会话 Cookie 仍为 Strict。
- **会话**：
  - 仍在 API 进程内存中，8 小时有效，因此保持单 API 进程部署；会话落库按方案放到后续。
  - 飞书用户的会话每次请求都按数据库校验在职状态与角色，停用、移出范围或收回全部角色后，下一次请求返回 401。
- **操作者**：飞书用户为 `user:fs:<飞书 user_id>`；应急管理员为 `user:<ADMIN_USERNAME>`，固定拥有系统管理员角色；`service:feishu` 服务密钥身份不变。
- **第 1 期权限**：只区分“能否管理人员与权限”（系统管理员）。其他写操作仍只要求登录（有角色），按角色细分在第 2 期落实。柠檬云账号绑定等 5 处仍写死只允许应急管理员，也在第 2 期改为按权限判断。
- **审计**：登录成功与失败、同步范围、部门角色、个人角色变更写入 `identity_audit`。

## 配置

`.env` 中配置 `FEISHU_APP_ID`、`FEISHU_APP_SECRET`（两项须同时填写），可选 `FEISHU_TENANT_KEY`、`ADMIN_PASSWORD_LOGIN_ENABLED`。飞书开放平台“重定向 URL”须登记 `APP_ORIGIN + /api/session/feishu/callback`，两者必须完全一致。

## 验证

- `backend/tests/identity/`：模拟飞书的完整登录、同步、权限测试，以及用模拟 HTTP 传输测试飞书适配器。
- 在项目根目录运行 `npm.cmd run test:api`、`npm.cmd run lint:api`、`npm.cmd run check:architecture`。
- 真实飞书授权尚未联调。

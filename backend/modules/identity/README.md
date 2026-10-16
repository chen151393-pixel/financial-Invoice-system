# 身份模块

提供单管理员账号密码登录、退出、来源校验、失败次数限制与单进程内存会话。

## 文件职责

controller.py 处理 HTTP/Cookie，dto.py 校验登录请求，service.py 管理身份。没有数据库 DAO，因为账号来自服务器配置，会话尚未落库；本次不新增用户表、注册、角色或找回密码。

## 公开入口

| 接口 | 请求与响应 | 用途 |
| --- | --- | --- |
| GET /api/session | 成功返回 `{ authenticated: true }`，无效会话返回 401 | 检查登录状态 |
| POST /api/session | 请求 `{ username: string, password: string }`；成功返回 `{ authenticated: true }` 并设置 Cookie | 账号密码登录 |
| DELETE /api/session | 成功返回 `{ authenticated: false }`，删除 Cookie 并撤销服务器会话 | 退出 |
| POST /api/session/local | 固定拒绝签发免密会话，返回 403 | 旧客户端兼容一个版本；确认前端及脚本均不再调用后删除 |

模块通过应用工厂注入依赖，不建立全局客户端或全局数据库连接。

## 关键约束

- `ADMIN_USERNAME` 默认 admin；`ADMIN_PASSWORD` 必须在服务器配置为非空值，无默认密码。用户名和密码由后端校验，DTO 拒绝空字符串、错误类型及额外字段；不设最短密码长度。
- 本机和远程浏览器统一登录；旧 `LOCAL_BROWSER_ACCESS` 不再读取，不能恢复免密访问。
- Cookie 为 HttpOnly、SameSite=Strict，HTTPS 下启用 Secure；8 小时后失效，重新登录轮换当前 Cookie 对应的会话。退出后旧 Cookie 不可重用。
- 每个客户端 IP 在 15 分钟窗口内失败 10 次后拒绝登录；不信任转发 IP。保留独立服务密钥身份。
- 登录及使用 Cookie 的写请求要求 Origin 与 APP_ORIGIN 一致。不得在 Service 中依赖 Request，不返回 NS 凭证。
- owner 仍为 `user:ADMIN_USERNAME`；本次不修改数据归属。会话和限流在内存中，重启需要重新登录，部署须使用单 API 进程。

## 验证

在项目根目录运行 `npm.cmd run test:api`、`npm.cmd run lint:api` 和 `npm.cmd run check:architecture`。认证测试使用 FakeNS 与隔离数据库，不操作真实 NS。

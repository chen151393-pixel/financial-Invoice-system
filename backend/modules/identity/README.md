# 身份模块

本机浏览器自动会话、密码登录API、退出API、来源校验与单进程内存会话。

## 文件职责

controller.py处理HTTP/Cookie，dto.py校验登录请求，service.py管理身份。没有数据库DAO，因为目前会话尚未落库。

## 公开入口

`POST /api/session/local` 和 `POST/DELETE /api/session`。模块通过应用工厂注入依赖，不建立全局客户端或全局数据库连接。

## 关键约束

不得在Service中依赖Request，不返回NS凭证。

管理员密码 `ADMIN_PASSWORD` 必须配置为非空值，不设最短字符数限制。登录仍校验用户名、密码和请求来源，并保留失败次数限制。

## 验证

在项目根目录运行 `npm.cmd run test:api`、`npm.cmd run lint:api` 和 `npm.cmd run check:architecture`。接口验证使用FakeNS，不操作真实NS。

本机免登录通过 `LOCAL_BROWSER_ACCESS=true` 启用，仅允许本机监听、本机APP_ORIGIN及实际回环客户端；Origin和Host必须匹配，忽略转发IP声明。签发会话使用原管理员owner，原接口继续要求会话或服务密钥。前端已移除登录表单，过期后刷新页面重新进入。测试覆盖远程／跨站／错误Host拒绝、IPv6、本机配置边界及owner不变。

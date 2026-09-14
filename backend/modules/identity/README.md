# 身份模块

登录、退出、来源校验与单进程内存会话。

## 文件职责

controller.py处理HTTP/Cookie，dto.py校验登录请求，service.py管理身份。没有数据库DAO，因为目前会话尚未落库。

## 公开入口

`POST/DELETE /api/session`。模块通过应用工厂注入依赖，不建立全局客户端或全局数据库连接。

## 关键约束

不得在Service中依赖Request，不返回NS凭证。

管理员密码 `ADMIN_PASSWORD` 必须配置为非空值，不设最短字符数限制。登录仍校验用户名、密码和请求来源，并保留失败次数限制。

## 验证

在项目根目录运行 `npm.cmd run test:api`、`npm.cmd run lint:api` 和 `npm.cmd run check:architecture`。接口验证使用FakeNS，不操作真实NS。

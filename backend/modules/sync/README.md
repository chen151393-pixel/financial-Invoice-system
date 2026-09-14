# 连接状态模块

展示服务器连接配置与最近M2M认证结果，尚未执行全量或增量同步。

## 文件职责

controller.py接收请求；service.py生成连接状态并调用NS认证。没有持久同步队列。

## 公开入口

`GET /api/ns/status；POST /api/ns/connect`。模块通过应用工厂注入依赖，不建立全局客户端或全局数据库连接。

## 关键约束

认证成功不等于拥有记录读写权限，状态不能虚构为同步完成。

## 验证

在项目根目录运行 `npm.cmd run test:api`、`npm.cmd run lint:api` 和 `npm.cmd run check:architecture`。接口验证使用FakeNS，不操作真实NS。

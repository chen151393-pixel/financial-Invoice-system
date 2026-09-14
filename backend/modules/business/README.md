# 业务记录模块

查询配置允许访问的NS记录，支持列表与指定ID。尚未实现标准业务单据落库。

## 文件职责

controller.py声明接口；dto.py定义查询请求；service.py校验查询目标并调用注入的NS客户端。

## 公开入口

`GET /api/ns/records/*；POST /api/ns/query`。模块通过应用工厂注入依赖，不建立全局客户端或全局数据库连接。

## 关键约束

详细查询空ID在后端拒绝，保留旧GET协议。

## 验证

在项目根目录运行 `npm.cmd run test:api`、`npm.cmd run lint:api` 和 `npm.cmd run check:architecture`。接口验证使用FakeNS，不操作真实NS。

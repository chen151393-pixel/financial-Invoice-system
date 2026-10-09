# 审计模块

在回写事务内记录操作者、任务、动作与时间。

## 文件职责

public.py是模块公开记录接口；dao.py写SQL；entity.py保存既有ns_audit表定义。

## 公开入口

`record(connection, at=..., actor=..., action=..., preview_id=...)`。模块通过应用工厂注入依赖，不建立全局客户端或全局数据库连接。

## 关键约束

复用调用方事务，不单独提交；其他模块不直接导入audit.dao/entity。

## 验证

在项目根目录运行 `npm.cmd run test:api`、`npm.cmd run lint:api` 和 `npm.cmd run check:architecture`。接口验证使用FakeNS，不操作真实NS。

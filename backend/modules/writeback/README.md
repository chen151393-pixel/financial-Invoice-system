# 回写模块

生成不可变预览、用户确认、执行NS写入、查询与离线恢复。

## 文件职责

controller.py接口；dto.py请求；vo.py响应；service.py业务事务；policy.py规则；dao.py SQL；entity.py表；mapper.py纯转换。

## 公开入口

`POST /api/ns/preview、/preview-text、/execute；GET /api/ns/jobs、/jobs/{id}、/jobs/{id}/view`。模块通过应用工厂注入依赖，不建立全局客户端或全局数据库连接。

## 关键约束

Service持有事务，DAO复用连接；外部请求在事务外。unknown禁止盲目重试；尚未接入多角色审批。

## 验证

在项目根目录运行 `npm.cmd run test:api`、`npm.cmd run lint:api` 和 `npm.cmd run check:architecture`。接口验证使用FakeNS，不操作真实NS。

# 业务记录模块

查询配置允许访问的NS记录，支持列表与指定ID。已实现采购与报关按PL完整落库；本机已配置真实沙箱映射并通过单个PL只读联查，真实保存尚未验收。

已接入独立 MySQL 业务库连接检查：`GET /api/business/database-status` 需要现有登录身份，返回未配置、连接失败、缺少表或连接成功。`service.py` 调用 `core/business_database.py` 的基础设施检查，`database_vo.py` 定义安全响应。连接参数使用 `BUSINESS_MYSQL_*`，不替换原应用库；配置及命令见 [MySQL说明](../../../docs/mysql/README.md)。检查不执行建表或单据同步。

已增加 PL 单联查：`pl_service.py` 编排按需读取，`pl_config.py` 校验服务器字段映射，`pl_mapper.py` 转换源字段，`pl_vo.py` 定义输出。配置和边界见 [PL 联查说明](../../../docs/pl-lookup.md)。

## 文件职责

真实 PL 核对接口 `POST /api/ns/pl-comparison`：`pl_comparison_service.py` 负责公司筛选与归组；`pl_comparison_mapper.py` 将源行转换为固定 15 列；`pl_comparison_vo.py` 定义响应；`pl_export.py` 生成同次读取结果的 Excel。复用 `pl_reader.py`，额外按 PL 独立查找报关明细，避免没有采购关联时漏报关。只读，不触发数据库保存或 NS 写入。边界与验证见 [PL 联查说明](../../../docs/pl-lookup.md)。

controller.py声明接口；dto.py定义查询请求；service.py校验查询目标并调用注入的NS客户端。

## 公开入口

`GET /api/ns/records/*；POST /api/ns/query`。模块通过应用工厂注入依赖，不建立全局客户端或全局数据库连接。

## 关键约束

详细查询空ID在后端拒绝，保留旧GET协议。

## 验证

在项目根目录运行 `npm.cmd run test:api`、`npm.cmd run lint:api` 和 `npm.cmd run check:architecture`。接口验证使用FakeNS，不操作真实NS。

## PL本地保存

`pl_reader.py`共用完整读取；`entity.py`反射既有四表，不自动建表；`storage_mapper.py`纯字段／Decimal转换；`dao.py`负责命名锁、查询及保存SQL；`storage_service.py`协调账户范围串行读取及原子事务。接口与字段映射见 [PL保存说明](../../../docs/pl-storage.md)。后端保留本地查询、拉取保存及仅查询 NS 接口；旧 PL 单联查前端已移除，当前核对页仅查询与导出。

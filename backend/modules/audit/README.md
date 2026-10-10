# 审计模块

在财务审核事务内记录操作者、审核快照、备注与时间（`finance_review_audit`）。

## 文件职责

`public.py` 是公开记录接口；`dao.py` 写 SQL；`entity.py` 定义 `finance_review_audit`，以及保留的历史回写表 `ns_previews`、`ns_target_locks`、`ns_audit`。

## 公开入口

`record_finance_review(connection, at=..., actor=..., snapshot_id=..., note=...)`，复用调用方事务。

## 历史回写表

NS 回写代码已移至 `archive/writeback` 分支。三张回写表的定义仍登记在元数据中，用于迁移结构核验和历史应用库导入时原样复制 executing/unknown 记录及其锁；主线没有代码读写它们。删除前须人工确认没有 executing/unknown 记录，再单独迁移删除。

架构方案第 4 步把审核审计并入 `review` 模块后，本模块只剩历史回写表，届时一并处理。

## 关键约束

复用调用方事务，不单独提交；其他模块不直接导入 audit.dao/entity。

## 验证

在项目根目录运行 `npm.cmd run test:api`、`npm.cmd run lint:api` 和 `npm.cmd run check:architecture`。

-- 供应商人员关联精简版（MySQL 8）：只新增 task_supplier_owners 一表九字段。
-- 已确认旧三表方案未在业务库执行，本脚本替换尚未部署的 0043。
-- 执行前确认 schema_version 为 0042_review_customs_receipts，且新表尚不存在。
-- 不回填历史、不修改既有任务，不调用 NS；与自动迁移二选一，不要重复执行。
SELECT DATABASE();
SELECT version_num FROM schema_version;

-- Running upgrade 0042_review_customs_receipts -> 0043_task_supplier_owners

CREATE TABLE task_supplier_owners (
    id BIGINT UNSIGNED NOT NULL COMMENT '记录主键，同时用于并发版本校验' AUTO_INCREMENT,
    supplier_id BIGINT UNSIGNED NOT NULL COMMENT 'source 供应商本地主键，跨模块不建外键',
    company_id BIGINT UNSIGNED NOT NULL COMMENT 'source 采购公司本地主键，跨模块不建外键',
    member_id BIGINT UNSIGNED NOT NULL COMMENT 'identity 人员本地主键，跨模块不建外键',
    member_name VARCHAR(200) NOT NULL COMMENT '人员姓名快照，保留历史显示',
    effective_date DATE NOT NULL COMMENT '人员分工生效日期，北京时间；同日取较新记录',
    reason VARCHAR(300) NOT NULL COMMENT '新增或调整原因',
    actor VARCHAR(200) NOT NULL COMMENT '来自认证身份的操作者',
    created_at DATETIME(6) NOT NULL COMMENT '记录保存时间，UTC；历史只追加' DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id)
)COMMENT='供应商与采购抬头的人员分工历史；不另建当前关系、版本或任务归属表' ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin;

CREATE INDEX ix_task_owner_effective ON task_supplier_owners (supplier_id, company_id, effective_date, id);

UPDATE schema_version SET version_num='0043_task_supplier_owners' WHERE schema_version.version_num = '0042_review_customs_receipts';


COMMIT;
SELECT version_num FROM schema_version;

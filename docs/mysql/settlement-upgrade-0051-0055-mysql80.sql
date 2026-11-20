-- 结汇模块 0051～0055：纯 MySQL 8.0 手动升级 SQL
-- 适用 MySQL 8.0.16 及以上的 8.0 版本；使用 InnoDB / utf8mb4。
-- 本文件只有 SELECT / SET / CREATE TABLE / ALTER TABLE / CREATE INDEX / UPDATE，
-- 不含存储过程，也不需要 DELIMITER。
--
-- 执行前务必确认：
-- 1. 备份目标业务库，在客户端选中目标库（本文件不固定数据库名称）。
-- 2. 先单独执行下面的版本查询；完整运行本文件要求当前版本为：
--       0050_settlement_direct_documents
-- 3. 若已是 0051～0054，只从对应的下一个版本段开始，按顺序执行剩余完整段。
--    若已是 0055，不要执行；低于 0050 时先补齐之前的迁移。
-- 4. 这是一次性增量 SQL，不支持重复运行；任何语句报错应立即停止。
--    若之前升级中途失败，先核对实际表结构，不要直接重跑或手改版本号。
-- 5. MySQL DDL 会自动提交，不能靠 ROLLBACK 撤销整个升级。
--    不要用“忽略错误继续执行”，每段末尾的 schema_version 更新须在该段成功后执行。
-- 6. 只调整本地业务库结构，不删除业务记录，不修改收汇金额，不写 NS。

-- 【先单独执行】确认选中的数据库与版本。
SELECT DATABASE() AS target_database, VERSION() AS mysql_version;
SELECT version_num FROM schema_version;

-- 【确认符合上述前置条件后】再执行以下对应版本段。
SET NAMES utf8mb4 COLLATE utf8mb4_bin;

-- ============================================================
-- 0051：创建直接收汇资料组，扩展提单与合同归属
-- 前置版本：0050_settlement_direct_documents
-- ============================================================

CREATE TABLE settlement_document_groups (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    group_no VARCHAR(40) COLLATE utf8mb4_bin NOT NULL,
    request_id VARCHAR(36) COLLATE utf8mb4_bin NOT NULL,
    consignee VARCHAR(200) NOT NULL,
    currency VARCHAR(10) NOT NULL,
    created_by VARCHAR(190) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    updated_at DATETIME(6) NOT NULL,
    PRIMARY KEY (id),
    UNIQUE (group_no),
    UNIQUE (request_id)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin;

CREATE TABLE settlement_document_group_items (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    group_id BIGINT UNSIGNED NOT NULL,
    declaration_no VARCHAR(150) COLLATE utf8mb4_bin NOT NULL,
    created_at DATETIME(6) NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT uq_settlement_document_group_declaration UNIQUE (declaration_no),
    FOREIGN KEY(group_id) REFERENCES settlement_document_groups (id)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin;

ALTER TABLE settlement_bills DROP CHECK ck_settlement_bill_source;

ALTER TABLE settlement_bills ADD COLUMN document_group_id BIGINT UNSIGNED COMMENT '所属直接收汇资料组';

ALTER TABLE settlement_bills ADD CONSTRAINT fk_settlement_bill_group FOREIGN KEY(document_group_id) REFERENCES settlement_document_groups (id);

ALTER TABLE settlement_bills ADD CONSTRAINT ck_settlement_bill_source CHECK ((CASE WHEN batch_id IS NOT NULL THEN 1 ELSE 0 END + CASE WHEN direct_declaration_no IS NOT NULL THEN 1 ELSE 0 END + CASE WHEN document_group_id IS NOT NULL THEN 1 ELSE 0 END) = 1);

CREATE INDEX ix_settlement_bill_group ON settlement_bills (document_group_id, removed_at);

ALTER TABLE settlement_contracts DROP CHECK ck_settlement_contract_source;

ALTER TABLE settlement_contracts ADD COLUMN document_group_id BIGINT UNSIGNED COMMENT '所属直接收汇资料组';

ALTER TABLE settlement_contracts ADD CONSTRAINT fk_settlement_contract_group FOREIGN KEY(document_group_id) REFERENCES settlement_document_groups (id);

ALTER TABLE settlement_contracts ADD CONSTRAINT ck_settlement_contract_source CHECK ((CASE WHEN batch_id IS NOT NULL THEN 1 ELSE 0 END + CASE WHEN direct_declaration_no IS NOT NULL THEN 1 ELSE 0 END + CASE WHEN document_group_id IS NOT NULL THEN 1 ELSE 0 END) = 1);

ALTER TABLE settlement_contracts ADD COLUMN document_key VARCHAR(64) COLLATE utf8mb4_bin;

ALTER TABLE settlement_contracts ADD CONSTRAINT uq_settlement_contract_group_key UNIQUE (document_group_id, document_key);

UPDATE schema_version SET version_num='0051_settlement_document_groups' WHERE schema_version.version_num = '0050_settlement_direct_documents';

-- ============================================================
-- 0052：补充表和字段中文备注
-- 前置版本：0051_settlement_document_groups
-- ============================================================

ALTER TABLE settlement_document_groups COMMENT '直接收汇资料组，同收货人同币种，可含不同申报抬头';

ALTER TABLE settlement_document_groups MODIFY id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '本地自增主键';

ALTER TABLE settlement_document_groups MODIFY group_no VARCHAR(40) COLLATE utf8mb4_bin NOT NULL COMMENT '资料组编号';

ALTER TABLE settlement_document_groups MODIFY request_id VARCHAR(36) COLLATE utf8mb4_bin NOT NULL COMMENT '创建幂等请求标识';

ALTER TABLE settlement_document_groups MODIFY consignee VARCHAR(200) NOT NULL COMMENT '创建时境外收货人';

ALTER TABLE settlement_document_groups MODIFY currency VARCHAR(10) NOT NULL COMMENT '创建时币种，不跨币种合并';

ALTER TABLE settlement_document_groups MODIFY created_by VARCHAR(190) NOT NULL COMMENT '创建人，取认证身份';

ALTER TABLE settlement_document_groups CHANGE created_at created_at DATETIME(6) NOT NULL COMMENT '本地记录创建时间，UTC';

ALTER TABLE settlement_document_groups CHANGE updated_at updated_at DATETIME(6) NOT NULL COMMENT '本地记录最后更新时间，UTC；由 DAO 更新';

ALTER TABLE settlement_document_group_items COMMENT '直接收汇资料组成员，一张报关单只属于一组';

ALTER TABLE settlement_document_group_items MODIFY id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '本地自增主键';

ALTER TABLE settlement_document_group_items MODIFY group_id BIGINT UNSIGNED NOT NULL COMMENT '所属直接收汇资料组';

ALTER TABLE settlement_document_group_items MODIFY declaration_no VARCHAR(150) COLLATE utf8mb4_bin NOT NULL COMMENT '资料组内报关单，一票只能属于一组';

ALTER TABLE settlement_document_group_items CHANGE created_at created_at DATETIME(6) NOT NULL COMMENT '成员归组时间，UTC';

ALTER TABLE settlement_contracts MODIFY document_key VARCHAR(64) COLLATE utf8mb4_bin NULL COMMENT '资料组内申报抬头与出口合同号的稳定标识';

UPDATE schema_version SET version_num='0052_settlement_group_comments' WHERE schema_version.version_num = '0051_settlement_document_groups';

-- ============================================================
-- 0053：保存资料组合并关系和原始成员范围
-- 前置版本：0052_settlement_group_comments
-- ============================================================

ALTER TABLE settlement_document_groups ADD COLUMN initial_declaration_nos JSON COMMENT '创建时成员快照，合并后仍保留原始范围';

ALTER TABLE settlement_document_groups ADD COLUMN merged_into_id BIGINT UNSIGNED COMMENT '合并后的新资料组，原组保留供追溯';

ALTER TABLE settlement_document_groups ADD COLUMN merged_at DATETIME(6) COMMENT '合并时间，UTC';

ALTER TABLE settlement_document_groups ADD COLUMN merged_by VARCHAR(190) COMMENT '合并操作人，取认证身份';

ALTER TABLE settlement_document_groups ADD CONSTRAINT fk_settlement_document_group_successor FOREIGN KEY(merged_into_id) REFERENCES settlement_document_groups (id);

UPDATE schema_version SET version_num='0053_settlement_group_merge' WHERE schema_version.version_num = '0052_settlement_group_comments';

-- ============================================================
-- 0054：保存香港银行水单原件索引
-- 前置版本：0053_settlement_group_merge
-- ============================================================

CREATE TABLE settlement_hk_slips (
    batch_id BIGINT UNSIGNED NOT NULL COMMENT '所属香港批次主键，一批次一份水单',
    file_name VARCHAR(255) NOT NULL COMMENT '银行水单原始文件名',
    file_id VARCHAR(36) COLLATE utf8mb4_bin NOT NULL COMMENT '资料目录内服务端生成的 PDF 文件标识',
    sha256 VARCHAR(64) COLLATE utf8mb4_bin NOT NULL COMMENT '原件 SHA-256 校验值',
    uploaded_by VARCHAR(190) NOT NULL COMMENT '登记操作人，来自认证身份',
    created_at DATETIME(6) NOT NULL COMMENT '本地记录创建时间，UTC' DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL COMMENT '本地记录最后更新时间，UTC；由 DAO 更新' DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (batch_id),
    FOREIGN KEY(batch_id) REFERENCES settlement_batches (id)
)ENGINE=InnoDB COMMENT='香港到账银行水单原件，随批次留存不写 NS' CHARSET=utf8mb4 COLLATE utf8mb4_bin;

UPDATE schema_version SET version_num='0054_settlement_hk_slips' WHERE schema_version.version_num = '0053_settlement_group_merge';

-- ============================================================
-- 0055：保存资料组来源更新审计记录
-- 前置版本：0054_settlement_hk_slips
-- ============================================================

ALTER TABLE settlement_document_groups ADD COLUMN basis_history JSON COMMENT '人工确认更新来源的前后依据、时间和认证操作者';

UPDATE schema_version SET version_num='0055_settlement_group_basis' WHERE schema_version.version_num = '0054_settlement_hk_slips';

-- 升级完成后检查：应返回 0055_settlement_group_basis。
SELECT version_num FROM schema_version;

-- 应列出资料组、资料组成员和香港水单三张新增表。
SELECT table_name, table_comment
FROM information_schema.tables
WHERE table_schema = DATABASE()
  AND table_name IN (
    'settlement_document_groups',
    'settlement_document_group_items',
    'settlement_hk_slips'
  )
ORDER BY table_name;

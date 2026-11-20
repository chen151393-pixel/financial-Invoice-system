-- 结汇模块：针对 0050 版本已部分执行 0051～0055 的结构修复。
-- 适用本次已核对的 financial_invoice_business；MySQL 8.0.16+（含 8.4）。
-- 保留现有表与业务记录；跳过已存在的表/字段/索引/外键。
-- 最后核验字段、唯一索引、外键和三选一约束，全部通过才登记 0055。
-- 不修改金额，不写 NS，不调用外部服务。不适用于低于 0050 的数据库。
--
-- 执行方法：
-- 1. 停止 app 容器，备份 financial_invoice_business。
-- 2. 用新的 Navicat 查询连接，确认“遇到错误停止”，完整运行本文件。
--    不要只执行选中的部分；不要与原升级 SQL 同时运行。
-- 3. 查看最后一个结果 result_FINAL 和 version_FINAL；任何报错立即停止，
--    断开这个查询连接以释放迁移锁，保留报错供核对，不要手改版本号。
-- 4. 只有 result_FINAL 为“修复完成，可以启动应用”才重启 app。
-- MySQL DDL 自动提交；失败时保留已完成结构，不能靠 ROLLBACK 撤销。
-- 本文件使用会话变量与 PREPARE，无存储过程，不需要 DELIMITER。

USE financial_invoice_business;
SET NAMES utf8mb4 COLLATE utf8mb4_bin;
SET @repair_lock_name=SHA2(CONCAT('schema:',DATABASE()),256);
SET @repair_lock=GET_LOCK(@repair_lock_name,0);
SET @repair_version_count=(SELECT COUNT(*) FROM schema_version);
SET @repair_version_before=(SELECT MIN(version_num) FROM schema_version);
SET @repair_enabled=(DATABASE()='financial_invoice_business' AND @repair_lock=1 AND @@autocommit=1
  AND VERSION() LIKE '8.%' AND @repair_version_count=1 AND @repair_version_before IN (
    '0050_settlement_direct_documents','0051_settlement_document_groups',
    '0052_settlement_group_comments','0053_settlement_group_merge','0054_settlement_hk_slips'));
SELECT DATABASE() AS database_before, VERSION() AS mysql_version,
  @repair_version_before AS version_before, @repair_enabled AS repair_enabled;

-- 补齐规范迁移中的结构；存在的对象不重复创建。

SET @repair_ddl=IF(@repair_enabled AND (NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name='settlement_document_groups')),'CREATE TABLE settlement_document_groups (
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
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin','DO 0');
PREPARE settlement_repair_stmt FROM @repair_ddl;
EXECUTE settlement_repair_stmt;
DEALLOCATE PREPARE settlement_repair_stmt;

SET @repair_ddl=IF(@repair_enabled AND (NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name='settlement_document_group_items')),'CREATE TABLE settlement_document_group_items (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    group_id BIGINT UNSIGNED NOT NULL,
    declaration_no VARCHAR(150) COLLATE utf8mb4_bin NOT NULL,
    created_at DATETIME(6) NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT uq_settlement_document_group_declaration UNIQUE (declaration_no),
    FOREIGN KEY(group_id) REFERENCES settlement_document_groups (id)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_bin','DO 0');
PREPARE settlement_repair_stmt FROM @repair_ddl;
EXECUTE settlement_repair_stmt;
DEALLOCATE PREPARE settlement_repair_stmt;

SET @repair_ddl=IF(@repair_enabled AND (EXISTS (SELECT 1 FROM information_schema.table_constraints WHERE table_schema=DATABASE() AND table_name='settlement_bills' AND constraint_name='ck_settlement_bill_source') AND NOT EXISTS (SELECT 1 FROM information_schema.table_constraints tc JOIN information_schema.check_constraints cc ON cc.constraint_schema=tc.constraint_schema AND cc.constraint_name=tc.constraint_name WHERE tc.table_schema=DATABASE() AND tc.table_name='settlement_bills' AND tc.constraint_name='ck_settlement_bill_source' AND tc.constraint_type='CHECK' AND tc.enforced='YES' AND REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(LOWER(cc.check_clause),'`',''),' ',''),'(',''),')',''),CHAR(9),''),CHAR(10),''),CHAR(13),'')='casewhenbatch_idisnotnullthen1else0end+casewhendirect_declaration_noisnotnullthen1else0end+casewhendocument_group_idisnotnullthen1else0end=1')),'ALTER TABLE settlement_bills DROP CHECK ck_settlement_bill_source','DO 0');
PREPARE settlement_repair_stmt FROM @repair_ddl;
EXECUTE settlement_repair_stmt;
DEALLOCATE PREPARE settlement_repair_stmt;

SET @repair_ddl=IF(@repair_enabled AND (NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='settlement_bills' AND column_name='document_group_id')),'ALTER TABLE settlement_bills ADD COLUMN document_group_id BIGINT UNSIGNED COMMENT ''所属直接收汇资料组''','DO 0');
PREPARE settlement_repair_stmt FROM @repair_ddl;
EXECUTE settlement_repair_stmt;
DEALLOCATE PREPARE settlement_repair_stmt;

SET @repair_ddl=IF(@repair_enabled AND (NOT EXISTS (SELECT 1 FROM information_schema.table_constraints WHERE table_schema=DATABASE() AND table_name='settlement_bills' AND constraint_name='fk_settlement_bill_group')),'ALTER TABLE settlement_bills ADD CONSTRAINT fk_settlement_bill_group FOREIGN KEY(document_group_id) REFERENCES settlement_document_groups (id)','DO 0');
PREPARE settlement_repair_stmt FROM @repair_ddl;
EXECUTE settlement_repair_stmt;
DEALLOCATE PREPARE settlement_repair_stmt;

SET @repair_ddl=IF(@repair_enabled AND (NOT EXISTS (SELECT 1 FROM information_schema.table_constraints WHERE table_schema=DATABASE() AND table_name='settlement_bills' AND constraint_name='ck_settlement_bill_source')),'ALTER TABLE settlement_bills ADD CONSTRAINT ck_settlement_bill_source CHECK ((CASE WHEN batch_id IS NOT NULL THEN 1 ELSE 0 END + CASE WHEN direct_declaration_no IS NOT NULL THEN 1 ELSE 0 END + CASE WHEN document_group_id IS NOT NULL THEN 1 ELSE 0 END) = 1)','DO 0');
PREPARE settlement_repair_stmt FROM @repair_ddl;
EXECUTE settlement_repair_stmt;
DEALLOCATE PREPARE settlement_repair_stmt;

SET @repair_ddl=IF(@repair_enabled AND (NOT EXISTS (SELECT 1 FROM information_schema.statistics WHERE table_schema=DATABASE() AND table_name='settlement_bills' AND index_name='ix_settlement_bill_group')),'CREATE INDEX ix_settlement_bill_group ON settlement_bills (document_group_id, removed_at)','DO 0');
PREPARE settlement_repair_stmt FROM @repair_ddl;
EXECUTE settlement_repair_stmt;
DEALLOCATE PREPARE settlement_repair_stmt;

SET @repair_ddl=IF(@repair_enabled AND (EXISTS (SELECT 1 FROM information_schema.table_constraints WHERE table_schema=DATABASE() AND table_name='settlement_contracts' AND constraint_name='ck_settlement_contract_source') AND NOT EXISTS (SELECT 1 FROM information_schema.table_constraints tc JOIN information_schema.check_constraints cc ON cc.constraint_schema=tc.constraint_schema AND cc.constraint_name=tc.constraint_name WHERE tc.table_schema=DATABASE() AND tc.table_name='settlement_contracts' AND tc.constraint_name='ck_settlement_contract_source' AND tc.constraint_type='CHECK' AND tc.enforced='YES' AND REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(LOWER(cc.check_clause),'`',''),' ',''),'(',''),')',''),CHAR(9),''),CHAR(10),''),CHAR(13),'')='casewhenbatch_idisnotnullthen1else0end+casewhendirect_declaration_noisnotnullthen1else0end+casewhendocument_group_idisnotnullthen1else0end=1')),'ALTER TABLE settlement_contracts DROP CHECK ck_settlement_contract_source','DO 0');
PREPARE settlement_repair_stmt FROM @repair_ddl;
EXECUTE settlement_repair_stmt;
DEALLOCATE PREPARE settlement_repair_stmt;

SET @repair_ddl=IF(@repair_enabled AND (NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='settlement_contracts' AND column_name='document_group_id')),'ALTER TABLE settlement_contracts ADD COLUMN document_group_id BIGINT UNSIGNED COMMENT ''所属直接收汇资料组''','DO 0');
PREPARE settlement_repair_stmt FROM @repair_ddl;
EXECUTE settlement_repair_stmt;
DEALLOCATE PREPARE settlement_repair_stmt;

SET @repair_ddl=IF(@repair_enabled AND (NOT EXISTS (SELECT 1 FROM information_schema.table_constraints WHERE table_schema=DATABASE() AND table_name='settlement_contracts' AND constraint_name='fk_settlement_contract_group')),'ALTER TABLE settlement_contracts ADD CONSTRAINT fk_settlement_contract_group FOREIGN KEY(document_group_id) REFERENCES settlement_document_groups (id)','DO 0');
PREPARE settlement_repair_stmt FROM @repair_ddl;
EXECUTE settlement_repair_stmt;
DEALLOCATE PREPARE settlement_repair_stmt;

SET @repair_ddl=IF(@repair_enabled AND (NOT EXISTS (SELECT 1 FROM information_schema.table_constraints WHERE table_schema=DATABASE() AND table_name='settlement_contracts' AND constraint_name='ck_settlement_contract_source')),'ALTER TABLE settlement_contracts ADD CONSTRAINT ck_settlement_contract_source CHECK ((CASE WHEN batch_id IS NOT NULL THEN 1 ELSE 0 END + CASE WHEN direct_declaration_no IS NOT NULL THEN 1 ELSE 0 END + CASE WHEN document_group_id IS NOT NULL THEN 1 ELSE 0 END) = 1)','DO 0');
PREPARE settlement_repair_stmt FROM @repair_ddl;
EXECUTE settlement_repair_stmt;
DEALLOCATE PREPARE settlement_repair_stmt;

SET @repair_ddl=IF(@repair_enabled AND (NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='settlement_contracts' AND column_name='document_key')),'ALTER TABLE settlement_contracts ADD COLUMN document_key VARCHAR(64) COLLATE utf8mb4_bin','DO 0');
PREPARE settlement_repair_stmt FROM @repair_ddl;
EXECUTE settlement_repair_stmt;
DEALLOCATE PREPARE settlement_repair_stmt;

SET @repair_ddl=IF(@repair_enabled AND (NOT EXISTS (SELECT 1 FROM information_schema.table_constraints WHERE table_schema=DATABASE() AND table_name='settlement_contracts' AND constraint_name='uq_settlement_contract_group_key')),'ALTER TABLE settlement_contracts ADD CONSTRAINT uq_settlement_contract_group_key UNIQUE (document_group_id, document_key)','DO 0');
PREPARE settlement_repair_stmt FROM @repair_ddl;
EXECUTE settlement_repair_stmt;
DEALLOCATE PREPARE settlement_repair_stmt;

SET @repair_ddl=IF(@repair_enabled AND (1),'ALTER TABLE settlement_document_groups COMMENT ''直接收汇资料组，同收货人同币种，可含不同申报抬头''','DO 0');
PREPARE settlement_repair_stmt FROM @repair_ddl;
EXECUTE settlement_repair_stmt;
DEALLOCATE PREPARE settlement_repair_stmt;

SET @repair_ddl=IF(@repair_enabled AND (1),'ALTER TABLE settlement_document_groups MODIFY id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT ''本地自增主键''','DO 0');
PREPARE settlement_repair_stmt FROM @repair_ddl;
EXECUTE settlement_repair_stmt;
DEALLOCATE PREPARE settlement_repair_stmt;

SET @repair_ddl=IF(@repair_enabled AND (1),'ALTER TABLE settlement_document_groups MODIFY group_no VARCHAR(40) COLLATE utf8mb4_bin NOT NULL COMMENT ''资料组编号''','DO 0');
PREPARE settlement_repair_stmt FROM @repair_ddl;
EXECUTE settlement_repair_stmt;
DEALLOCATE PREPARE settlement_repair_stmt;

SET @repair_ddl=IF(@repair_enabled AND (1),'ALTER TABLE settlement_document_groups MODIFY request_id VARCHAR(36) COLLATE utf8mb4_bin NOT NULL COMMENT ''创建幂等请求标识''','DO 0');
PREPARE settlement_repair_stmt FROM @repair_ddl;
EXECUTE settlement_repair_stmt;
DEALLOCATE PREPARE settlement_repair_stmt;

SET @repair_ddl=IF(@repair_enabled AND (1),'ALTER TABLE settlement_document_groups MODIFY consignee VARCHAR(200) NOT NULL COMMENT ''创建时境外收货人''','DO 0');
PREPARE settlement_repair_stmt FROM @repair_ddl;
EXECUTE settlement_repair_stmt;
DEALLOCATE PREPARE settlement_repair_stmt;

SET @repair_ddl=IF(@repair_enabled AND (1),'ALTER TABLE settlement_document_groups MODIFY currency VARCHAR(10) NOT NULL COMMENT ''创建时币种，不跨币种合并''','DO 0');
PREPARE settlement_repair_stmt FROM @repair_ddl;
EXECUTE settlement_repair_stmt;
DEALLOCATE PREPARE settlement_repair_stmt;

SET @repair_ddl=IF(@repair_enabled AND (1),'ALTER TABLE settlement_document_groups MODIFY created_by VARCHAR(190) NOT NULL COMMENT ''创建人，取认证身份''','DO 0');
PREPARE settlement_repair_stmt FROM @repair_ddl;
EXECUTE settlement_repair_stmt;
DEALLOCATE PREPARE settlement_repair_stmt;

SET @repair_ddl=IF(@repair_enabled AND (1),'ALTER TABLE settlement_document_groups CHANGE created_at created_at DATETIME(6) NOT NULL COMMENT ''本地记录创建时间，UTC''','DO 0');
PREPARE settlement_repair_stmt FROM @repair_ddl;
EXECUTE settlement_repair_stmt;
DEALLOCATE PREPARE settlement_repair_stmt;

SET @repair_ddl=IF(@repair_enabled AND (1),'ALTER TABLE settlement_document_groups CHANGE updated_at updated_at DATETIME(6) NOT NULL COMMENT ''本地记录最后更新时间，UTC；由 DAO 更新''','DO 0');
PREPARE settlement_repair_stmt FROM @repair_ddl;
EXECUTE settlement_repair_stmt;
DEALLOCATE PREPARE settlement_repair_stmt;

SET @repair_ddl=IF(@repair_enabled AND (1),'ALTER TABLE settlement_document_group_items COMMENT ''直接收汇资料组成员，一张报关单只属于一组''','DO 0');
PREPARE settlement_repair_stmt FROM @repair_ddl;
EXECUTE settlement_repair_stmt;
DEALLOCATE PREPARE settlement_repair_stmt;

SET @repair_ddl=IF(@repair_enabled AND (1),'ALTER TABLE settlement_document_group_items MODIFY id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT ''本地自增主键''','DO 0');
PREPARE settlement_repair_stmt FROM @repair_ddl;
EXECUTE settlement_repair_stmt;
DEALLOCATE PREPARE settlement_repair_stmt;

SET @repair_ddl=IF(@repair_enabled AND (1),'ALTER TABLE settlement_document_group_items MODIFY group_id BIGINT UNSIGNED NOT NULL COMMENT ''所属直接收汇资料组''','DO 0');
PREPARE settlement_repair_stmt FROM @repair_ddl;
EXECUTE settlement_repair_stmt;
DEALLOCATE PREPARE settlement_repair_stmt;

SET @repair_ddl=IF(@repair_enabled AND (1),'ALTER TABLE settlement_document_group_items MODIFY declaration_no VARCHAR(150) COLLATE utf8mb4_bin NOT NULL COMMENT ''资料组内报关单，一票只能属于一组''','DO 0');
PREPARE settlement_repair_stmt FROM @repair_ddl;
EXECUTE settlement_repair_stmt;
DEALLOCATE PREPARE settlement_repair_stmt;

SET @repair_ddl=IF(@repair_enabled AND (1),'ALTER TABLE settlement_document_group_items CHANGE created_at created_at DATETIME(6) NOT NULL COMMENT ''成员归组时间，UTC''','DO 0');
PREPARE settlement_repair_stmt FROM @repair_ddl;
EXECUTE settlement_repair_stmt;
DEALLOCATE PREPARE settlement_repair_stmt;

SET @repair_ddl=IF(@repair_enabled AND (1),'ALTER TABLE settlement_contracts MODIFY document_key VARCHAR(64) COLLATE utf8mb4_bin NULL COMMENT ''资料组内申报抬头与出口合同号的稳定标识''','DO 0');
PREPARE settlement_repair_stmt FROM @repair_ddl;
EXECUTE settlement_repair_stmt;
DEALLOCATE PREPARE settlement_repair_stmt;

SET @repair_ddl=IF(@repair_enabled AND (NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='settlement_document_groups' AND column_name='initial_declaration_nos')),'ALTER TABLE settlement_document_groups ADD COLUMN initial_declaration_nos JSON COMMENT ''创建时成员快照，合并后仍保留原始范围''','DO 0');
PREPARE settlement_repair_stmt FROM @repair_ddl;
EXECUTE settlement_repair_stmt;
DEALLOCATE PREPARE settlement_repair_stmt;

SET @repair_ddl=IF(@repair_enabled AND (NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='settlement_document_groups' AND column_name='merged_into_id')),'ALTER TABLE settlement_document_groups ADD COLUMN merged_into_id BIGINT UNSIGNED COMMENT ''合并后的新资料组，原组保留供追溯''','DO 0');
PREPARE settlement_repair_stmt FROM @repair_ddl;
EXECUTE settlement_repair_stmt;
DEALLOCATE PREPARE settlement_repair_stmt;

SET @repair_ddl=IF(@repair_enabled AND (NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='settlement_document_groups' AND column_name='merged_at')),'ALTER TABLE settlement_document_groups ADD COLUMN merged_at DATETIME(6) COMMENT ''合并时间，UTC''','DO 0');
PREPARE settlement_repair_stmt FROM @repair_ddl;
EXECUTE settlement_repair_stmt;
DEALLOCATE PREPARE settlement_repair_stmt;

SET @repair_ddl=IF(@repair_enabled AND (NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='settlement_document_groups' AND column_name='merged_by')),'ALTER TABLE settlement_document_groups ADD COLUMN merged_by VARCHAR(190) COMMENT ''合并操作人，取认证身份''','DO 0');
PREPARE settlement_repair_stmt FROM @repair_ddl;
EXECUTE settlement_repair_stmt;
DEALLOCATE PREPARE settlement_repair_stmt;

SET @repair_ddl=IF(@repair_enabled AND (NOT EXISTS (SELECT 1 FROM information_schema.table_constraints WHERE table_schema=DATABASE() AND table_name='settlement_document_groups' AND constraint_name='fk_settlement_document_group_successor')),'ALTER TABLE settlement_document_groups ADD CONSTRAINT fk_settlement_document_group_successor FOREIGN KEY(merged_into_id) REFERENCES settlement_document_groups (id)','DO 0');
PREPARE settlement_repair_stmt FROM @repair_ddl;
EXECUTE settlement_repair_stmt;
DEALLOCATE PREPARE settlement_repair_stmt;

SET @repair_ddl=IF(@repair_enabled AND (NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name='settlement_hk_slips')),'CREATE TABLE settlement_hk_slips (
    batch_id BIGINT UNSIGNED NOT NULL COMMENT ''所属香港批次主键，一批次一份水单'',
    file_name VARCHAR(255) NOT NULL COMMENT ''银行水单原始文件名'',
    file_id VARCHAR(36) COLLATE utf8mb4_bin NOT NULL COMMENT ''资料目录内服务端生成的 PDF 文件标识'',
    sha256 VARCHAR(64) COLLATE utf8mb4_bin NOT NULL COMMENT ''原件 SHA-256 校验值'',
    uploaded_by VARCHAR(190) NOT NULL COMMENT ''登记操作人，来自认证身份'',
    created_at DATETIME(6) NOT NULL COMMENT ''本地记录创建时间，UTC'' DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL COMMENT ''本地记录最后更新时间，UTC；由 DAO 更新'' DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (batch_id),
    FOREIGN KEY(batch_id) REFERENCES settlement_batches (id)
)ENGINE=InnoDB COMMENT=''香港到账银行水单原件，随批次留存不写 NS'' CHARSET=utf8mb4 COLLATE utf8mb4_bin','DO 0');
PREPARE settlement_repair_stmt FROM @repair_ddl;
EXECUTE settlement_repair_stmt;
DEALLOCATE PREPARE settlement_repair_stmt;

SET @repair_ddl=IF(@repair_enabled AND (NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='settlement_document_groups' AND column_name='basis_history')),'ALTER TABLE settlement_document_groups ADD COLUMN basis_history JSON COMMENT ''人工确认更新来源的前后依据、时间和认证操作者''','DO 0');
PREPARE settlement_repair_stmt FROM @repair_ddl;
EXECUTE settlement_repair_stmt;
DEALLOCATE PREPARE settlement_repair_stmt;

-- basis_history 已存在时只补充备注，保留 JSON 内容。

SET @repair_ddl=IF(@repair_enabled AND (1),'ALTER TABLE settlement_document_groups MODIFY basis_history JSON NULL COMMENT ''人工确认更新来源的前后依据、时间和认证操作者''','DO 0');
PREPARE settlement_repair_stmt FROM @repair_ddl;
EXECUTE settlement_repair_stmt;
DEALLOCATE PREPARE settlement_repair_stmt;

SET @repair_ddl=IF(@repair_enabled AND (NOT EXISTS (SELECT 1 FROM information_schema.key_column_usage WHERE table_schema=DATABASE() AND table_name='settlement_document_group_items' AND column_name='group_id' AND referenced_table_schema=DATABASE() AND referenced_table_name='settlement_document_groups' AND referenced_column_name='id')),'ALTER TABLE settlement_document_group_items ADD CONSTRAINT fk_settlement_document_group_item_group FOREIGN KEY(group_id) REFERENCES settlement_document_groups (id)','DO 0');
PREPARE settlement_repair_stmt FROM @repair_ddl;
EXECUTE settlement_repair_stmt;
DEALLOCATE PREPARE settlement_repair_stmt;

-- 会话临时表只保存结构核验结果，不存放业务记录。
DROP TEMPORARY TABLE IF EXISTS tmp_settlement_repair_checks_0055;
CREATE TEMPORARY TABLE tmp_settlement_repair_checks_0055 AS

SELECT 'settlement_document_groups:table' AS check_name, (EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name='settlement_document_groups' AND engine='InnoDB' AND table_collation='utf8mb4_bin' AND table_comment='直接收汇资料组，同收货人同币种，可含不同申报抬头')) AS passed
UNION ALL
SELECT 'settlement_document_groups.id' AS check_name, (EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='settlement_document_groups' AND column_name='id' AND data_type='bigint' AND is_nullable='NO' AND column_comment='本地自增主键' AND column_type LIKE '%unsigned%' AND extra LIKE '%auto_increment%')) AS passed
UNION ALL
SELECT 'settlement_document_groups.group_no' AS check_name, (EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='settlement_document_groups' AND column_name='group_no' AND data_type='varchar' AND is_nullable='NO' AND column_comment='资料组编号' AND character_maximum_length=40 AND collation_name='utf8mb4_bin')) AS passed
UNION ALL
SELECT 'settlement_document_groups.request_id' AS check_name, (EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='settlement_document_groups' AND column_name='request_id' AND data_type='varchar' AND is_nullable='NO' AND column_comment='创建幂等请求标识' AND character_maximum_length=36 AND collation_name='utf8mb4_bin')) AS passed
UNION ALL
SELECT 'settlement_document_groups.consignee' AS check_name, (EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='settlement_document_groups' AND column_name='consignee' AND data_type='varchar' AND is_nullable='NO' AND column_comment='创建时境外收货人' AND character_maximum_length=200 AND collation_name='utf8mb4_bin')) AS passed
UNION ALL
SELECT 'settlement_document_groups.currency' AS check_name, (EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='settlement_document_groups' AND column_name='currency' AND data_type='varchar' AND is_nullable='NO' AND column_comment='创建时币种，不跨币种合并' AND character_maximum_length=10 AND collation_name='utf8mb4_bin')) AS passed
UNION ALL
SELECT 'settlement_document_groups.created_by' AS check_name, (EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='settlement_document_groups' AND column_name='created_by' AND data_type='varchar' AND is_nullable='NO' AND column_comment='创建人，取认证身份' AND character_maximum_length=190 AND collation_name='utf8mb4_bin')) AS passed
UNION ALL
SELECT 'settlement_document_groups.initial_declaration_nos' AS check_name, (EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='settlement_document_groups' AND column_name='initial_declaration_nos' AND data_type='json' AND is_nullable='YES' AND column_comment='创建时成员快照，合并后仍保留原始范围')) AS passed
UNION ALL
SELECT 'settlement_document_groups.merged_into_id' AS check_name, (EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='settlement_document_groups' AND column_name='merged_into_id' AND data_type='bigint' AND is_nullable='YES' AND column_comment='合并后的新资料组，原组保留供追溯' AND column_type LIKE '%unsigned%')) AS passed
UNION ALL
SELECT 'settlement_document_groups.merged_at' AS check_name, (EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='settlement_document_groups' AND column_name='merged_at' AND data_type='datetime' AND is_nullable='YES' AND column_comment='合并时间，UTC' AND datetime_precision=6)) AS passed
UNION ALL
SELECT 'settlement_document_groups.merged_by' AS check_name, (EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='settlement_document_groups' AND column_name='merged_by' AND data_type='varchar' AND is_nullable='YES' AND column_comment='合并操作人，取认证身份' AND character_maximum_length=190 AND collation_name='utf8mb4_bin')) AS passed
UNION ALL
SELECT 'settlement_document_groups.basis_history' AS check_name, (EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='settlement_document_groups' AND column_name='basis_history' AND data_type='json' AND is_nullable='YES' AND column_comment='人工确认更新来源的前后依据、时间和认证操作者')) AS passed
UNION ALL
SELECT 'settlement_document_groups.created_at' AS check_name, (EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='settlement_document_groups' AND column_name='created_at' AND data_type='datetime' AND is_nullable='NO' AND column_comment='本地记录创建时间，UTC' AND datetime_precision=6)) AS passed
UNION ALL
SELECT 'settlement_document_groups.updated_at' AS check_name, (EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='settlement_document_groups' AND column_name='updated_at' AND data_type='datetime' AND is_nullable='NO' AND column_comment='本地记录最后更新时间，UTC；由 DAO 更新' AND datetime_precision=6)) AS passed
UNION ALL
SELECT 'settlement_document_group_items:table' AS check_name, (EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name='settlement_document_group_items' AND engine='InnoDB' AND table_collation='utf8mb4_bin' AND table_comment='直接收汇资料组成员，一张报关单只属于一组')) AS passed
UNION ALL
SELECT 'settlement_document_group_items.id' AS check_name, (EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='settlement_document_group_items' AND column_name='id' AND data_type='bigint' AND is_nullable='NO' AND column_comment='本地自增主键' AND column_type LIKE '%unsigned%' AND extra LIKE '%auto_increment%')) AS passed
UNION ALL
SELECT 'settlement_document_group_items.group_id' AS check_name, (EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='settlement_document_group_items' AND column_name='group_id' AND data_type='bigint' AND is_nullable='NO' AND column_comment='所属直接收汇资料组' AND column_type LIKE '%unsigned%')) AS passed
UNION ALL
SELECT 'settlement_document_group_items.declaration_no' AS check_name, (EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='settlement_document_group_items' AND column_name='declaration_no' AND data_type='varchar' AND is_nullable='NO' AND column_comment='资料组内报关单，一票只能属于一组' AND character_maximum_length=150 AND collation_name='utf8mb4_bin')) AS passed
UNION ALL
SELECT 'settlement_document_group_items.created_at' AS check_name, (EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='settlement_document_group_items' AND column_name='created_at' AND data_type='datetime' AND is_nullable='NO' AND column_comment='成员归组时间，UTC' AND datetime_precision=6)) AS passed
UNION ALL
SELECT 'settlement_hk_slips:table' AS check_name, (EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name='settlement_hk_slips' AND engine='InnoDB' AND table_collation='utf8mb4_bin' AND table_comment='香港到账银行水单原件，随批次留存不写 NS')) AS passed
UNION ALL
SELECT 'settlement_hk_slips.batch_id' AS check_name, (EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='settlement_hk_slips' AND column_name='batch_id' AND data_type='bigint' AND is_nullable='NO' AND column_comment='所属香港批次主键，一批次一份水单' AND column_type LIKE '%unsigned%')) AS passed
UNION ALL
SELECT 'settlement_hk_slips.file_name' AS check_name, (EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='settlement_hk_slips' AND column_name='file_name' AND data_type='varchar' AND is_nullable='NO' AND column_comment='银行水单原始文件名' AND character_maximum_length=255 AND collation_name='utf8mb4_bin')) AS passed
UNION ALL
SELECT 'settlement_hk_slips.file_id' AS check_name, (EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='settlement_hk_slips' AND column_name='file_id' AND data_type='varchar' AND is_nullable='NO' AND column_comment='资料目录内服务端生成的 PDF 文件标识' AND character_maximum_length=36 AND collation_name='utf8mb4_bin')) AS passed
UNION ALL
SELECT 'settlement_hk_slips.sha256' AS check_name, (EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='settlement_hk_slips' AND column_name='sha256' AND data_type='varchar' AND is_nullable='NO' AND column_comment='原件 SHA-256 校验值' AND character_maximum_length=64 AND collation_name='utf8mb4_bin')) AS passed
UNION ALL
SELECT 'settlement_hk_slips.uploaded_by' AS check_name, (EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='settlement_hk_slips' AND column_name='uploaded_by' AND data_type='varchar' AND is_nullable='NO' AND column_comment='登记操作人，来自认证身份' AND character_maximum_length=190 AND collation_name='utf8mb4_bin')) AS passed
UNION ALL
SELECT 'settlement_hk_slips.created_at' AS check_name, (EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='settlement_hk_slips' AND column_name='created_at' AND data_type='datetime' AND is_nullable='NO' AND column_comment='本地记录创建时间，UTC' AND datetime_precision=6 AND LOWER(column_default)='current_timestamp(6)')) AS passed
UNION ALL
SELECT 'settlement_hk_slips.updated_at' AS check_name, (EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='settlement_hk_slips' AND column_name='updated_at' AND data_type='datetime' AND is_nullable='NO' AND column_comment='本地记录最后更新时间，UTC；由 DAO 更新' AND datetime_precision=6 AND LOWER(column_default)='current_timestamp(6)')) AS passed
UNION ALL
SELECT 'settlement_bills.batch_id' AS check_name, (EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='settlement_bills' AND column_name='batch_id' AND is_nullable='YES' AND data_type='bigint' AND column_type LIKE '%unsigned%')) AS passed
UNION ALL
SELECT 'settlement_bills.direct_declaration_no' AS check_name, (EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='settlement_bills' AND column_name='direct_declaration_no' AND is_nullable='YES' AND data_type='varchar' AND character_maximum_length=150 AND collation_name='utf8mb4_bin')) AS passed
UNION ALL
SELECT 'settlement_bills.document_group_id' AS check_name, (EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='settlement_bills' AND column_name='document_group_id' AND is_nullable='YES' AND data_type='bigint' AND column_type LIKE '%unsigned%' AND column_comment='所属直接收汇资料组')) AS passed
UNION ALL
SELECT 'settlement_bills:check' AS check_name, (EXISTS (SELECT 1 FROM information_schema.table_constraints tc JOIN information_schema.check_constraints cc ON cc.constraint_schema=tc.constraint_schema AND cc.constraint_name=tc.constraint_name WHERE tc.table_schema=DATABASE() AND tc.table_name='settlement_bills' AND tc.constraint_name='ck_settlement_bill_source' AND tc.constraint_type='CHECK' AND tc.enforced='YES' AND REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(LOWER(cc.check_clause),'`',''),' ',''),'(',''),')',''),CHAR(9),''),CHAR(10),''),CHAR(13),'')='casewhenbatch_idisnotnullthen1else0end+casewhendirect_declaration_noisnotnullthen1else0end+casewhendocument_group_idisnotnullthen1else0end=1')) AS passed
UNION ALL
SELECT 'settlement_bills:foreign_key' AS check_name, (EXISTS (SELECT 1 FROM information_schema.key_column_usage WHERE table_schema=DATABASE() AND table_name='settlement_bills' AND column_name='document_group_id' AND referenced_table_schema=DATABASE() AND referenced_table_name='settlement_document_groups' AND referenced_column_name='id')) AS passed
UNION ALL
SELECT 'settlement_contracts.batch_id' AS check_name, (EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='settlement_contracts' AND column_name='batch_id' AND is_nullable='YES' AND data_type='bigint' AND column_type LIKE '%unsigned%')) AS passed
UNION ALL
SELECT 'settlement_contracts.direct_declaration_no' AS check_name, (EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='settlement_contracts' AND column_name='direct_declaration_no' AND is_nullable='YES' AND data_type='varchar' AND character_maximum_length=150 AND collation_name='utf8mb4_bin')) AS passed
UNION ALL
SELECT 'settlement_contracts.document_group_id' AS check_name, (EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='settlement_contracts' AND column_name='document_group_id' AND is_nullable='YES' AND data_type='bigint' AND column_type LIKE '%unsigned%' AND column_comment='所属直接收汇资料组')) AS passed
UNION ALL
SELECT 'settlement_contracts.document_key' AS check_name, (EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='settlement_contracts' AND column_name='document_key' AND is_nullable='YES' AND data_type='varchar' AND character_maximum_length=64 AND collation_name='utf8mb4_bin' AND column_comment='资料组内申报抬头与出口合同号的稳定标识')) AS passed
UNION ALL
SELECT 'settlement_contracts:check' AS check_name, (EXISTS (SELECT 1 FROM information_schema.table_constraints tc JOIN information_schema.check_constraints cc ON cc.constraint_schema=tc.constraint_schema AND cc.constraint_name=tc.constraint_name WHERE tc.table_schema=DATABASE() AND tc.table_name='settlement_contracts' AND tc.constraint_name='ck_settlement_contract_source' AND tc.constraint_type='CHECK' AND tc.enforced='YES' AND REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(LOWER(cc.check_clause),'`',''),' ',''),'(',''),')',''),CHAR(9),''),CHAR(10),''),CHAR(13),'')='casewhenbatch_idisnotnullthen1else0end+casewhendirect_declaration_noisnotnullthen1else0end+casewhendocument_group_idisnotnullthen1else0end=1')) AS passed
UNION ALL
SELECT 'settlement_contracts:foreign_key' AS check_name, (EXISTS (SELECT 1 FROM information_schema.key_column_usage WHERE table_schema=DATABASE() AND table_name='settlement_contracts' AND column_name='document_group_id' AND referenced_table_schema=DATABASE() AND referenced_table_name='settlement_document_groups' AND referenced_column_name='id')) AS passed
UNION ALL
SELECT 'settlement_document_group_items:foreign_key' AS check_name, (EXISTS (SELECT 1 FROM information_schema.key_column_usage WHERE table_schema=DATABASE() AND table_name='settlement_document_group_items' AND column_name='group_id' AND referenced_table_schema=DATABASE() AND referenced_table_name='settlement_document_groups' AND referenced_column_name='id')) AS passed
UNION ALL
SELECT 'settlement_document_groups:foreign_key' AS check_name, (EXISTS (SELECT 1 FROM information_schema.key_column_usage WHERE table_schema=DATABASE() AND table_name='settlement_document_groups' AND column_name='merged_into_id' AND referenced_table_schema=DATABASE() AND referenced_table_name='settlement_document_groups' AND referenced_column_name='id')) AS passed
UNION ALL
SELECT 'settlement_hk_slips:foreign_key' AS check_name, (EXISTS (SELECT 1 FROM information_schema.key_column_usage WHERE table_schema=DATABASE() AND table_name='settlement_hk_slips' AND column_name='batch_id' AND referenced_table_schema=DATABASE() AND referenced_table_name='settlement_batches' AND referenced_column_name='id')) AS passed
UNION ALL
SELECT 'settlement_document_groups:index:id' AS check_name, (EXISTS (SELECT 1 FROM information_schema.statistics WHERE table_schema=DATABASE() AND table_name='settlement_document_groups' AND index_name='PRIMARY' GROUP BY index_name HAVING GROUP_CONCAT(column_name ORDER BY seq_in_index SEPARATOR ',')='id' AND SUM(sub_part IS NOT NULL)=0 AND MAX(non_unique)=0)) AS passed
UNION ALL
SELECT 'settlement_document_groups:index:group_no' AS check_name, (EXISTS (SELECT 1 FROM information_schema.statistics WHERE table_schema=DATABASE() AND table_name='settlement_document_groups' GROUP BY index_name HAVING GROUP_CONCAT(column_name ORDER BY seq_in_index SEPARATOR ',')='group_no' AND SUM(sub_part IS NOT NULL)=0 AND MAX(non_unique)=0)) AS passed
UNION ALL
SELECT 'settlement_document_groups:index:request_id' AS check_name, (EXISTS (SELECT 1 FROM information_schema.statistics WHERE table_schema=DATABASE() AND table_name='settlement_document_groups' GROUP BY index_name HAVING GROUP_CONCAT(column_name ORDER BY seq_in_index SEPARATOR ',')='request_id' AND SUM(sub_part IS NOT NULL)=0 AND MAX(non_unique)=0)) AS passed
UNION ALL
SELECT 'settlement_document_group_items:index:id' AS check_name, (EXISTS (SELECT 1 FROM information_schema.statistics WHERE table_schema=DATABASE() AND table_name='settlement_document_group_items' AND index_name='PRIMARY' GROUP BY index_name HAVING GROUP_CONCAT(column_name ORDER BY seq_in_index SEPARATOR ',')='id' AND SUM(sub_part IS NOT NULL)=0 AND MAX(non_unique)=0)) AS passed
UNION ALL
SELECT 'settlement_document_group_items:index:declaration_no' AS check_name, (EXISTS (SELECT 1 FROM information_schema.statistics WHERE table_schema=DATABASE() AND table_name='settlement_document_group_items' AND index_name='uq_settlement_document_group_declaration' GROUP BY index_name HAVING GROUP_CONCAT(column_name ORDER BY seq_in_index SEPARATOR ',')='declaration_no' AND SUM(sub_part IS NOT NULL)=0 AND MAX(non_unique)=0)) AS passed
UNION ALL
SELECT 'settlement_bills:index:document_group_id,removed_at' AS check_name, (EXISTS (SELECT 1 FROM information_schema.statistics WHERE table_schema=DATABASE() AND table_name='settlement_bills' AND index_name='ix_settlement_bill_group' GROUP BY index_name HAVING GROUP_CONCAT(column_name ORDER BY seq_in_index SEPARATOR ',')='document_group_id,removed_at' AND SUM(sub_part IS NOT NULL)=0)) AS passed
UNION ALL
SELECT 'settlement_contracts:index:batch_id,contract_no' AS check_name, (EXISTS (SELECT 1 FROM information_schema.statistics WHERE table_schema=DATABASE() AND table_name='settlement_contracts' AND index_name='uq_settlement_contract_batch_no' GROUP BY index_name HAVING GROUP_CONCAT(column_name ORDER BY seq_in_index SEPARATOR ',')='batch_id,contract_no' AND SUM(sub_part IS NOT NULL)=0 AND MAX(non_unique)=0)) AS passed
UNION ALL
SELECT 'settlement_contracts:index:direct_declaration_no,contract_no' AS check_name, (EXISTS (SELECT 1 FROM information_schema.statistics WHERE table_schema=DATABASE() AND table_name='settlement_contracts' AND index_name='uq_settlement_contract_direct_no' GROUP BY index_name HAVING GROUP_CONCAT(column_name ORDER BY seq_in_index SEPARATOR ',')='direct_declaration_no,contract_no' AND SUM(sub_part IS NOT NULL)=0 AND MAX(non_unique)=0)) AS passed
UNION ALL
SELECT 'settlement_contracts:index:document_group_id,document_key' AS check_name, (EXISTS (SELECT 1 FROM information_schema.statistics WHERE table_schema=DATABASE() AND table_name='settlement_contracts' AND index_name='uq_settlement_contract_group_key' GROUP BY index_name HAVING GROUP_CONCAT(column_name ORDER BY seq_in_index SEPARATOR ',')='document_group_id,document_key' AND SUM(sub_part IS NOT NULL)=0 AND MAX(non_unique)=0)) AS passed
UNION ALL
SELECT 'settlement_hk_slips:index:batch_id' AS check_name, (EXISTS (SELECT 1 FROM information_schema.statistics WHERE table_schema=DATABASE() AND table_name='settlement_hk_slips' AND index_name='PRIMARY' GROUP BY index_name HAVING GROUP_CONCAT(column_name ORDER BY seq_in_index SEPARATOR ',')='batch_id' AND SUM(sub_part IS NOT NULL)=0 AND MAX(non_unique)=0)) AS passed;


SET @repair_failed=(SELECT COUNT(*) FROM tmp_settlement_repair_checks_0055 WHERE passed IS NULL OR passed<>1);
SELECT check_name AS failed_check FROM tmp_settlement_repair_checks_0055 WHERE passed IS NULL OR passed<>1;
-- 全部结构核验通过且前置版本正确，才登记为镜像要求的版本。
UPDATE schema_version SET version_num='0055_settlement_group_basis'
WHERE version_num=@repair_version_before AND @repair_enabled=1 AND @repair_failed=0;
SET @repair_updated=ROW_COUNT();
COMMIT;
DROP TEMPORARY TABLE tmp_settlement_repair_checks_0055;
DO RELEASE_LOCK(@repair_lock_name);
-- 请查看这个最终结果，不要把第一个结果中的旧版本当成最终状态。
SELECT DATABASE() AS database_FINAL, (SELECT MIN(version_num) FROM schema_version) AS version_FINAL,
  @repair_failed AS failed_checks,
  CASE WHEN @repair_updated=1 AND @repair_failed=0 THEN '修复完成，可以启动应用'
       WHEN @repair_version_before='0055_settlement_group_basis' AND @repair_failed=0 THEN '结构已完整，版本已是0055'
       WHEN @repair_enabled<>1 OR @repair_enabled IS NULL THEN '未更新版本：前置版本、迁移锁、MySQL版本或自动提交条件不满足'
       ELSE '未更新版本：结构核验未通过，请提供 failed_check 结果' END AS result_FINAL;

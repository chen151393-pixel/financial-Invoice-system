-- 结汇模块 MySQL 8 手动增量升级：0051 ～ 0055
-- 由本仓库 Alembic 迁移离线生成 DDL，再包装版本检查与迁移互斥锁。
-- 适用：目标库已完整执行到 0050、0051、0052、0053 或 0054；0055 会直接跳过。
-- 低于 0050、超过 0055、版本记录异常时拒绝执行。已有部分失败的迁移应先核对结构。
-- 执行前：备份目标库；选择正确的业务库，在独立查询窗口执行整个脚本。
-- 请勿在有未提交业务操作的窗口运行；不要只选中中间一段执行。
-- 需 MySQL 8.0.16+（也支持 MySQL 8.4），不适用于 SQLite 或 MariaDB。
-- 需 CREATE ROUTINE / ALTER ROUTINE / EXECUTE 及相关表的 CREATE / ALTER / INDEX / REFERENCES 权限。
-- MySQL DDL 会自动提交，中途失败不能整体回滚；脚本只在每个完整迁移成功后推进版本。
-- 不删除业务记录，不修改应收或到账金额，不写 NS，不执行历史资料组合并。
-- 没有固定 USE 某个库，避免误选环境；请先在客户端选中目标业务库。

SET NAMES utf8mb4 COLLATE utf8mb4_bin;
SELECT DATABASE() AS target_database, VERSION() AS mysql_version;

DELIMITER $$
DROP PROCEDURE IF EXISTS codex_settlement_upgrade_0051_0055$$
CREATE PROCEDURE codex_settlement_upgrade_0051_0055()
BEGIN
    DECLARE v_version VARCHAR(64);
    DECLARE v_count INT DEFAULT 0;
    DECLARE v_lock_name VARCHAR(64);
    DECLARE v_lock_held INT DEFAULT 0;
    DECLARE v_release_result INT;
    DECLARE v_major INT;
    DECLARE v_minor INT;
    DECLARE v_patch INT;
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        IF v_lock_held = 1 THEN
            SELECT RELEASE_LOCK(v_lock_name) INTO v_release_result;
        END IF;
        RESIGNAL;
    END;

    IF DATABASE() IS NULL THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Select the target business database first';
    END IF;
    SET v_major = CAST(SUBSTRING_INDEX(VERSION(), '.', 1) AS UNSIGNED);
    SET v_minor = CAST(SUBSTRING_INDEX(SUBSTRING_INDEX(VERSION(), '.', 2), '.', -1) AS UNSIGNED);
    SET v_patch = CAST(SUBSTRING_INDEX(SUBSTRING_INDEX(VERSION(), '.', 3), '.', -1) AS UNSIGNED);
    IF LOCATE('MariaDB', VERSION()) > 0 OR v_major <> 8
       OR (v_minor = 0 AND v_patch < 16) THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Requires MySQL 8.0.16+ or MySQL 8.4';
    END IF;
    IF @@SESSION.autocommit <> 1 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Run in a fresh query session with autocommit=1';
    END IF;

    -- 与 Alembic 在线迁移使用同一把库级互斥锁。
    SET v_lock_name = SHA2(CONCAT('schema:', DATABASE()), 256);
    SELECT GET_LOCK(v_lock_name, 0) INTO v_lock_held;
    IF v_lock_held IS NULL OR v_lock_held <> 1 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Another schema migration is running; stop and retry later';
    END IF;
    SELECT COUNT(*) INTO v_count
      FROM information_schema.tables
     WHERE table_schema = DATABASE() AND table_name = 'schema_version';
    IF v_count <> 1 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Missing schema_version; initialize with the full migration chain first';
    END IF;
    SELECT COUNT(*), MAX(version_num) INTO v_count, v_version FROM schema_version;
    IF v_count <> 1 OR v_version IS NULL OR v_version NOT IN (
        '0050_settlement_direct_documents',
        '0051_settlement_document_groups',
        '0052_settlement_group_comments',
        '0053_settlement_group_merge',
        '0054_settlement_hk_slips',
        '0055_settlement_group_basis'
    ) THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Unexpected schema version; supported starting versions are 0050 through 0055';
    END IF;
    SELECT v_version AS starting_version;

    -- 0051_settlement_document_groups：直接收汇资料组及提单／合同的资料组归属。
    IF v_version = '0050_settlement_direct_documents' THEN
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
        )CHARSET=utf8mb4 ENGINE=InnoDB COLLATE utf8mb4_bin;

        CREATE TABLE settlement_document_group_items (
            id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
            group_id BIGINT UNSIGNED NOT NULL,
            declaration_no VARCHAR(150) COLLATE utf8mb4_bin NOT NULL,
            created_at DATETIME(6) NOT NULL,
            PRIMARY KEY (id),
            CONSTRAINT uq_settlement_document_group_declaration UNIQUE (declaration_no),
            FOREIGN KEY(group_id) REFERENCES settlement_document_groups (id)
        )CHARSET=utf8mb4 ENGINE=InnoDB COLLATE utf8mb4_bin;

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
        IF ROW_COUNT() <> 1 THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Failed to advance schema_version to 0051_settlement_document_groups';
        END IF;
        COMMIT;
        SET v_version = '0051_settlement_document_groups';
    END IF;

    -- 0052_settlement_group_comments：资料组表与字段中文备注。
    IF v_version = '0051_settlement_document_groups' THEN
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
        IF ROW_COUNT() <> 1 THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Failed to advance schema_version to 0052_settlement_group_comments';
        END IF;
        COMMIT;
        SET v_version = '0052_settlement_group_comments';
    END IF;

    -- 0053_settlement_group_merge：资料组合并后的后继关系与原始成员范围。
    IF v_version = '0052_settlement_group_comments' THEN
        ALTER TABLE settlement_document_groups ADD COLUMN initial_declaration_nos JSON COMMENT '创建时成员快照，合并后仍保留原始范围';

        ALTER TABLE settlement_document_groups ADD COLUMN merged_into_id BIGINT UNSIGNED COMMENT '合并后的新资料组，原组保留供追溯';

        ALTER TABLE settlement_document_groups ADD COLUMN merged_at DATETIME(6) COMMENT '合并时间，UTC';

        ALTER TABLE settlement_document_groups ADD COLUMN merged_by VARCHAR(190) COMMENT '合并操作人，取认证身份';

        ALTER TABLE settlement_document_groups ADD CONSTRAINT fk_settlement_document_group_successor FOREIGN KEY(merged_into_id) REFERENCES settlement_document_groups (id);

        UPDATE schema_version SET version_num='0053_settlement_group_merge' WHERE schema_version.version_num = '0052_settlement_group_comments';
        IF ROW_COUNT() <> 1 THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Failed to advance schema_version to 0053_settlement_group_merge';
        END IF;
        COMMIT;
        SET v_version = '0053_settlement_group_merge';
    END IF;

    -- 0054_settlement_hk_slips：香港批次银行水单原件索引。
    IF v_version = '0053_settlement_group_merge' THEN
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
        )CHARSET=utf8mb4 ENGINE=InnoDB COMMENT='香港到账银行水单原件，随批次留存不写 NS' COLLATE utf8mb4_bin;

        UPDATE schema_version SET version_num='0054_settlement_hk_slips' WHERE schema_version.version_num = '0053_settlement_group_merge';
        IF ROW_COUNT() <> 1 THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Failed to advance schema_version to 0054_settlement_hk_slips';
        END IF;
        COMMIT;
        SET v_version = '0054_settlement_hk_slips';
    END IF;

    -- 0055_settlement_group_basis：资料组人工更新来源的审计记录。
    IF v_version = '0054_settlement_hk_slips' THEN
        ALTER TABLE settlement_document_groups ADD COLUMN basis_history JSON COMMENT '人工确认更新来源的前后依据、时间和认证操作者';

        UPDATE schema_version SET version_num='0055_settlement_group_basis' WHERE schema_version.version_num = '0054_settlement_hk_slips';
        IF ROW_COUNT() <> 1 THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Failed to advance schema_version to 0055_settlement_group_basis';
        END IF;
        COMMIT;
        SET v_version = '0055_settlement_group_basis';
    END IF;

    SELECT COUNT(*) INTO v_count FROM schema_version
     WHERE version_num = '0055_settlement_group_basis';
    IF v_count <> 1 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Schema version verification failed';
    END IF;
    COMMIT;
    SELECT RELEASE_LOCK(v_lock_name) INTO v_release_result;
    SET v_lock_held = 0;
    SELECT v_version AS final_version, 'Upgrade complete or already at 0055' AS result;
END$$
CALL codex_settlement_upgrade_0051_0055()$$
DROP PROCEDURE codex_settlement_upgrade_0051_0055$$
DELIMITER ;

-- 结果检查：版本应为 0055_settlement_group_basis；下面应列出三张新表。
SELECT version_num FROM schema_version;
SELECT table_name, table_comment
  FROM information_schema.tables
 WHERE table_schema = DATABASE()
   AND table_name IN (
       'settlement_document_groups',
       'settlement_document_group_items',
       'settlement_hk_slips'
   )
 ORDER BY table_name;

-- 补齐缺失前置迁移：0049 -> 0050（MySQL 8.0.16+）
-- 已根据目标库截图确认：提单与合同的 batch_id 仍为 NOT NULL，且无 direct_declaration_no。
-- 先备份并选中同一个目标业务库；本文件只执行一次，遇错立即停止。
-- 单独执行下面两条查询，确认版本仍为 0049 且字段状态与截图一致，再执行后面的升级段。
-- 不删除已有报关单、提单、合同或资料组，不修改金额。
-- 本段只升到 0050，不处理先前 0051～0055 已部分创建的结构。
-- 成功后应返回 0050_settlement_direct_documents；不要直接重跑旧 0051～0055 全文件。

SELECT DATABASE() AS target_database, version_num FROM schema_version;
SELECT table_name, column_name, column_type, is_nullable
FROM information_schema.columns
WHERE table_schema = DATABASE()
  AND table_name IN ('settlement_bills', 'settlement_contracts')
  AND column_name IN ('batch_id', 'direct_declaration_no')
ORDER BY table_name, column_name;

SET NAMES utf8mb4 COLLATE utf8mb4_bin;

-- Running upgrade 0049_settlement_direct_allocations -> 0050_settlement_direct_documents

ALTER TABLE settlement_bills MODIFY batch_id BIGINT UNSIGNED NULL;

ALTER TABLE settlement_bills ADD COLUMN direct_declaration_no VARCHAR(150) COLLATE utf8mb4_bin COMMENT '直接收汇资料所属报关单；与批次二选一';

ALTER TABLE settlement_bills ADD CONSTRAINT ck_settlement_bill_source CHECK ((batch_id IS NOT NULL AND direct_declaration_no IS NULL) OR (batch_id IS NULL AND direct_declaration_no IS NOT NULL));

CREATE INDEX ix_settlement_bill_direct ON settlement_bills (direct_declaration_no, removed_at);

ALTER TABLE settlement_contracts MODIFY batch_id BIGINT UNSIGNED NULL;

ALTER TABLE settlement_contracts ADD COLUMN direct_declaration_no VARCHAR(150) COLLATE utf8mb4_bin COMMENT '直接收汇资料所属报关单；与批次二选一';

ALTER TABLE settlement_contracts ADD CONSTRAINT ck_settlement_contract_source CHECK ((batch_id IS NOT NULL AND direct_declaration_no IS NULL) OR (batch_id IS NULL AND direct_declaration_no IS NOT NULL));

ALTER TABLE settlement_contracts ADD CONSTRAINT uq_settlement_contract_direct_no UNIQUE (direct_declaration_no, contract_no);

UPDATE schema_version SET version_num='0050_settlement_direct_documents' WHERE schema_version.version_num = '0049_settlement_direct_allocations';

-- 本次完成版本应为 0050。
SELECT version_num FROM schema_version;

-- 用于判断已部分执行的 0051：请保留这些结构，不删表。
SELECT table_name
FROM information_schema.tables
WHERE table_schema = DATABASE()
  AND table_name IN ('settlement_document_groups', 'settlement_document_group_items', 'settlement_hk_slips')
ORDER BY table_name;

-- 结汇迁移版本与结构检查（MySQL 8.0，只读）
-- 在执行迁移的同一个目标业务库中新开查询，完整运行本文件。
-- 请查看本次产生的结果，不要复用升级脚本开头的旧“结果1”。
-- 本文件只查询版本、表、字段、索引和约束，不改表、不修改版本号。
-- 若版本仍为 0049，0051～0055 脚本的前置 0050 尚未登记成功；
-- 先结合下面的结构结果及“消息”中第一条报错确认，不要直接把版本号改成 0055。

SELECT DATABASE() AS target_database, VERSION() AS mysql_version, version_num
FROM schema_version;

SELECT table_name, table_comment
FROM information_schema.tables
WHERE table_schema = DATABASE()
  AND table_name IN (
    'settlement_batches', 'settlement_bills', 'settlement_contracts',
    'settlement_document_groups', 'settlement_document_group_items', 'settlement_hk_slips'
  )
ORDER BY table_name;

SELECT table_name, column_name, column_type, is_nullable, column_default, column_comment
FROM information_schema.columns
WHERE table_schema = DATABASE()
  AND (
    (table_name IN ('settlement_bills', 'settlement_contracts')
      AND column_name IN ('batch_id', 'direct_declaration_no', 'document_group_id', 'document_key'))
    OR table_name IN ('settlement_document_groups', 'settlement_document_group_items', 'settlement_hk_slips')
  )
ORDER BY table_name, ordinal_position;

SELECT table_name, index_name, non_unique, seq_in_index, column_name
FROM information_schema.statistics
WHERE table_schema = DATABASE()
  AND table_name IN (
    'settlement_bills', 'settlement_contracts',
    'settlement_document_groups', 'settlement_document_group_items', 'settlement_hk_slips'
  )
ORDER BY table_name, index_name, seq_in_index;

SELECT tc.table_name, tc.constraint_name, tc.constraint_type, cc.check_clause
FROM information_schema.table_constraints AS tc
LEFT JOIN information_schema.check_constraints AS cc
  ON cc.constraint_schema = tc.constraint_schema
  AND cc.constraint_name = tc.constraint_name
  AND tc.constraint_type = 'CHECK'
WHERE tc.constraint_schema = DATABASE()
  AND tc.table_name IN (
    'settlement_bills', 'settlement_contracts',
    'settlement_document_groups', 'settlement_document_group_items', 'settlement_hk_slips'
  )
ORDER BY tc.table_name, tc.constraint_type, tc.constraint_name;

SELECT table_name, constraint_name, column_name, referenced_table_name, referenced_column_name
FROM information_schema.key_column_usage
WHERE table_schema = DATABASE()
  AND referenced_table_name IS NOT NULL
  AND table_name IN (
    'settlement_bills', 'settlement_contracts',
    'settlement_document_groups', 'settlement_document_group_items', 'settlement_hk_slips'
  )
ORDER BY table_name, constraint_name, ordinal_position;

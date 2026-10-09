-- 仅适用于业务库版本0004_invoice_allocations，先停止API与同步任务。
-- 与 npm.cmd run db:business:upgrade 二选一；运行前核实账套及原关系身份。
-- 增量创建一张表并搬迁依据，不写入NS。不要在已完成0005迁移的库重复执行。

-- Running upgrade 0004_invoice_allocations -> 0005_customs_relations

CREATE TABLE customs_reconciliation_results (
    id BIGINT UNSIGNED NOT NULL COMMENT '本地结果主键' AUTO_INCREMENT,
    tenant_id VARCHAR(100) COLLATE utf8mb4_bin NOT NULL COMMENT '后端身份派生的数据归属',
    ns_account VARCHAR(100) COLLATE utf8mb4_bin NOT NULL COMMENT 'NS账套，与报关单一致',
    customs_declaration_id BIGINT UNSIGNED NOT NULL COMMENT '报关单本地主键',
    evidence_version INTEGER NOT NULL COMMENT '关联依据契约版本',
    status VARCHAR(16) NOT NULL COMMENT 'partial待核实；collected仅依据；matched关联完整',
    mode VARCHAR(32) NOT NULL COMMENT 'full_sync完整同步；evidence_backfill补拉；dependency_changed失效',
    review_ready BOOL NOT NULL COMMENT '业务依据是否完整，不表示审核通过',
    reason TEXT NOT NULL COMMENT '未满足完整性的原因',
    issues JSON NOT NULL COMMENT '具体来源问题列表',
    raw_line_count INTEGER NOT NULL COMMENT '原始报关行数',
    packing_line_count INTEGER NOT NULL COMMENT 'Packing明细行数',
    purchase_link_count INTEGER NOT NULL COMMENT '销售至母采购行关系数',
    parent_line_count INTEGER NOT NULL COMMENT '母采购来源行数',
    evidence_data JSON NOT NULL COMMENT '原始行、Packing、母子采购身份等依据',
    evidence_read_at DATETIME(6) COMMENT '依据读取时间UTC',
    comparison_payload JSON COMMENT 'NS v3整单关联、数量、金额及币种的完整字符串快照',
    comparison_digest VARCHAR(64) COMMENT '整单内容SHA256，用于判断旧审核是否适用',
    query_request_id VARCHAR(100) COMMENT 'NS关联查询编号',
    query_completed_at DATETIME(6) COMMENT 'NS关联查询完成时间UTC',
    created_at DATETIME(6) NOT NULL COMMENT '本地首次保存时间UTC',
    updated_at DATETIME(6) NOT NULL COMMENT '本地最近更新时间UTC',
    PRIMARY KEY (id),
    CONSTRAINT uq_customs_reconciliation UNIQUE (tenant_id, ns_account, customs_declaration_id),
    CONSTRAINT fk_customs_reconciliation_parent FOREIGN KEY(tenant_id, ns_account, customs_declaration_id) REFERENCES customs_declarations (tenant_id, ns_account, id),
    CONSTRAINT ck_customs_reconciliation_status CHECK (status IN ('partial','collected','matched')),
    CONSTRAINT ck_customs_reconciliation_ready CHECK (review_ready = 0 OR (status = 'matched' AND comparison_payload IS NOT NULL AND comparison_digest IS NOT NULL))
)CHARSET=utf8mb4 COMMENT='报关单关联依据和当前核对结果，一单一条；审核历史保存在应用库' ENGINE=InnoDB COLLATE utf8mb4_bin;

CREATE INDEX ix_customs_reconciliation_status ON customs_reconciliation_results (tenant_id, ns_account, status, review_ready);

INSERT INTO customs_reconciliation_results (
          tenant_id, ns_account, customs_declaration_id, evidence_version, status, mode, review_ready,
          reason, issues, raw_line_count, packing_line_count, purchase_link_count, parent_line_count,
          evidence_data, evidence_read_at, comparison_payload, comparison_digest, query_request_id,
          query_completed_at, created_at, updated_at)
        SELECT c.tenant_id, c.ns_account, c.id, 1, NULLIF(JSON_UNQUOTE(JSON_EXTRACT(JSON_EXTRACT(c.source_data, '$.relationEvidence'), '$.status')), 'null'),
          COALESCE(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(JSON_EXTRACT(c.source_data, '$.relationEvidence'), '$.mode')), 'null'),'full_sync'),
          CASE WHEN NULLIF(JSON_UNQUOTE(JSON_EXTRACT(JSON_EXTRACT(c.source_data, '$.relationEvidence'), '$.status')), 'null') = 'matched' AND NULLIF(JSON_UNQUOTE(JSON_EXTRACT(JSON_EXTRACT(c.source_data, '$.relationEvidence'), '$.comparison.ready')), 'null') = 'true' AND JSON_TYPE(JSON_EXTRACT(JSON_EXTRACT(c.source_data, '$.relationEvidence'), '$.comparison.payload')) = 'OBJECT' THEN 1 ELSE 0 END,
          COALESCE(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(JSON_EXTRACT(c.source_data, '$.relationEvidence'), '$.comparison.reason')), 'null'),'已迁移原有依据，具体问题见issues'),
          COALESCE(JSON_EXTRACT(JSON_EXTRACT(c.source_data, '$.relationEvidence'), '$.issues'),JSON_ARRAY()),
          COALESCE(JSON_LENGTH(JSON_EXTRACT(JSON_EXTRACT(c.source_data, '$.relationEvidence'), '$.rawLines')),0), COALESCE(JSON_LENGTH(JSON_EXTRACT(JSON_EXTRACT(c.source_data, '$.relationEvidence'), '$.packingLines')),0),
          COALESCE(JSON_LENGTH(JSON_EXTRACT(JSON_EXTRACT(c.source_data, '$.relationEvidence'), '$.purchaseLinks')),0), COALESCE(JSON_LENGTH(JSON_EXTRACT(JSON_EXTRACT(c.source_data, '$.relationEvidence'), '$.parentLines')),0),
          JSON_REMOVE(JSON_EXTRACT(c.source_data, '$.relationEvidence'), '$.version','$.account','$.declarationId','$.readAt','$.status','$.mode','$.issues','$.comparison'),
          CASE WHEN SUBSTRING(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(JSON_EXTRACT(c.source_data, '$.relationEvidence'), '$.readAt')), 'null'),20,1)='.' THEN STR_TO_DATE(SUBSTRING_INDEX(SUBSTRING_INDEX(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(JSON_EXTRACT(c.source_data, '$.relationEvidence'), '$.readAt')), 'null'),'+',1),'Z',1), '%Y-%m-%dT%H:%i:%s.%f') ELSE STR_TO_DATE(SUBSTRING(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(JSON_EXTRACT(c.source_data, '$.relationEvidence'), '$.readAt')), 'null'),1,19), '%Y-%m-%dT%H:%i:%s') END, CASE WHEN JSON_TYPE(JSON_EXTRACT(JSON_EXTRACT(c.source_data, '$.relationEvidence'), '$.comparison.payload')) = 'OBJECT' THEN JSON_EXTRACT(JSON_EXTRACT(c.source_data, '$.relationEvidence'), '$.comparison.payload') ELSE NULL END,
          NULLIF(JSON_UNQUOTE(JSON_EXTRACT(JSON_EXTRACT(c.source_data, '$.relationEvidence'), '$.comparison.digest')), 'null'), NULLIF(JSON_UNQUOTE(JSON_EXTRACT(JSON_EXTRACT(c.source_data, '$.relationEvidence'), '$.comparison.requestId')), 'null'), CASE WHEN SUBSTRING(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(JSON_EXTRACT(c.source_data, '$.relationEvidence'), '$.comparison.readCompletedAt')), 'null'),20,1)='.' THEN STR_TO_DATE(SUBSTRING_INDEX(SUBSTRING_INDEX(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(JSON_EXTRACT(c.source_data, '$.relationEvidence'), '$.comparison.readCompletedAt')), 'null'),'+',1),'Z',1), '%Y-%m-%dT%H:%i:%s.%f') ELSE STR_TO_DATE(SUBSTRING(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(JSON_EXTRACT(c.source_data, '$.relationEvidence'), '$.comparison.readCompletedAt')), 'null'),1,19), '%Y-%m-%dT%H:%i:%s') END,
          UTC_TIMESTAMP(6), UTC_TIMESTAMP(6)
        FROM customs_declarations c WHERE JSON_TYPE(JSON_EXTRACT(c.source_data, '$.relationEvidence')) = 'OBJECT';

UPDATE customs_declarations c JOIN customs_reconciliation_results r
          ON r.tenant_id=c.tenant_id AND r.ns_account=c.ns_account AND r.customs_declaration_id=c.id
        SET c.source_data=JSON_REMOVE(c.source_data,'$.relationEvidence')
        WHERE JSON_CONTAINS_PATH(c.source_data,'one','$.relationEvidence')=1;

UPDATE business_alembic_version SET version_num='0005_customs_relations' WHERE business_alembic_version.version_num = '0004_invoice_allocations';

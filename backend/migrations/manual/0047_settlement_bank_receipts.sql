-- 结汇：银行收汇明细（MySQL 8）：只新增 settlement_bank_receipts 一张表，不修改既有表和数据。
-- 执行前确认 schema_version 为 0046_settlement_documents，且新表尚不存在。
-- 若 schema_version 仍早于 0046（结汇批次、结汇资料的表尚未建立），请先执行自动迁移或补齐 0045、0046。
-- 与自动迁移（npm run db:upgrade）二选一，不要重复执行。
SELECT DATABASE();
SELECT version_num FROM schema_version;

-- 只读核对：直接收汇改为总账后不再新建直接收汇批次，页面也不再展示这类批次。
-- 下面的查询应返回 0；不为 0 时说明库里还有未完结的直接收汇批次，请先在旧页面作废或结汇后再上线。
SELECT COUNT(*) AS open_direct_batches
FROM settlement_batches
WHERE route = 'direct' AND status IN ('collected', 'documents_ready');

-- Running upgrade 0046_settlement_documents -> 0047_settlement_bank_receipts

CREATE TABLE settlement_bank_receipts (
    id BIGINT UNSIGNED NOT NULL COMMENT '银行收汇记录本地主键' AUTO_INCREMENT,
    receipt_date DATE NOT NULL COMMENT '收汇日期（银行入账日期）',
    receiving_company VARCHAR(200) NOT NULL COMMENT '收汇抬头：我方收款主体，如上海毅鑫',
    receiving_account VARCHAR(200) COMMENT '收款账户（境内美金账户）',
    payer_name VARCHAR(500) NOT NULL COMMENT '付款人户名（银行流水原文）',
    payer_key VARCHAR(500) COLLATE utf8mb4_bin NOT NULL COMMENT '付款人户名规范化名称；与 customer_key 不同即三方代付',
    customer_name VARCHAR(500) NOT NULL COMMENT '实际客户，即境外收货人；取导入表格填写的值，与付款人户名不同时为三方代付',
    customer_key VARCHAR(500) COLLATE utf8mb4_bin NOT NULL COMMENT '实际客户规范化名称，与海关回执境外收货人的规范化名称相等时归到同一收货人',
    currency VARCHAR(20) NOT NULL COMMENT '币种代码，如 USD',
    amount NUMERIC(24, 6) NOT NULL COMMENT '收汇金额，与 currency 配套',
    reference VARCHAR(200) COMMENT '银行流水号',
    source_file VARCHAR(255) COMMENT '导入来源文件名',
    source_row INTEGER COMMENT '来源文件中的行号，便于核对',
    imported_by VARCHAR(190) NOT NULL COMMENT '导入人（认证身份）',
    imported_at DATETIME(6) NOT NULL COMMENT '导入时间，UTC',
    created_at DATETIME(6) NOT NULL COMMENT '本地记录创建时间，UTC' DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL COMMENT '本地记录最后更新时间，UTC；由 DAO 更新' DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id)
)ENGINE=InnoDB CHARSET=utf8mb4 COMMENT='银行收汇明细：境内美金账户收汇记录及其对应的实际客户（境外收货人）' COLLATE utf8mb4_bin;

CREATE INDEX ix_settlement_bank_receipt_customer ON settlement_bank_receipts (customer_key, currency);

CREATE INDEX ix_settlement_bank_receipt_date ON settlement_bank_receipts (receipt_date);

UPDATE schema_version SET version_num='0047_settlement_bank_receipts' WHERE schema_version.version_num = '0046_settlement_documents';


COMMIT;
SELECT version_num FROM schema_version;

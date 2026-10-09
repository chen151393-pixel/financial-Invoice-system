-- 发票 Excel 字段扩展设计草案，2026-09-22；未执行、不是已注册迁移。
-- 前提：目标库已具有 business-schema.sql 中的 invoices、invoice_lines 原始结构。
-- 不可直接用于未知版本的库，不可重复执行；实施前检查实际结构及历史数据。
-- 不含 USE、建库、删除或导入语句。未来以独立业务库 Alembic 迁移落地。
-- MySQL 版本要求沿用现有业务库；所有时间写入由后端负责，时间戳统一 UTC。

ALTER TABLE invoices
    ADD COLUMN invoice_type_name VARCHAR(100) NULL COMMENT '发票种类原文，保留数电专票、普票、航空行程单等',
    ADD COLUMN invoice_direction VARCHAR(16) NOT NULL DEFAULT 'unknown' COMMENT '进销项方向：input进项；output销项；unknown未核实',
    ADD COLUMN entry_date DATE NULL COMMENT '来源录入日期，不是本地创建时间',
    ADD COLUMN invoice_status_raw VARCHAR(100) NULL COMMENT '来源发票状态原文，例如正常、已红冲',
    ADD COLUMN invoice_status VARCHAR(24) NOT NULL DEFAULT 'unknown' COMMENT '标准状态：normal正常；red_offset已红冲；void作废；unknown未知',
    ADD COLUMN certification_date DATE NULL COMMENT '认证日期，空值不代表未认证结论',
    ADD COLUMN tax_period VARCHAR(7) NULL COMMENT '税款所属期，核实后规范为YYYY-MM；原值留在source_data',
    ADD COLUMN project_name VARCHAR(255) NULL COMMENT '项目名称原文',
    ADD COLUMN department_name VARCHAR(255) NULL COMMENT '部门名称原文',
    ADD COLUMN employee_name VARCHAR(255) NULL COMMENT '职员名称原文',
    ADD COLUMN seller_address_phone VARCHAR(1000) NULL COMMENT '供应商地址及电话合并原文，不强行拆分',
    ADD COLUMN seller_bank_account VARCHAR(1000) NULL COMMENT '供应商开户行及账号合并原文，展示及日志按权限脱敏',
    ADD COLUMN business_type_name VARCHAR(100) NULL COMMENT '业务类型原文，例如修理费、办公费、采购固定资产',
    ADD COLUMN tax_rate_summary VARCHAR(255) NULL COMMENT '票头税率展示原文，例如不征税,9%；不能作为单一数值税率',
    ADD COLUMN accounting_period VARCHAR(7) NULL COMMENT '记账期间，核实后规范为YYYY-MM；原值留在source_data',
    ADD COLUMN voucher_reference TEXT NULL COMMENT '关联凭证原文，不假定只有一个凭证或可解析为本地ID',
    ADD COLUMN remark TEXT NULL COMMENT '发票备注原文，不用作默认采购单关联键',
    ADD COLUMN validation_status VARCHAR(16) NOT NULL DEFAULT 'pending' COMMENT '校验状态：pending待校验；passed通过；review需核实；failed失败',
    ADD COLUMN validation_errors JSON NULL COMMENT '结构化校验问题，包含字段、代码和中文原因',
    ADD COLUMN content_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL COMMENT '标准业务内容SHA256摘要，不是发票唯一身份',
    ADD COLUMN source_version BIGINT UNSIGNED NOT NULL DEFAULT 1 COMMENT '本地来源内容版本，内容变化后由服务递增',
    ADD COLUMN created_at DATETIME(6) NULL COMMENT '本地首次保存时间UTC；旧数据未知时不伪造',
    ADD COLUMN updated_at DATETIME(6) NULL COMMENT '本地最近内容更新时间UTC',
    ADD CONSTRAINT ck_invoice_direction CHECK (invoice_direction IN ('input','output','unknown')),
    ADD CONSTRAINT ck_invoice_business_status CHECK (invoice_status IN ('normal','red_offset','void','unknown')),
    ADD CONSTRAINT ck_invoice_validation CHECK (validation_status IN ('pending','passed','review','failed')),
    ADD CONSTRAINT ck_invoice_version CHECK (source_version >= 1);

ALTER TABLE invoice_lines
    MODIFY COLUMN quantity DECIMAL(26,8) NULL COMMENT '数量；保留18位整数及8位小数，空值区别于零',
    ADD COLUMN tax_rate_raw VARCHAR(100) NULL COMMENT '行税率原文，例如13%、免税、不征税',
    ADD COLUMN tax_treatment VARCHAR(24) NOT NULL DEFAULT 'unknown' COMMENT '税收处理：rate数值税率；exempt免税；non_taxable不征税；unknown未知',
    ADD COLUMN input_type_name VARCHAR(100) NULL COMMENT '进项类型原文，例如货物、应税劳务',
    ADD COLUMN taxation_method_name VARCHAR(255) NULL COMMENT '计税方法原文',
    ADD COLUMN stamp_tax_category VARCHAR(255) NULL COMMENT '印花税税目原文，仅保存来源不自动计算税款',
    ADD COLUMN stamp_tax_subcategory VARCHAR(255) NULL COMMENT '印花税子目原文',
    ADD CONSTRAINT ck_invoice_line_tax_treatment CHECK (tax_treatment IN ('rate','exempt','non_taxable','unknown'));

-- 保留现有票号索引、来源唯一键、明细唯一键及带tenant_id的父子外键。
-- 按账套日期浏览；按同一账套供应商税号筛选。上线前用实际查询EXPLAIN确认。
CREATE INDEX ix_invoice_account_date
    ON invoices (tenant_id, external_system, external_account, invoice_date, id);
CREATE INDEX ix_invoice_account_seller_date
    ON invoices (tenant_id, external_system, external_account, seller_tax_no, invoice_date, id);

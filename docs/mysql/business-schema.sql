-- 真实业务存储：独立 MySQL 建库建表 SQL，不是迁移。
-- 当前范围：采购订单与报关单来源NS，发票来源外部；只保留六张业务表。
-- 适用 MySQL 8.0.16+，在新空库执行一次，不删除或复制现有数据。
CREATE DATABASE financial_invoice_business CHARACTER SET utf8mb4 COLLATE utf8mb4_bin;
USE financial_invoice_business;
SET NAMES utf8mb4;
SET time_zone = '+00:00';

CREATE TABLE customs_declarations (
	id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '本地自增主键，不使用来源系统内部ID',
	tenant_id VARCHAR(100) COLLATE utf8mb4_bin NOT NULL COMMENT '本系统数据归属标识，由后端身份配置确定',
	record_no VARCHAR(150) COMMENT '来源显示编号，例如NS的CD编号，不是真实报关单号',
	declaration_no VARCHAR(150) COLLATE utf8mb4_bin COMMENT '真实报关单号，暂不设全局唯一',
	declaration_date DATE COMMENT '申报日期，保留来源业务日期',
	declarant_identifier VARCHAR(100) COLLATE utf8mb4_bin COMMENT '申报主体业务标识，不能直接用来源公司ID跨平台比较',
	declarant_name VARCHAR(255) COMMENT '报关单申报主体名称',
	detail_sync_status VARCHAR(16) NOT NULL DEFAULT 'pending' COMMENT '明细同步状态：pending待同步；complete完整；failed失败',
	last_complete_sync_at DATETIME(6) COMMENT '最近一次完整同步成功时间，UTC',
	synced_at DATETIME(6) COMMENT '当前采用的完整报关单版本保存时间，UTC',
	is_active BOOL NOT NULL DEFAULT 1 COMMENT '是否有效：1有效；0已确认停用或源明细已移除',
	CONSTRAINT uq_customs_ns_parent UNIQUE (tenant_id, ns_account, id),
	ns_account VARCHAR(100) COLLATE utf8mb4_bin NOT NULL COMMENT 'NS账户标识，由服务器连接配置确定',
	ns_internal_id VARCHAR(190) COLLATE utf8mb4_bin NOT NULL COMMENT 'NS来源单据内部ID，仅用于来源去重，不是本地主键',
	source_data JSON NOT NULL COMMENT '本次完整单头和全部明细原始快照，精确小数按约定编码为字符串',
	source_modified_at DATETIME(6) COMMENT '来源记录最后修改时间，统一转换为UTC，来源未提供时为空',
	CONSTRAINT uq_customs_ns_source UNIQUE (tenant_id, ns_account, ns_internal_id),
	CONSTRAINT ck_customs_ns_source CHECK (CHAR_LENGTH(TRIM(ns_account)) > 0 AND CHAR_LENGTH(TRIM(ns_internal_id)) > 0),
	PRIMARY KEY (id),
	CONSTRAINT uq_customs_tenant_id UNIQUE (tenant_id, id),
	CONSTRAINT ck_customs_sync_status CHECK (detail_sync_status IN ('pending','complete','failed')),
	CONSTRAINT ck_customs_declarations_active CHECK (is_active IN (0,1))
)ENGINE=InnoDB CHARSET=utf8mb4 COMMENT='报关单主表，当前来源NS' COLLATE utf8mb4_bin;

CREATE INDEX ix_customs_number ON customs_declarations (tenant_id, declaration_no);

CREATE TABLE invoices (
	id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '本地自增主键，不使用来源系统内部ID',
	tenant_id VARCHAR(100) COLLATE utf8mb4_bin NOT NULL COMMENT '本系统数据归属标识，由后端身份配置确定',
	invoice_code VARCHAR(50) COLLATE utf8mb4_bin COMMENT '发票代码，来源未提供时为空',
	invoice_no VARCHAR(100) COLLATE utf8mb4_bin COMMENT '发票号码，不单独作为跨平台唯一键',
	invoice_date DATE COMMENT '发票开具日期',
	seller_name VARCHAR(255) COMMENT '销售方名称',
	seller_tax_no VARCHAR(100) COLLATE utf8mb4_bin COMMENT '销售方纳税人识别号',
	buyer_name VARCHAR(255) COMMENT '购买方名称',
	buyer_tax_no VARCHAR(100) COLLATE utf8mb4_bin COMMENT '购买方纳税人识别号',
	currency_code VARCHAR(20) COMMENT '来源币种代码，金额按此币种保存',
	amount_excluding_tax DECIMAL(24, 6) COMMENT '不含税金额',
	tax_amount DECIMAL(24, 6) COMMENT '税额',
	amount_including_tax DECIMAL(24, 6) COMMENT '价税合计金额',
	detail_sync_status VARCHAR(16) NOT NULL DEFAULT 'pending' COMMENT '明细同步状态：pending待同步；complete完整；failed失败',
	last_complete_sync_at DATETIME(6) COMMENT '最近一次完整同步成功时间，UTC',
	synced_at DATETIME(6) COMMENT '当前采用的完整发票版本保存时间，UTC',
	is_active BOOL NOT NULL DEFAULT 1 COMMENT '是否有效：1有效；0已确认停用或源明细已移除',
	external_system VARCHAR(50) COLLATE utf8mb4_bin NOT NULL COMMENT '当前接入的外部发票平台或导入渠道编码',
	external_account VARCHAR(100) COLLATE utf8mb4_bin NOT NULL COMMENT '外部平台账户或固定导入命名空间，由服务器配置',
	external_record_id VARCHAR(190) COLLATE utf8mb4_bin COMMENT '外部发票稳定记录ID，无此ID时必须提供import_key',
	import_key VARCHAR(190) COLLATE utf8mb4_bin COMMENT '无外部记录ID时使用的稳定导入键，重复导入必须复用',
	source_data JSON NOT NULL COMMENT '本次完整单头和全部明细原始快照，精确小数按约定编码为字符串',
	source_modified_at DATETIME(6) COMMENT '来源记录最后修改时间，统一转换为UTC，来源未提供时为空',
	CONSTRAINT uq_invoice_external_source UNIQUE (tenant_id, external_system, external_account, external_record_id),
	CONSTRAINT uq_invoice_import UNIQUE (tenant_id, external_system, external_account, import_key),
	CONSTRAINT ck_invoice_external_namespace CHECK (CHAR_LENGTH(TRIM(external_system)) > 0 AND CHAR_LENGTH(TRIM(external_account)) > 0),
	CONSTRAINT ck_invoice_source_required CHECK (external_record_id IS NOT NULL OR import_key IS NOT NULL),
	CONSTRAINT ck_invoice_source_nonempty CHECK ((external_record_id IS NULL OR CHAR_LENGTH(TRIM(external_record_id)) > 0) AND (import_key IS NULL OR CHAR_LENGTH(TRIM(import_key)) > 0)),
	PRIMARY KEY (id),
	CONSTRAINT uq_invoice_tenant_id UNIQUE (tenant_id, id),
	CONSTRAINT ck_invoice_sync_status CHECK (detail_sync_status IN ('pending','complete','failed')),
	CONSTRAINT ck_invoices_active CHECK (is_active IN (0,1))
)ENGINE=InnoDB CHARSET=utf8mb4 COMMENT='发票主表，当前来源外部平台或文件导入' COLLATE utf8mb4_bin;

CREATE INDEX ix_invoice_number ON invoices (tenant_id, invoice_no);

CREATE TABLE purchase_orders (
	id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '本地自增主键，不使用来源系统内部ID',
	tenant_id VARCHAR(100) COLLATE utf8mb4_bin NOT NULL COMMENT '本系统数据归属标识，由后端身份配置确定',
	order_no VARCHAR(150) COLLATE utf8mb4_bin COMMENT '子采购订单显示单号，不是本地主键',
	order_date DATE COMMENT '子采购订单业务日期',
	parent_order_no VARCHAR(150) COMMENT '关联母采购订单单号',
	pl_no VARCHAR(100) COLLATE utf8mb4_bin COMMENT '关联PL单号，用于按PL联查',
	customs_declaration_id BIGINT UNSIGNED COMMENT '解析完成后的关联报关单本地主键，尚未解析时为空',
	supplier_identifier VARCHAR(100) COLLATE utf8mb4_bin COMMENT 'NS供应商引用标识，仅在所属NS账户内解释',
	supplier_name VARCHAR(255) COMMENT '供应商名称',
	company_identifier VARCHAR(100) COLLATE utf8mb4_bin COMMENT 'NS公司引用类型及内部ID，在同一NS账户内比较',
	company_name VARCHAR(255) COMMENT '子采购订单公司抬头名称',
	currency_code VARCHAR(20) COMMENT '来源币种代码，金额按此币种保存',
	total_amount DECIMAL(24, 6) COMMENT '来源子采购订单总金额，不可按货品行重复累计',
	detail_sync_status VARCHAR(16) NOT NULL DEFAULT 'pending' COMMENT '明细同步状态：pending待同步；complete完整；failed失败',
	last_complete_sync_at DATETIME(6) COMMENT '最近一次完整同步成功时间，UTC',
	synced_at DATETIME(6) COMMENT '当前采用的完整子采购订单版本保存时间，UTC',
	is_active BOOL NOT NULL DEFAULT 1 COMMENT '是否有效：1有效；0已确认停用或源明细已移除',
	ns_account VARCHAR(100) COLLATE utf8mb4_bin NOT NULL COMMENT 'NS账户标识，由服务器连接配置确定',
	ns_internal_id VARCHAR(190) COLLATE utf8mb4_bin NOT NULL COMMENT 'NS来源单据内部ID，仅用于来源去重，不是本地主键',
	source_data JSON NOT NULL COMMENT '本次完整单头和全部明细原始快照，精确小数按约定编码为字符串',
	source_modified_at DATETIME(6) COMMENT '来源记录最后修改时间，统一转换为UTC，来源未提供时为空',
	CONSTRAINT uq_purchase_ns_source UNIQUE (tenant_id, ns_account, ns_internal_id),
	CONSTRAINT ck_purchase_ns_source CHECK (CHAR_LENGTH(TRIM(ns_account)) > 0 AND CHAR_LENGTH(TRIM(ns_internal_id)) > 0),
	PRIMARY KEY (id),
	CONSTRAINT uq_purchase_tenant_id UNIQUE (tenant_id, id),
	CONSTRAINT fk_purchase_customs_tenant FOREIGN KEY(tenant_id, ns_account, customs_declaration_id) REFERENCES customs_declarations (tenant_id, ns_account, id),
	CONSTRAINT ck_purchase_sync_status CHECK (detail_sync_status IN ('pending','complete','failed')),
	CONSTRAINT ck_purchase_orders_active CHECK (is_active IN (0,1))
)ENGINE=InnoDB CHARSET=utf8mb4 COMMENT='子采购订单主表，当前来源NS' COLLATE utf8mb4_bin;

CREATE INDEX ix_purchase_number ON purchase_orders (tenant_id, order_no);

CREATE INDEX ix_purchase_pl ON purchase_orders (tenant_id, pl_no);

CREATE TABLE customs_declaration_lines (
	id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '本地自增主键，不使用来源系统内部ID',
	tenant_id VARCHAR(100) COLLATE utf8mb4_bin NOT NULL COMMENT '本系统数据归属标识，由后端身份配置确定',
	customs_declaration_id BIGINT UNSIGNED NOT NULL COMMENT '所属报关单的本地主键',
	source_line_key VARCHAR(190) COLLATE utf8mb4_bin NOT NULL COMMENT '本单据内稳定来源明细标识，用于重复拉取去重，不能用数组下标',
	line_no VARCHAR(40) COMMENT '来源显示行号，不作为明细唯一标识',
	pl_no VARCHAR(100) COLLATE utf8mb4_bin COMMENT '报关明细的Packing NO.，用于与采购侧PL单号关联',
	sales_order_no VARCHAR(150) COMMENT '报关明细对应的销售订单编号',
	company_identifier VARCHAR(100) COLLATE utf8mb4_bin COMMENT 'NS公司引用类型及内部ID，在同一NS账户内比较',
	company_name VARCHAR(255) COMMENT '报关明细公司抬头名称，用于拼表展示',
	origin_place VARCHAR(255) COMMENT '境内货源地，保留来源地区或城市名称',
	item_code VARCHAR(150) COMMENT '来源货品编码',
	declaration_name VARCHAR(500) COMMENT '报关品名',
	specification VARCHAR(500) COMMENT '规格或型号，保留来源原值',
	quantity DECIMAL(24, 6) COMMENT '报关明细原数量，与unit_name配套，区别于本次报关数量',
	unit_name VARCHAR(50) COMMENT '报关明细原数量单位，与quantity配套',
	declared_quantity DECIMAL(24, 6) COMMENT '本次报关数量，与declared_unit配套',
	declared_unit VARCHAR(50) COMMENT '本次报关数量单位',
	unit_price DECIMAL(24, 8) COMMENT '来源明细单价，含税口径按来源字段确认',
	amount DECIMAL(24, 6) COMMENT '来源报关明细行金额，按本行币种保存',
	currency_code VARCHAR(20) COMMENT '来源币种代码，金额按此币种保存',
	synced_at DATETIME(6) COMMENT '当前记录成功同步保存时间，UTC',
	is_active BOOL NOT NULL DEFAULT 1 COMMENT '是否有效：1有效；0已确认停用或源明细已移除',
	PRIMARY KEY (id),
	CONSTRAINT uq_customs_source_line UNIQUE (tenant_id, customs_declaration_id, source_line_key),
	CONSTRAINT ck_customs_line_key CHECK (CHAR_LENGTH(TRIM(source_line_key)) > 0),
	CONSTRAINT fk_customs_line_parent FOREIGN KEY(tenant_id, customs_declaration_id) REFERENCES customs_declarations (tenant_id, id),
	CONSTRAINT ck_customs_declaration_lines_active CHECK (is_active IN (0,1))
)ENGINE=InnoDB CHARSET=utf8mb4 COMMENT='报关明细' COLLATE utf8mb4_bin;

CREATE INDEX ix_customs_lines_pl ON customs_declaration_lines (tenant_id, pl_no, is_active);

CREATE INDEX ix_customs_lines_parent ON customs_declaration_lines (tenant_id, customs_declaration_id, is_active);

CREATE TABLE invoice_lines (
	id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '本地自增主键，不使用来源系统内部ID',
	tenant_id VARCHAR(100) COLLATE utf8mb4_bin NOT NULL COMMENT '本系统数据归属标识，由后端身份配置确定',
	invoice_id BIGINT UNSIGNED NOT NULL COMMENT '所属发票的本地主键',
	source_line_key VARCHAR(190) COLLATE utf8mb4_bin NOT NULL COMMENT '本单据内稳定来源明细标识，用于重复拉取去重，不能用数组下标',
	line_no VARCHAR(40) COMMENT '来源显示行号，不作为明细唯一标识',
	item_name VARCHAR(500) COMMENT '发票货物或应税劳务、服务名称',
	specification VARCHAR(500) COMMENT '规格或型号，保留来源原值',
	quantity DECIMAL(24, 6) COMMENT '货品数量，与本行单位配套',
	unit_name VARCHAR(50) COMMENT '货品数量单位',
	unit_price DECIMAL(24, 8) COMMENT '来源明细单价，含税口径按来源字段确认',
	amount_excluding_tax DECIMAL(24, 6) COMMENT '不含税金额',
	tax_rate DECIMAL(12, 8) COMMENT '税率，按小数比例保存，例如13%保存为0.13',
	tax_amount DECIMAL(24, 6) COMMENT '税额',
	amount_including_tax DECIMAL(24, 6) COMMENT '价税合计金额',
	synced_at DATETIME(6) COMMENT '当前记录成功同步保存时间，UTC',
	is_active BOOL NOT NULL DEFAULT 1 COMMENT '是否有效：1有效；0已确认停用或源明细已移除',
	PRIMARY KEY (id),
	CONSTRAINT uq_invoice_source_line UNIQUE (tenant_id, invoice_id, source_line_key),
	CONSTRAINT ck_invoice_line_key CHECK (CHAR_LENGTH(TRIM(source_line_key)) > 0),
	CONSTRAINT fk_invoice_line_parent FOREIGN KEY(tenant_id, invoice_id) REFERENCES invoices (tenant_id, id),
	CONSTRAINT ck_invoice_lines_active CHECK (is_active IN (0,1))
)ENGINE=InnoDB CHARSET=utf8mb4 COMMENT='发票明细' COLLATE utf8mb4_bin;

CREATE INDEX ix_invoice_lines_parent ON invoice_lines (tenant_id, invoice_id, is_active);

CREATE TABLE purchase_order_lines (
	id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '本地自增主键，不使用来源系统内部ID',
	tenant_id VARCHAR(100) COLLATE utf8mb4_bin NOT NULL COMMENT '本系统数据归属标识，由后端身份配置确定',
	purchase_order_id BIGINT UNSIGNED NOT NULL COMMENT '所属子采购订单的本地主键',
	source_line_key VARCHAR(190) COLLATE utf8mb4_bin NOT NULL COMMENT '本单据内稳定来源明细标识，用于重复拉取去重，不能用数组下标',
	line_no VARCHAR(40) COMMENT '来源显示行号，不作为明细唯一标识',
	item_code VARCHAR(150) COMMENT '来源货品编码',
	item_name VARCHAR(500) COMMENT '货品名称',
	declaration_name VARCHAR(500) COMMENT '报关品名',
	specification VARCHAR(500) COMMENT '规格或型号，保留来源原值',
	quantity DECIMAL(24, 6) COMMENT '采购货品数量，与unit_name配套',
	unit_name VARCHAR(50) COMMENT '采购货品数量单位',
	declaration_quantity DECIMAL(24, 6) COMMENT '采购行报关数量，与declaration_unit配套',
	declaration_unit VARCHAR(50) COMMENT '采购行报关数量单位',
	tax_inclusive_price DECIMAL(24, 8) COMMENT '采购货品行含税单价',
	amount DECIMAL(24, 6) COMMENT '采购货品行总金额，不能填入重复的整单金额',
	synced_at DATETIME(6) COMMENT '当前记录成功同步保存时间，UTC',
	is_active BOOL NOT NULL DEFAULT 1 COMMENT '是否有效：1有效；0已确认停用或源明细已移除',
	PRIMARY KEY (id),
	CONSTRAINT uq_purchase_source_line UNIQUE (tenant_id, purchase_order_id, source_line_key),
	CONSTRAINT ck_purchase_line_key CHECK (CHAR_LENGTH(TRIM(source_line_key)) > 0),
	CONSTRAINT fk_purchase_line_parent FOREIGN KEY(tenant_id, purchase_order_id) REFERENCES purchase_orders (tenant_id, id),
	CONSTRAINT ck_purchase_order_lines_active CHECK (is_active IN (0,1))
)ENGINE=InnoDB CHARSET=utf8mb4 COMMENT='采购货品行' COLLATE utf8mb4_bin;

CREATE INDEX ix_purchase_lines_parent ON purchase_order_lines (tenant_id, purchase_order_id, is_active);

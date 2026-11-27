-- 结汇客户名称归并：MySQL 8.0 手动增量升级 0057 → 0058。
-- DDL 与 backend/migrations/versions/0058_settlement_consignees.py 保持一致。
-- 请在目标业务库中执行；不固定库名，不修改回执、流水、批次或收汇金额。
--
-- 先单独执行【一】，只有一条版本记录且为 0057_review_customs_import_jobs 时，才能执行【二】。
-- 已为 0058 时无需重跑；低于 0057 时先补齐之前的迁移，不可跳号。
-- MySQL DDL 会自动提交。任何语句报错立即停止，不要忽略错误或单独执行版本更新。
-- 本 SQL 只建名称表并推进版本；存量名称由新版应用启动时自动补齐。

-- 【一】单独检查目标库与当前版本。
SELECT DATABASE() AS target_database, VERSION() AS mysql_version;
SELECT version_num FROM schema_version;

-- 【二】确认前置版本正确后，按顺序执行下面全部语句。
SET NAMES utf8mb4 COLLATE utf8mb4_bin;

CREATE TABLE settlement_consignees (
    name_key VARCHAR(500) COLLATE utf8mb4_bin NOT NULL COMMENT '去符号、空白并统一大写后的客户匹配键',
    display_name VARCHAR(500) NOT NULL COMMENT '首次登记的客户原名；后续格式变体不覆盖',
    created_at DATETIME(6) NOT NULL COMMENT '本地记录创建时间，UTC' DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL COMMENT '本地记录最后更新时间，UTC；由 DAO 更新' DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (name_key)
) CHARSET=utf8mb4 ENGINE=InnoDB COMMENT='结汇客户名称归并；香港客户展示由环境配置覆盖' COLLATE utf8mb4_bin;

UPDATE schema_version
SET version_num = '0058_settlement_consignees'
WHERE version_num = '0057_review_customs_import_jobs';

-- 更新应影响 1 行，最终版本应为 0058_settlement_consignees。
SELECT ROW_COUNT() AS updated_version_rows;
SELECT version_num FROM schema_version;
SHOW CREATE TABLE settlement_consignees;

-- 完成后启动包含 0058 的新版应用。
-- 应用会先补齐既有客户名称，再启动工作线程；不会覆盖已登记名称。
-- 如需检查初始化结果，在应用启动完成后执行：
-- SELECT name_key, display_name FROM settlement_consignees ORDER BY name_key;

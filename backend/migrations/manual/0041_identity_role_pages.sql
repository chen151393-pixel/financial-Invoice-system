-- MySQL 8：角色页面权限，0040_sync_ns_plans -> 0041_identity_role_pages。
-- 本文件仅供手动执行，不会自动连接数据库，也不包含角色授权数据。
-- 先停止后端并选中正确的业务数据库，避免与其他迁移同时执行。
-- 请按下面的三个阶段分段执行，不要在忽略 SQL 错误的模式下整批运行。

-- 第一步：只执行本段检查。
SELECT DATABASE() AS current_database;
SELECT version_num FROM schema_version;
SHOW TABLES LIKE 'identity_role_pages';

-- 仅当选中的库正确、schema_version 恰好一行且为 0040_sync_ns_plans、
-- identity_role_pages 尚不存在时，才继续第二步。条件不符请停止，不要改版本号。

-- 第二步：建表。MySQL DDL 会隐式提交，建表失败时不能继续更新版本。
SET NAMES utf8mb4;
SET time_zone = '+00:00';

CREATE TABLE identity_role_pages (
    id BIGINT UNSIGNED NOT NULL COMMENT '角色页面配置主键' AUTO_INCREMENT,
    `role` VARCHAR(40) NOT NULL COMMENT '固定角色代码；管理员页面权限不可修改',
    pages JSON NOT NULL COMMENT '允许访问的页面代码数组；空数组为无权限',
    revision INTEGER NOT NULL COMMENT '编辑版本；未配置时接口版本为 0',
    updated_by VARCHAR(200) NOT NULL COMMENT '最近保存的认证管理员',
    created_at DATETIME(6) NOT NULL COMMENT '本地记录创建时间，UTC' DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL COMMENT '本地记录最后更新时间，UTC；由 DAO 更新' DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    CONSTRAINT uq_identity_role_pages_role UNIQUE (`role`)
)COMMENT='角色的页面访问范围，多角色取并集，独立于具体业务操作权限' CHARSET=utf8mb4 ENGINE=InnoDB COLLATE utf8mb4_bin;

-- 第三步：仅在上面的 CREATE TABLE 成功后执行，登记与 Alembic 一致的版本。
UPDATE schema_version SET version_num='0041_identity_role_pages' WHERE schema_version.version_num = '0040_sync_ns_plans';

-- affected_rows 必须为 1；否则停止并核对版本，不能强制覆盖。
SELECT ROW_COUNT() AS affected_rows;
SELECT version_num FROM schema_version;
SHOW CREATE TABLE identity_role_pages;

-- 完成后部署对应版本的前后端并重启。
-- 不需要插入初始角色配置；管理员在“角色管理”保存后由接口写入并记录审计。

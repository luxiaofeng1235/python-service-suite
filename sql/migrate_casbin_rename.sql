-- ============================================
-- 迁移：auth_casbin_rule 列重命名 v0→sub, v1→obj, v2→act，删除 v3~v5
-- ============================================

ALTER TABLE `auth_casbin_rule`
    CHANGE `v0` `sub` VARCHAR(100) NOT NULL COMMENT 'sub：主体（角色名 或 用户ID）',
    CHANGE `v1` `obj` VARCHAR(100) NOT NULL COMMENT 'obj：客体（资源名，或 g 时的角色名）',
    CHANGE `v2` `act` VARCHAR(100) DEFAULT '' COMMENT 'act：操作（如 list / create / delete）',
    DROP COLUMN `v3`,
    DROP COLUMN `v4`,
    DROP COLUMN `v5`;

ALTER TABLE `auth_casbin_rule`
    DROP INDEX `idx_v0`,
    ADD INDEX `idx_sub` (`sub`);

-- auth_roles 表的注释更新（仅注释，不影响功能）
ALTER TABLE `auth_roles`
    MODIFY `name` VARCHAR(50) NOT NULL COMMENT '角色名（与 casbin_rule.sub 对应）';

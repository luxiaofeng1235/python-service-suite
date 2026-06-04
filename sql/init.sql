-- ============================================
-- FastAPI AI Service - 数据库初始化脚本
-- 目标数据库: MySQL 8.0+1
-- 编码: utf8mb4
-- 自动生成时间: 2025-07-13
-- ============================================

-- 创建数据库（如果尚未创建）
-- CREATE DATABASE IF NOT EXISTS fastapi_server
--     DEFAULT CHARACTER SET utf8mb4
--     DEFAULT COLLATE utf8mb4_unicode_ci;

-- ============================================
-- 1. 用户表
-- ============================================

CREATE TABLE IF NOT EXISTS `users` (
    `id`            INT(11)         NOT NULL AUTO_INCREMENT  COMMENT '用户ID（主键）',
    `username`      VARCHAR(50)     NOT NULL                 COMMENT '用户名（唯一）',
    `password_hash` VARCHAR(255)    NOT NULL                 COMMENT '密码哈希',
    `nickname`      VARCHAR(50)     DEFAULT NULL             COMMENT '昵称',
    `email`         VARCHAR(255)    DEFAULT NULL             COMMENT '电子邮箱',
    `is_active`     TINYINT(1)      NOT NULL DEFAULT 1       COMMENT '是否启用 1-启用 0-禁用',
    `is_deleted`    TINYINT(1)      NOT NULL DEFAULT 0       COMMENT '是否已注销（软删除）',
    `deleted_at`    DATETIME        DEFAULT NULL             COMMENT '注销时间',
    `last_login_ip` VARCHAR(45)     DEFAULT NULL             COMMENT '最后登录 IP',
    `last_login_at` DATETIME        DEFAULT NULL             COMMENT '最后登录时间',
    `created_at`    DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_at`    DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_username` (`username`),
    KEY `idx_created_at` (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='用户表';


-- ============================================
-- 2. 用户登录 Token 表
-- ============================================

CREATE TABLE IF NOT EXISTS `user_tokens` (
    `id`         INT(11)      NOT NULL AUTO_INCREMENT COMMENT 'id',
    `user_id`    INT(11)      NOT NULL                 COMMENT '用户ID',
    `token`      VARCHAR(64)  NOT NULL                 COMMENT '登录Token',
    `expires_at` DATETIME     NOT NULL                 COMMENT '过期时间',
    `is_active`  TINYINT(1)   NOT NULL DEFAULT 1       COMMENT '是否有效',
    `created_at` DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_at` DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_token` (`token`),
    KEY `idx_user_id` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='用户登录Token';


-- ============================================
-- 3. 后台管理员表
-- ============================================

CREATE TABLE IF NOT EXISTS `auth_admins` (
    `id`            INT(10) UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '管理员ID',
    `username`      VARCHAR(50)      NOT NULL                COMMENT '用户名',
    `password_hash` VARCHAR(255)     NOT NULL                COMMENT '密码哈希',
    `nickname`      VARCHAR(50)      NOT NULL DEFAULT ''     COMMENT '昵称',
    `is_super`      TINYINT(1)       NOT NULL DEFAULT 0      COMMENT '是否超管 1-是 0-否',
    `is_active`     TINYINT(1)       NOT NULL DEFAULT 1      COMMENT '是否启用 1-启用 0-禁用',
    `created_at`    DATETIME         NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_at`    DATETIME         NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_username` (`username`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='后台管理员表';


-- ============================================
-- 4. 后台管理员 Token 表
-- ============================================

CREATE TABLE IF NOT EXISTS `admin_tokens` (
    `id`         INT(11)      NOT NULL AUTO_INCREMENT COMMENT 'id',
    `admin_id`   INT(11)      NOT NULL                 COMMENT '管理员ID',
    `token`      VARCHAR(64)  NOT NULL                 COMMENT '登录Token',
    `expires_at` DATETIME     NOT NULL                 COMMENT '过期时间',
    `is_active`  TINYINT(1)   NOT NULL DEFAULT 1       COMMENT '是否有效',
    `created_at` DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_at` DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_token` (`token`),
    KEY `idx_admin_id` (`admin_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='后台管理员Token';


-- ============================================
-- 5. AI 对话记录表
-- ============================================

CREATE TABLE IF NOT EXISTS `ai_chat_log` (
    `id`          INT(11)      NOT NULL AUTO_INCREMENT COMMENT 'id',
    `user_id`     INT(11)      NOT NULL DEFAULT 0       COMMENT '用户ID',
    `model_id`    INT(11)      NOT NULL DEFAULT 0       COMMENT '模型类型',
    `chat`        JSON         NOT NULL                 COMMENT '聊天消息JSON',
    `create_time` DATETIME     DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `update_time` DATETIME     DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='AI聊天记录';


-- ============================================
-- 6. 验证码表
-- ============================================

CREATE TABLE IF NOT EXISTS `verification_codes` (
    `id`         INT(11)      NOT NULL AUTO_INCREMENT COMMENT 'id',
    `email`      VARCHAR(255) NOT NULL                 COMMENT '邮箱',
    `code`       VARCHAR(6)   NOT NULL                 COMMENT '6位验证码',
    `purpose`    VARCHAR(50)  NOT NULL DEFAULT 'password_reset' COMMENT '用途',
    `expires_at` DATETIME     NOT NULL                 COMMENT '过期时间',
    `used`       TINYINT(1)   NOT NULL DEFAULT 0       COMMENT '是否已使用',
    `created_at` DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    PRIMARY KEY (`id`),
    KEY `idx_email` (`email`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='验证码表';


-- ============================================
-- 7. 附件/文件上传记录表
-- ============================================

CREATE TABLE IF NOT EXISTS `attachment` (
    `id`            INT(11)      NOT NULL AUTO_INCREMENT COMMENT '文件ID',
    `user_id`       INT(11)      NOT NULL                 COMMENT '上传用户ID',
    `original_name` VARCHAR(255) NOT NULL                 COMMENT '原始文件名',
    `stored_name`   VARCHAR(255) NOT NULL                 COMMENT '存储文件名',
    `file_path`     VARCHAR(500) NOT NULL                 COMMENT '文件相对路径',
    `file_size`     INT(11)      NOT NULL                 COMMENT '文件大小（字节）',
    `mime_type`     VARCHAR(100) NOT NULL                 COMMENT 'MIME 类型',
    `file_type`     VARCHAR(20)  NOT NULL                 COMMENT '文件分类：image / video / other',
    `created_at`    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '上传时间',
    PRIMARY KEY (`id`),
    KEY `idx_user_id` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='附件/文件上传记录表';


-- ============================================
-- 8. 抽奖配置表
-- ============================================

CREATE TABLE IF NOT EXISTS `lottery_configs` (
    `id`          INT             NOT NULL AUTO_INCREMENT COMMENT '主键',
    `scene_key`   VARCHAR(100)    NOT NULL                COMMENT '场景标识（唯一），如 sign_reward / recharge / daily_free',
    `name`        VARCHAR(100)    NOT NULL DEFAULT ''     COMMENT '场景名称（后台展示用）',
    `config_json` JSON            NOT NULL                COMMENT '完整抽奖配置，JSON 结构见下方',
    `status`      TINYINT(1)      NOT NULL DEFAULT 1      COMMENT '1=启用 0=禁用',
    `created_at`  DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at`  DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_scene_key` (`scene_key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='抽奖配置表';

INSERT INTO `lottery_configs` (`scene_key`, `name`, `config_json`) VALUES
('default', '通用奖池配置', '{\n  "mode": "pool",\n  "pool": [\n    {"prize_id": "cash_red_packet", "type": "cash",     "v": 40, "money": [0.5, 5]},\n    {"prize_id": "gift_001",        "type": "prop",     "v": 30, "props": {"id": "gift_001", "name": "金币"}},\n    {"prize_id": "score_pack",      "type": "score",    "v": 20, "money": [10, 100]},\n    {"prize_id": "speaker_001",     "type": "physical", "v": 5,  "props": {"name": "蓝牙音箱", "image": "https://...", "need_address": true}},\n    {"prize_id": "coupon_1001",     "type": "coupon",   "v": 5,  "props": {"coupon_id": 1001, "amount": 10}}\n  ]\n}')
ON DUPLICATE KEY UPDATE `id` = `id`;


-- ============================================
-- 9. RBAC — 权限目录表
-- ============================================

CREATE TABLE IF NOT EXISTS `auth_permissions` (
    `id`          INT(11)      NOT NULL AUTO_INCREMENT COMMENT '权限ID',
    `resource`    VARCHAR(50)  NOT NULL                 COMMENT '资源名（如 user / role / permission）',
    `action`      VARCHAR(50)  NOT NULL                 COMMENT '操作名（如 list / create / delete）',
    `description` VARCHAR(255) DEFAULT NULL             COMMENT '中文说明（如 "查看用户列表"）',
    `created_at`  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    PRIMARY KEY (`id`),
    KEY `idx_resource_action` (`resource`, `action`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='权限目录表';


-- ============================================
-- 10. RBAC — 角色定义表
-- ============================================

CREATE TABLE IF NOT EXISTS `auth_roles` (
    `id`          INT(11)      NOT NULL AUTO_INCREMENT COMMENT '角色ID',
    `name`        VARCHAR(50)  NOT NULL                 COMMENT '角色名（与 casbin_rule.v0 对应）',
    `description` VARCHAR(255) DEFAULT NULL             COMMENT '角色描述',
    `is_system`   TINYINT(1)   NOT NULL DEFAULT 0       COMMENT '系统内置角色（不可删除）',
    `created_at`  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_at`  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_name` (`name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='角色定义表';


-- ============================================
-- 11. RBAC — Casbin 策略规则表
-- ============================================

CREATE TABLE IF NOT EXISTS `auth_casbin_rule` (
    `id`    INT(11)      NOT NULL AUTO_INCREMENT COMMENT '主键',
    `ptype` VARCHAR(10)  NOT NULL                 COMMENT '策略类型：p=权限, g=角色归属',
    `v0`    VARCHAR(100) NOT NULL                 COMMENT 'sub：主体（角色名 或 用户ID）',
    `v1`    VARCHAR(100) NOT NULL                 COMMENT 'obj：客体（资源名，或 g 时的角色名）',
    `v2`    VARCHAR(100) DEFAULT ''               COMMENT 'act：操作（如 list / create / delete）',
    `v3`    VARCHAR(100) DEFAULT ''               COMMENT '预留字段',
    `v4`    VARCHAR(100) DEFAULT ''               COMMENT '预留字段',
    `v5`    VARCHAR(100) DEFAULT ''               COMMENT '预留字段',
    PRIMARY KEY (`id`),
    KEY `idx_ptype` (`ptype`),
    KEY `idx_v0` (`v0`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Casbin 策略规则表';


-- ============================================
-- 初始化数据 — RBAC 默认权限与角色
-- ============================================

INSERT INTO `auth_permissions` (`resource`, `action`, `description`) VALUES
('user',       'list',   '查看用户列表'),
('user',       'read',   '查看用户详情'),
('user',       'update', '更新用户信息'),
('user',       'delete', '强制注销用户'),
('user',       'disable','禁用用户'),
('user',       'enable', '启用用户'),
('user',       'cleanup','清理过期Token'),
('role',       'list',   '查看角色列表'),
('role',       'read',   '查看角色详情'),
('role',       'create', '创建角色'),
('role',       'update', '更新角色'),
('role',       'delete', '删除角色'),
('permission', 'list',   '查看权限目录'),
('permission', 'create', '创建权限条目'),
('permission', 'delete', '删除权限条目'),
('permission', 'assign', '分配/移除角色权限'),
('user_role',  'list',   '查看用户角色'),
('user_role',  'assign', '分配/移除用户角色'),
('admin',      'create', '创建管理员')
ON DUPLICATE KEY UPDATE `id` = `id`;


INSERT INTO `auth_roles` (`name`, `description`, `is_system`) VALUES
('admin',  '超级管理员（拥有全部权限）', 1),
('editor', '内容编辑员',                0)
ON DUPLICATE KEY UPDATE `id` = `id`;


-- admin 角色：分配所有权限
INSERT INTO `auth_casbin_rule` (`ptype`, `v0`, `v1`, `v2`) VALUES
('p', 'admin',   'permission', 'assign'),
('p', 'admin',   'permission', 'create'),
('p', 'admin',   'permission', 'delete'),
('p', 'admin',   'permission', 'list'),
('p', 'admin',   'role',       'create'),
('p', 'admin',   'role',       'delete'),
('p', 'admin',   'role',       'list'),
('p', 'admin',   'role',       'read'),
('p', 'admin',   'role',       'update'),
('p', 'admin',   'user',       'cleanup'),
('p', 'admin',   'user',       'delete'),
('p', 'admin',   'user',       'disable'),
('p', 'admin',   'user',       'enable'),
('p', 'admin',   'user',       'list'),
('p', 'admin',   'user',       'read'),
('p', 'admin',   'user',       'update'),
('p', 'admin',   'user_role',  'assign'),
('p', 'admin',   'user_role',  'list')
ON DUPLICATE KEY UPDATE `id` = `id`;

-- editor 角色：只可查看用户列表和详情
INSERT INTO `auth_casbin_rule` (`ptype`, `v0`, `v1`, `v2`) VALUES
('p', 'editor',  'user',       'list'),
('p', 'editor',  'user',       'read')
ON DUPLICATE KEY UPDATE `id` = `id`;


-- ============================================
-- 默认后台管理员账号
-- ============================================

-- 密码: admin123（bcrypt 哈希）
INSERT INTO `auth_admins` (`username`, `password_hash`, `nickname`, `is_super`, `is_active`) VALUES
('admin', '$2b$12$E0W/N3io5miOg1yqljORVu8x.xWhGR7r.wMAavb6lqTGlZ3bct9Sa', '超级管理员', 1, 1)
ON DUPLICATE KEY UPDATE `id` = `id`;

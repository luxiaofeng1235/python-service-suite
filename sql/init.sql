-- ============================================
-- FastAPI AI Service - 数据库初始化脚本
-- 目标数据库: fastapi_ai (MySQL 8.0+)
-- 编码: utf8mb4
-- ============================================

-- 创建数据库（如果尚未创建）
-- CREATE DATABASE IF NOT EXISTS fastapi_ai
--     DEFAULT CHARACTER SET utf8mb4
--     DEFAULT COLLATE utf8mb4_unicode_ci;

-- ==================== 用户表 ====================
CREATE TABLE IF NOT EXISTS `users` (
    `id`            INT             NOT NULL AUTO_INCREMENT  COMMENT '用户ID（主键）',
    `username`      VARCHAR(50)     NOT NULL                 COMMENT '用户名（唯一）',
    `password_hash` VARCHAR(255)    NOT NULL                 COMMENT '密码哈希',
    `nickname`      VARCHAR(50)     DEFAULT NULL             COMMENT '昵称',
    `email`         VARCHAR(255)    DEFAULT NULL             COMMENT '电子邮箱',
    `is_super`      TINYINT(1)      NOT NULL DEFAULT 0       COMMENT '是否管理员 1-是 0-否',
    `is_active`     TINYINT(1)      NOT NULL DEFAULT 1       COMMENT '是否启用 1-启用 0-禁用',
    `created_at`    DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_at`    DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_username` (`username`),
    KEY `idx_created_at` (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='用户表';

-- ==================== 验证码表 ====================
CREATE TABLE IF NOT EXISTS `verification_codes` (
    `id`         INT          NOT NULL AUTO_INCREMENT COMMENT 'id',
    `email`      VARCHAR(255) NOT NULL COMMENT '邮箱',
    `code`       VARCHAR(6)   NOT NULL COMMENT '6位验证码',
    `purpose`    VARCHAR(50)  NOT NULL DEFAULT 'password_reset' COMMENT '用途',
    `expires_at` DATETIME     NOT NULL COMMENT '过期时间',
    `used`       TINYINT(1)   NOT NULL DEFAULT 0 COMMENT '是否已使用',
    `created_at` DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    PRIMARY KEY (`id`),
    KEY `idx_email` (`email`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='验证码表';

-- ==================== AI 对话记录表 ====================
CREATE TABLE IF NOT EXISTS `ai_chat_log` (
    `id`          INT          NOT NULL AUTO_INCREMENT COMMENT 'id',
    `user_id`     INT          NOT NULL COMMENT '用户id',
    `model_id`    INT          NOT NULL COMMENT '模型id',
    `chat`        JSON         NOT NULL COMMENT '聊天记录',
    `create_time` DATETIME     DEFAULT NULL COMMENT '创建时间',
    `update_time` DATETIME     DEFAULT NULL COMMENT '更新时间',
    PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='ai聊天记录';

-- ==================== 用户登录 Token 表 ====================
CREATE TABLE IF NOT EXISTS `user_tokens` (
    `id`         INT          NOT NULL AUTO_INCREMENT COMMENT 'id',
    `user_id`    INT          NOT NULL COMMENT '用户ID',
    `token`      VARCHAR(64)  NOT NULL COMMENT '登录Token',
    `expires_at` DATETIME     NOT NULL COMMENT '过期时间',
    `is_active`  TINYINT(1)   NOT NULL DEFAULT 1 COMMENT '是否有效',
    `created_at` DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_at` DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_token` (`token`),
    KEY `idx_user_id` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='用户登录Token';

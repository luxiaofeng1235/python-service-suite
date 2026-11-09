-- 文生图任务表，与现有 PHP ai_to_work 表结构保持一致。
-- 已有此表时不需要重复执行，不会修改已有表或重置自增序号。
CREATE TABLE IF NOT EXISTS `ai_to_work` (
    `id` INT NOT NULL AUTO_INCREMENT COMMENT 'id',
    `user_id` INT NOT NULL COMMENT '用户id',
    `task_id` VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci DEFAULT NULL COMMENT '任务id',
    `params` JSON NOT NULL COMMENT '生成参数',
    `work` JSON DEFAULT NULL COMMENT '作品',
    `type` TINYINT(1) DEFAULT '1' COMMENT '1图片，2视频',
    `status` TINYINT(1) DEFAULT '0' COMMENT '类型，0生成中，1已生成，2生成失败，3已删除',
    `create_time` DATETIME DEFAULT NULL,
    `update_time` DATETIME DEFAULT NULL,
    PRIMARY KEY (`id`) USING BTREE,
    UNIQUE KEY `task_id` (`task_id`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='ai作品表';

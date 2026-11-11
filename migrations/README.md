# 数据库迁移

项目使用 Alembic 管理表结构变更。

常用命令：

```bash
alembic upgrade head
alembic current
alembic revision --autogenerate -m "change description"
```

迁移连接从 `.env` 的 `DATABASE_URL` 读取。业务运行仍使用 async 驱动，迁移时会自动转换为同步驱动。

2026-11-11 修复：保留已部署 revision 编号，自动将 MySQL `alembic_version.version_num` 扩至 64 字符，兼容历史 37 字符编号。CMS 迁移兼容已有 `tag_ids` 字段；新增修复迁移补建缺失的 AI 任务、对话、CMS 标签、抽奖配置表以及用户登录字段，不覆盖已有业务记录。

已有数据库先查看 `alembic current`，备份后执行 `alembic upgrade head`；空数据库可直接完整升级。不要对已有数据的数据库执行 `stamp head` 代替结构迁移。修复迁移无法区分原有表和新建表，因此禁止自动降级，回退需恢复备份。

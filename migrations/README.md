# 数据库迁移

项目使用 Alembic 管理表结构变更。

常用命令：

```bash
alembic upgrade head
alembic revision --autogenerate -m "change description"
```

迁移连接从 `.env` 的 `DATABASE_URL` 读取。业务运行仍使用 async 驱动，迁移时会自动转换为同步驱动。

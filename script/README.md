# Model / Schema 代码生成器

配置文件固定默认读取项目根目录的 `generator.yaml`，`script/` 仅保存工具代码与模板。
数据库连接复用 `.env` 的 `DATABASE_URL`，目前只支持 MySQL 普通表。

工具保留四个功能模块：`codegen.py` 负责 CLI 和文件写入，`configuration.py` 负责配置，`database_reader.py` 负责读表，`rendering.py` 负责渲染。表结构与生成计划的数据类定义在各自使用的模块中，模板放在 `templates/`。

在项目根目录、已安装项目依赖的 Python 环境执行：

```bash
# 只预览；仍会连接数据库读取表结构，不写文件。
python -m script.codegen --table demo_articles --dry-run

# 生成 Model 与 Schema；表名替换成自己已经建好的表。
python -m script.codegen --table demo_articles

# 指定另一个配置文件，文件内输出目录仍相对项目根目录解析。
python -m script.codegen --config generator.yaml --table demo_articles
```

默认生成 `app/models/demo_article.py` 与 `app/schemas/demo_article.py`，包含中文文件头、类说明、字段说明，以及 `DemoArticle`、`DemoArticleCreateRequest`、`DemoArticleUpdateRequest`、`DemoArticleResponse`。

- 目录、ORM 基类、命名映射、Schema 类型及排除字段在 YAML 维护，不规则复数请显式设置 `naming.overrides`。
- 任一目标文件、同名类或同表映射已经存在，默认整组跳过；`on_exists: error` 则返回错误。没有覆盖选项，已生成文件由开发者维护。
- Model 保留数据库类型、主键、自增、索引、默认值及约束，不增加数据库中没有的索引或自动更新时间规则。
- Schema 只生成数据库能确定的基础约束。创建或更新时使用 `req.model_dump(exclude_unset=True)`，省略的值由数据库默认值处理；明确提交 `null` 时，数据库非空字段会拒绝。
- 自增及计算字段不进入请求；响应默认排除 YAML 列出的密码和令牌字段。业务验证、权限、响应字段及序列化格式需要人工完善。
- 不会生成 Service、Controller、路由或迁移，不执行建表、改表、数据查询与写入。未知类型、缺少主键或保留名称冲突会报错。
- 开启注册后只向目标目录 `__init__.py` 追加导入。自定义 Model 包需要被应用和 Alembic 环境导入，才能进入共享 `Base.metadata`。
- `script/.codegen.lock` 防止两个生成进程同时追加导入；进程被强制结束后，确认没有生成器运行再手动清理残留锁和未完成产物。

已通过 `ai_demo_class` 表完成实际预览和正式生成验证；业务校验和接口逻辑仍需开发者补充。

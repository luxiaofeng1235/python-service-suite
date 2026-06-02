# 项目里程碑

> FastAPI AI Service 当前建设进度与后续路线图。
> 更新时间：2026-07-13，按重构后代码结构整理。

---

## 当前定位

项目已从"AI 接口 Demo"演进为**前后台分离的企业级 FastAPI 脚手架**：

- 前台接口（`app/api/`）面向普通用户，提供注册登录、AI 对话、文件上传等
- 后台管理（`app/admin/`）面向管理员，提供 RBAC 权限、用户管理等
- 后台管理员使用独立 `auth_admins` 表，与前台 `users` 完全隔离
- 新增业务模块只需：Model → Service → Controller → 路由注册

---

## M1：基础脚手架闭环（已完成）

| 模块 | 内容 | 状态 |
|------|------|------|
| 项目结构 | 前后台分离：`app/api/` + `app/admin/` + `app/routes/` | 已完成 |
| 三层架构 | Controller → Service → Model，前后台各用各的 | 已完成 |
| 请求/响应模型 | Pydantic Schema 统一放在 `app/schemas` | 已完成 |
| 统一响应 | `Response.success/fail/error`，`_serialize` 支持 ORM 自动序列化 | 已完成 |
| 全局异常 | 业务异常、参数校验异常、HTTP 异常、兜底异常 | 已完成 |
| Swagger 文档 | `/docs`、`/redoc` 自动生成 | 已完成 |
| 配置管理 | `.env` + `app/core/config.py` | 已完成 |
| 路由聚合 | 前台走 `routes/api.py`，后台走 `routes/admin.py` | 已完成 |

---

## M2：用户与权限体系（已完成）

### 前台用户系统（`/api/user/*`）

| 模块 | 内容 | 状态 |
|------|------|------|
| 用户注册 | 用户名唯一校验、密码加密、用户入库 | 已完成 |
| 用户登录 | 生成 32 位短 Token，写入 `user_tokens` | 已完成 |
| Token 鉴权 | `get_current_user` 注入当前用户 | 已完成 |
| 免登录白名单 | `AUTH_WHITE_LIST` 统一配置 | 已完成 |
| 退出登录 | Token 立即失效 | 已完成 |
| 过期 Token 清理 | 管理员接口清理 | 已完成 |
| 账号注销 | 软删除用户并清空 Token | 已完成 |
| 忘记密码 | 邮箱验证码 + Redis 缓存 + DB 兜底 | 已完成 |

### 后台管理员系统（`/admin/auth/*`）

| 模块 | 内容 | 状态 |
|------|------|------|
| 独立管理员表 | `auth_admins`，与前台 `users` 完全分离 | 已完成 |
| 独立 Token 表 | `admin_tokens`，与前台 `user_tokens` 分离 | 已完成 |
| 管理员登录 | `/admin/auth/login`，读取 `auth_admins` 表 | 已完成 |
| 管理员注册 | `/admin/auth/register`，超管创建 | 已完成 |
| 管理员退出 | `/admin/auth/logout` | 已完成 |
| 管理员鉴权 | `get_current_admin_user` 独立依赖 | 已完成 |
| 禁用/启用 | `/admin/admins/{id}/toggle-active`，不可自禁，不可禁超管 | 已完成 |

### RBAC 权限体系（`/admin/*`）

| 模块 | 内容 | 状态 |
|------|------|------|
| 权限目录 | `auth_permissions` 表，resource + action | 已完成 |
| 角色管理 | `auth_roles` 表，含系统内置保护 | 已完成 |
| Casbin 规则 | `auth_casbin_rule`：角色-权限（`p`）+ 管理员-角色（`g`） | 已完成 |
| 权限校验 | `require_permission(resource, action)` 依赖工厂 | 已完成 |
| 超管直通 | `is_super=True` 跳过权限校验 | 已完成 |
| 后台用户管理 | 前台用户的列表/详情/更新/禁用/启用/删除 | 已完成 |
| 管理员列表 | `/admin/admins/list` | 已完成 |

---

## M3：AI 对话能力（已完成基础版）

| 模块 | 内容 | 状态 |
|------|------|------|
| 千问接入 | OpenAI 兼容协议调用 DashScope 千问 | 已完成 |
| 普通对话 | `/api/ai/chat` 返回完整回复 | 已完成 |
| SSE 流式输出 | `/api/ai/chat/send_stream_sse` 分片返回 | 已完成 |
| 上下文关联 | `chat_id=0` 新建，非 0 按历史上下文组装 | 已完成 |
| 对话记录 | `ai_chat_log` 保存用户消息和 AI 回复 | 已完成 |
| 对话列表/详情 | `/api/ai/chats`、`/api/ai/chats/{chat_id}` | 已完成 |
| 删除对话 | `DELETE /api/ai/chats/{chat_id}` | 已完成 |

## M4：文件与静态资源（已完成基础版）

| 模块 | 内容 | 状态 |
|------|------|------|
| 图片上传 | `/api/file/upload/image`，无需登录 | 已完成 |
| 视频上传 | `/api/file/upload/video`，无需登录 | 已完成 |
| 文件列表 | `/api/file/list` 分页返回附件 | 已完成 |
| 附件表 | `attachment` 表 | 已完成 |
| 本地静态访问 | `/uploads/**` 映射上传目录 | 已完成 |
| 配置化限制 | 格式、大小从配置读取 | 已完成 |

---

## M5：数据库与缓存（已完成基础版）

| 模块 | 内容 | 状态 |
|------|------|------|
| SQLAlchemy Async | 异步 ORM 会话管理 | 已完成 |
| MySQL 支持 | `mysql+aiomysql` 连接 | 已完成 |
| Alembic 迁移 | 版本化管理表结构 | 已完成 |
| Redis 集成 | 启动时初始化，失败不阻塞 | 已完成 |
| 验证码缓存 | Redis + DB 双保险 | 已完成 |

---

## M6：日志与可观测性（已完成基础版）

| 模块 | 内容 | 状态 |
|------|------|------|
| 请求日志中间件 | method、path、status、cost、client_ip | 已完成 |
| Trace ID | 响应头返回 `X-Trace-Id` | 已完成 |
| 耗时统计 | 响应头返回 `X-Process-Time` | 已完成 |
| 慢请求日志 | 超过 `SLOW_REQUEST_MS` 单独记录 | 已完成 |
| 日志文件 | 应用日志、请求日志、慢请求日志分文件 | 已完成 |
| 敏感参数脱敏 | password、token、authorization 等字段脱敏 | 已完成 |

---

## M7：部署与工程化（已完成基础版）

| 模块 | 内容 | 状态 |
|------|------|------|
| Dockerfile | 镜像构建 | 已完成 |
| docker-compose | app + mysql + redis 编排 | 已完成 |
| Makefile | dev、build、docker、alembic 常用命令 | 已完成 |
| Ruff | 代码格式化与检查配置 | 已完成 |
| `.env.example` | 环境变量模板 | 已完成 |

---

## 后续规划

| 方向 | 内容 | 优先级 |
|------|------|--------|
| 测试用例 | Service 单测、API 集成测试 | P0 |
| Redis 限流 | 登录、验证码、AI 调用频控 | P0 |
| AI 多模型配置 | 模型、system prompt 从 DB 动态维护 | P1 |
| 操作日志 | 管理员操作审计日志 | P1 |
| RAG 知识库 | 文档入库、切片、向量检索 | P1 |
| Agent 路由 | 意图识别分发到不同业务 Service | P1 |
| CI/CD | 自动检查、自动测试、自动部署 | P1 |

## 状态图例

- **已完成**：当前代码已具备该能力
- **P0**：近期必须做
- **P1**：重要但可排在 P0 之后
- **P2**：增强项，等主链路稳定后再做

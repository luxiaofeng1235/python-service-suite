# FastAPI AI Service — 企业级 AI 接口服务脚手架

> **不仅是一个 AI 服务框架，更是一套通用的企业级后端脚手架**。基于 FastAPI 三层架构，内置用户鉴权、SSE 流式输出、OpenAI 兼容接口（当前接入千问，可扩展 DeepSeek / OpenAI 等任意兼容服务）、对话管理全链路。  
> 无论是搭建 **AI 聊天助手、电商后台、内容管理系统、SaaS 平台、API 网关**，还是星座/命理等垂直领域应用，这套脚手架都能让你**半天内完成核心模块落地，专注于业务逻辑，而非基础设施**。

---

## 特性概览

| 能力 | 说明 |
|------|------|
| **三层架构** | Controller → Service → Model 清晰分层，业务代码与基础设施解耦 |
| **用户鉴权体系** | 注册/登录/Token 鉴权/管理员/密码找回，开箱即用 |
| **AI 模型接入** | OpenAI 兼容接口，当前接入千问，后续可扩展 DeepSeek / OpenAI 等任意兼容服务 |
| **SSE 流式输出** | 标准 Server-Sent Events，兼容旧协议，前端直接对接 |
| **对话管理** | 完整 CRUD + 上下文清除 + 重生成，按用户隔离 |
| **数据库迁移** | Alembic 管理表结构变更，开发用 SQLite，生产切 MySQL |
| **Docker 一键部署** | 本地 SQLite 开发 / 生产 MySQL 集群，Makefile 一条命令搞定 |
| **统一响应格式** | 所有接口返回统一 JSON 结构，前端对接无歧义 |
| **日志系统** | 基于 loguru 按业务域分流，对标 Go 版多全局 Logger 的写法，开箱即用 |

---

## 快速落地一个业务模块

这套脚手架的设计目标就是让你**半天内从零到一完成一个新业务模块**，无论它是 AI 接口还是传统 CRUD。

```text
1. 在 app/models/ 下新建 xxx.py —— 定义数据库模型（如需新表，跑 alembic 迁移）
2. 在 app/<模块>/services/ 下新建 xxx_service.py —— 写业务逻辑
3. 在 app/<模块>/controllers/ 下新建 xxx_controller.py —— 注册路由
4. 在 app/routes/<模块>.py 中 include_router —— 挂接到主服务
5. ✅ 重启服务，接口可用
```

> - 前台接口 → 放在 `app/api/` 下，路由注册到 `app/routes/api.py`
> - 后台管理 → 放在 `app/admin/` 下，路由注册到 `app/routes/admin.py`

> 鉴权、数据库、流式输出、统一响应格式、日志追踪全都不用自己写。

**这套脚手架适用于以下场景：**

| 业务场景 | 典型模块 | 复用能力 |
|---------|---------|---------|
| 🛒 **电商平台** | 商品管理、订单系统、购物车、支付回调、物流查询 | 鉴权体系、日志追踪、数据库迁移、统一响应 |
| 📝 **内容管理 (CMS)** | 文章发布、分类管理、评论审核、标签系统、SEO 接口 | 用户权限（管理员/普通用户）、分页查询、统一响应 |
| 💼 **SaaS 平台** | 租户管理、套餐订阅、用量统计、API Key 管理 | 多层权限（get_current_admin/get_current_user）、Token 鉴权 |
| 🏪 **API 网关** | 第三方接入鉴权、接口限流、数据聚合、协议转换 | 中间件机制、AUTH_WHITE_LIST 免鉴白名单 |
| 💬 **AI 应用** | 聊天助手、知识库问答、内容生成、意图识别 | SSE 流式输出、模型配置、对话管理全链路 |

无论你的业务类型是什么，新增模块只需要四刀——**Model + Service + Controller + 路由注册**，其余基础设施全部就绪。

---

## 架构分层

```
前台 (app/api/)                 后台 (app/admin/)
    │                                 │
Controller → Service → Model    Controller → Service → Model
                                   (RBAC 权限)
                                       │
                                   auth_admins (独立表)
```

| 层 | 职责 | 前台示例 | 后台示例 |
|----|------|---------|---------|
| **Controller** | 路由定义、参数校验、返回响应 | `api/controllers/user_controller.py` | `admin/controllers/rbac_controller.py` |
| **Service** | 核心业务逻辑 | `api/services/user_service.py` | `admin/services/auth_service.py` |
| **Model (ORM)** | 数据库表映射 | `app/models/user.py` | `app/models/auth_admin.py` |
| **Schema** | Pydantic 请求/响应体 | `app/schemas/user.py` | `app/schemas/auth_admin.py` |
| **Route** | 路由聚合 | `app/routes/api.py` | `app/routes/admin.py` |

**关键约定**：
- 前台 (`app/api/`) 和后台 (`app/admin/`) 完全隔离，各用各的 controller + service
- 业务逻辑只放在 Service 层，Controller 不做任何数据操作
- 后台 RBAC 使用独立的 `auth_admins` + `admin_tokens` 表，与前台 `users` 体系无关

---

## 目录结构

```
app/
├── main.py                  # 入口 — app 工厂、中间件、路由挂载
│
├── routes/                  # 路由聚合入口
│   ├── api.py               # 前台接口路由（app/api/controllers）
│   └── admin.py             # 后台管理路由（app/admin/controllers）
│
├── setup/                   # 应用启动配置
│   ├── lifecycle.py         # 启动/关闭生命周期钩子
│   └── routes.py            # 统一注册前台+后台路由
│
├── api/                     # 前台接口层（面向普通用户）
│   ├── controllers/         # 前台路由控制器
│   │   ├── user_controller.py
│   │   ├── ai_controller.py
│   │   ├── file_controller.py
│   │   ├── tools_controller.py
│   │   └── test_controller.py
│   └── services/            # 前台业务逻辑
│       ├── user_service.py
│       ├── ai_service.py
│       └── file_service.py
│
├── admin/                   # 后台管理层（面向管理员）
│   ├── controllers/         # 后台路由控制器
│   │   ├── auth_controller.py       # 管理员认证（login/register/logout/me）
│   │   ├── admin_controller.py      # 管理员管理（列表/禁用启用）
│   │   ├── user_admin_controller.py # 前台用户管理（后台视角）
│   │   └── rbac_controller.py       # RBAC 权限管理
│   └── services/            # 后台业务逻辑
│       ├── auth_service.py          # 管理员认证服务
│       └── user_admin_service.py    # 前台用户管理服务
│
├── core/                    # 核心基础设施（改配置就够了）
│   ├── config.py            # 集中配置管理，从 .env 读取
│   ├── security.py          # Token 签发/验证/密码加密
│   ├── dependency.py        # 前台鉴权依赖：get_current_user
│   ├── admin_auth.py        # 后台鉴权依赖：get_current_admin_user
│   └── rbac.py              # RBAC 鉴权依赖工厂：require_permission
│
├── common/                  # 通用工具
│   ├── response.py          # 统一响应格式 Response.success / Response.fail
│   ├── exception.py         # 全局异常处理器
│   ├── pagination.py        # 分页查询工具
│   └── sse.py               # SSE 流式响应工具
│
├── models/                  # ORM 数据模型
│   ├── user.py              # 前台用户表
│   ├── user_token.py        # 前台用户 Token 表
│   ├── verification_code.py # 验证码表
│   ├── ai_chat_log.py       # AI 对话日志表
│   ├── attachment.py        # 文件附件表
│   ├── rbac.py              # RBAC 权限/角色/CasbinRule 表
│   ├── auth_admin.py        # 后台管理员表（独立于 users）
│   └── admin_token.py       # 后台管理员 Token 表
│
├── schemas/                 # Pydantic 请求/响应模型
│   ├── ai.py                # AI 对话请求/响应体
│   ├── user.py              # 用户注册/登录/密码重置
│   ├── user_admin.py        # 后台用户管理请求/响应
│   ├── auth_admin.py        # 管理员登录/注册请求体
│   ├── rbac.py              # RBAC 请求/响应体
│   ├── file.py              # 文件上传响应体
│   └── storage.py           # 存储验证
│
├── storage/                 # 文件存储
│   └── validation.py        # 文件上传验证规则
│
├── utils/                   # 辅助工具
│   └── email.py             # SMTP 邮件发送（验证码、通知）
│
├── web/                     # 预留 Web 业务模块
│   └── README.md
│
├── database.py              # 数据库引擎 & 会话管理
│
└── migrations/              # Alembic 迁移脚本
    ├── versions/
    └── env.py
```

**新增模块只需四步**：创建 `model`（如需新表）→ 创建 `service` → 创建 `controller` → 在 `routes/api.py` 或 `routes/admin.py` 注册。

---

## 依赖说明

| 依赖 | 说明 |
|------|------|
| `fastapi` | Web 框架 |
| `uvicorn[standard]` | ASGI 服务器 |
| `pydantic` | 数据验证 |
| `pydantic-settings` | 配置管理（从 .env 读取） |
| `python-jose[cryptography]` | JWT 令牌编码/解码 |
| `passlib[bcrypt]` / `bcrypt` | 密码哈希 |
| `python-multipart` | 文件上传解析 |
| `python-dotenv` | .env 文件加载 |
| `sse-starlette` | SSE 流式响应 |
| `aiosqlite` | SQLite 异步驱动（开发环境） |
| `sqlalchemy[asyncio]` | ORM 框架（异步） |
| `databases` | 异步数据库工具集 |
| `aiomysql` / `pymysql` | MySQL 异步驱动（生产环境） |
| `alembic` | 数据库迁移 |
| `ipip-ipdb` | IP 地址解析（ipip.net .ipdb 格式） |
| `loguru` | 日志框架（按业务域分流到独立文件） |

## 环境变量配置

在项目根目录创建 `.env` 文件：

```bash
cp .env.example .env
```

然后按本地环境填写数据库、SMTP、千问等配置。README 不展示任何真实密钥或密钥格式示例，敏感配置只放在本地 `.env` 中。

## 快速启动

```bash
# 1. 安装依赖
pip3 install -r requirements.txt

# 2. 配置环境变量
cp .env.example .env    # 从模板创建本地配置
# 编辑 .env 填入自己的密钥、邮箱授权码等敏感信息

# 3. 初始化或升级数据库
alembic upgrade head

# 4. 启动服务
cd /mnt/d/python_work/fastapi_server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

表结构变更统一用 Alembic 管理。`AUTO_CREATE_TABLES=True` 仅建议本地临时初始化使用测试。

## 里程碑

当前开发进度、已完成能力和后续计划统一维护在 [MILESTONE.md](/mnt/d/python_work/fastapi_server/MILESTONE.md)。

## Docker 部署

项目提供 Docker 与 docker-compose 一键部署，支持本地 SQLite 开发和生产 MySQL 集群。

### 前置条件

- Docker & Docker Compose v2+

### 1. 本地开发（SQLite，无外部依赖）

```bash
# 1. 构建镜像
make build

# 2. 启动（仅 app 服务）
docker compose up -d app --no-deps

# 3. 初始化数据库
make alembic-upgrade
```

> 本地 SQLite 开发无需 MySQL/Redis，用 `--no-deps` 跳过依赖服务。

### 2. 生产部署（MySQL + Redis）

```bash
# 1. 修改 .env 数据库连接为 MySQL
# DATABASE_URL=mysql+aiomysql://root:root123@mysql:3306/fastapi_ai?charset=utf8mb4

# 2. 启动全套服务
make docker-up

# 3. 初始化数据库（首次）
make alembic-upgrade

# 4. 查看日志
make docker-logs
```

> MySQL 首次启动会自动执行 `sql/init.sql` 初始化库表（如果卷为空）。

### 3. 常用 Docker 命令

```bash
make build           # 构建镜像
make docker-up       # 启动服务
make docker-down     # 停止服务
make docker-restart  # 重启
make docker-logs     # 查看日志
make docker-shell    # 进入容器
make docker-clean    # 清理全部（含数据卷）
```

### 4. 验证

```bash
curl http://localhost:8000/api/health
# 登录测试
curl -X POST http://localhost:8000/api/user/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"123456"}'
```

## Makefile 快速参考

```bash
make help            # 显示所有可用命令
make dev             # 本地热重载启动
make install         # 安装依赖
make lint            # 代码检查（ruff）
make format          # 代码格式化（ruff）
make alembic-upgrade # 数据库升级
make clean           # 清理缓存/tmp/log
```

## API 文档

启动后访问：
- Swagger UI：http://localhost:8000/docs
- ReDoc：http://localhost:8000/redoc

## AI 流式输出

当前仓库已接入 OpenAI 兼容接口，当前默认对接千问，开箱即用：

- `POST /api/ai/chat`：返回完整回复
- `POST /api/ai/chat/send_stream_sse`：返回 SSE 流式分片
- `GET /api/ai/chats`：对话列表（登录后按用户隔离）
- `GET /api/ai/chats/{chat_id}`：对话详情
- `DELETE /api/ai/chats/{chat_id}`：删除对话

请求体示例：

```json
{
  "model": 1,
  "chat_id": 0,
  "msg": "你好，帮我介绍一下这个服务",
  "restart": 0,
  "is_deep_reflection": 0
}
```

说明：

- 框架使用 OpenAI 兼容协议（`/v1/chat/completions`），接入 DeepSeek / 千问 / OpenAI 等任意兼容服务均可
- 需在 `.env` 中配置对应 API Key（默认变量名 `QWEN_API_KEY`，可自行扩展）
- `/api/ai/chat/send_stream_sse` 返回 `text/event-stream`
- AI 对话接口无需登录；如果携带登录 Token，会按当前用户保存和查询上下文
- 流式输出兼容旧协议：`data:` 直接返回增量文本
- 流结束时依次返回 `data: [LOG_ID]:<chat_id>` 和 `data: [DONE]`
- 深度思考片段返回 JSON 字符串：`{"type":"reasoning_content","data":"..."}`
- `chat_id=0` 表示新建对话；传已有 `chat_id` 表示续聊
- `restart=1` 表示重生成上一条 AI 回复
- `model` 取值为 `1`，对应千问 qwen-max

`curl` 示例：

```bash
curl -N \
  -H "Accept: text/event-stream" \
  -H "Content-Type: application/json" \
  -X POST http://localhost:8000/api/ai/chat/send_stream_sse \
  -d '{"model":1,"chat_id":0,"msg":"你好，介绍一下这个服务","restart":0}'
```

## LLM / RAG 待开发规划

架构链路：

```
Controller → 业务 Service (ConstellationService 等) → LangChain Agent / LangGraph → AIService → LLM 模型
```

各层职责：

| 层级 | 职责 |
|------|------|
| **Controller** | 参数校验、认证鉴权、路由分发 |
| **业务 Service** | 数据查询、业务规则、定价、权限校验，不拼 prompt、不调 LLM |
| **LangChain Agent / LangGraph** | 意图识别、知识检索、工具调用编排，通过 `@tool` 装饰器对接业务 Service |
| **AIService** | prompt 组装、上下文管理、流式输出、模型配置 |
| **LLM 模型** | 语义理解、自然语言生成、推理总结，不接触价格/权限/订单 |

全链路示例（星座问答）：

```text
用户：我是双鱼座，今天运势怎么样？
  ↓
Controller → ChatService
  ↓
LangChain Agent（意图识别 + 工具路由）
  ├── @tool: get_constellation_info  → 调用 ConstellationService（星座日期、星象、运势评分）
  ├── @tool: search_knowledge_base    → 调用 RagService（星座知识库检索）
  └── Agent 生成最终指令给 AIService
  ↓
AIService 组装 prompt → 调用 LLM（OpenAI 兼容接口）→ SSE 流式返回
```

设计原则：

1. **LLM 只做语义层** — 理解用户、组织语言，不碰核心数据/权限/支付
2. **Agent 不做业务决策** — 调 Service 拿数据，定价/权限由后端锁定
3. **业务 Service 是唯一数据源** — Agent/LLM 不直连数据库
4. **渐进引入** — 先简单意图路由 + RAG，复杂编排（LangGraph）按需接入

建议预留目录：

```
app/services/
├── constellation_service.py    # 星座业务（档案、星盘、运势计算）
├── rag_service.py              # 知识库检索（向量 + 关键词）
├── agent_router_service.py     # 意图路由分发
├── agents/
│   ├── base_agent.py           # Agent 基类
│   ├── constellation_agent.py  # 星座 Agent
│   ├── dream_agent.py          # 解梦 Agent
│   └── knowledge_agent.py      # 知识库问答 Agent
├── ai_service.py               # LLM 调用
└── prompt/
    ├── constellation.yaml
    ├── dream.yaml
    └── router.yaml
```

## 用户与权限

当前已预留的用户接口（`/api/user/*`）：

| 方法 | 路径 | 说明 | 登录要求 |
|------|------|------|---------|
| `POST` | `/api/user/register` | 用户注册 | 否 |
| `POST` | `/api/user/login` | 用户登录，返回 32 位短 Token | 否 |
| `POST` | `/api/user/logout` | 退出登录，使当前 Token 立即失效 | 是 |
| `POST` | `/api/user/forgot-password` | 忘记密码，发送验证码邮件 | 否 |
| `POST` | `/api/user/reset-password` | 重置密码，验证码 + 新密码 | 否 |
| `GET` | `/api/user/list` | 用户列表（分页），默认每页 10 条 | 是 |
| `GET` | `/api/user/me` | 获取当前登录用户信息 | 是 |
| `DELETE` | `/api/user/delete` | 注销当前账号（软删除） | 是 |
| `DELETE` | `/api/user/tokens/expired` | 清理过期 Token | 管理员 |

### 后台管理员认证（`/admin/auth/*`）

后台管理员使用独立的 `auth_admins` 表，与前台用户完全隔离：

| 方法 | 路径 | 说明 | 权限要求 |
|------|------|------|---------|
| `POST` | `/admin/auth/login` | 管理员登录 | 否 |
| `POST` | `/admin/auth/register` | 创建新管理员 | `admin:create` |
| `POST` | `/admin/auth/logout` | 退出登录 | 是 |
| `GET` | `/admin/auth/me` | 当前管理员信息 | 是 |

### RBAC 权限管理（`/admin/*`）

基于 Casbin 的 RBAC 权限体系，三张核心表：

| 表 | 说明 |
|----|------|
| `auth_permissions` | 权限目录（resource + action，如 `user:list`） |
| `auth_roles` | 角色（如 admin、editor） |
| `auth_casbin_rule` | 规则表：角色-权限映射 `p` + 管理员-角色绑定 `g` |

**权限校验流程**：

```
请求 → require_permission("user", "list")
         │
         ├─ 超管（is_super=True）→ ✅ 直通
         │
         └─ 普通管理员
              │
              └─ 查 CasbinRule：
                   g, admin_id, role_name  →  获取角色
                   p, role_name, resource, action  →  判断是否有权限
```

**已有后台管理接口**：

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| `GET` | `/admin/users/list` | 前台用户列表 | `user:list` |
| `GET` | `/admin/users/{id}` | 前台用户详情 | `user:read` |
| `PUT` | `/admin/users/{id}` | 更新前台用户 | `user:update` |
| `DELETE` | `/admin/users/{id}` | 强制注销前台用户 | `user:delete` |
| `POST` | `/admin/users/{id}/disable` | 禁用前台用户 | `user:disable` |
| `POST` | `/admin/users/{id}/enable` | 启用前台用户 | `user:enable` |
| `GET` | `/admin/permissions` | 权限目录列表 | `permission:list` |
| `POST` | `/admin/permissions` | 创建权限条目 | `permission:create` |
| `DELETE` | `/admin/permissions/{id}` | 删除权限条目 | `permission:delete` |
| `GET` | `/admin/roles` | 角色列表 | `role:list` |
| `POST` | `/admin/roles` | 创建角色 | `role:create` |
| `PUT` | `/admin/roles/{id}` | 更新角色 | `role:update` |
| `DELETE` | `/admin/roles/{id}` | 删除角色 | `role:delete` |
| `GET` | `/admin/roles/{id}/permissions` | 角色权限列表 | `permission:list` |
| `POST` | `/admin/roles/{id}/permissions` | 为角色分配权限 | `permission:assign` |
| `DELETE` | `/admin/roles/{id}/permissions` | 移除角色权限 | `permission:assign` |
| `GET` | `/admin/admins` | 管理员列表 | `admin:list` |
| `POST` | `/admin/admins/{id}/toggle-active` | 禁用/启用管理员 | `admin:toggle` |
| `GET` | `/admin/admins/{id}/roles` | 管理员的角色列表 | `user_role:list` |
| `POST` | `/admin/admins/{id}/roles` | 为管理员分配角色 | `user_role:assign` |
| `DELETE` | `/admin/admins/{id}/roles/{role_id}` | 移除管理员角色 | `user_role:assign` |

### 注册 / 登录

请求体示例：

```json
{
  "username": "test_user",
  "password": "12345677",
  "email": "test@example.com",
  "nickname": "测试用户"
}
```

登录成功后返回：

```json
{
  "code": 1,
  "msg": "登录成功",
  "data": {
    "access_token": "32位短Token",
    "token_type": "bearer"
  }
}
```

### 请求需登录接口

在 Header 中携带 Token：

```bash
curl -H "Authorization: Bearer <token>" http://localhost:8000/api/user/me
```

### 接口说明

- 注册时用户名 2-50 字符，密码 6-128 字符，邮箱、昵称可选
- Token 有效时长由 `.env` 的 `ACCESS_TOKEN_EXPIRE_MINUTES` 控制
- 退出登录立即失效当前 Token，不影响其他设备
- 忘记密码流程：`POST /api/user/forgot-password` 发邮件 → 查收 6 位验证码 → `POST /api/user/reset-password` 提交新密码
- `GET /api/user/list` 支持 `page` 和 `size` 参数，`size` 最大 100
- `DELETE /api/user/delete` 为软删除（标记 `is_deleted=True`），同时清空该用户所有 Token
- `DELETE /api/user/tokens/expired` 需 `users.is_super=1` 管理员权限
- 免登录路径由 `.env` 的 `AUTH_WHITE_LIST` 统一配置，逗号分隔

## 日志系统

基于 **loguru** 实现，对标 Go 版 `ZapLog.Pay.Info(...)` 的多全局 Logger 写法，按业务域自动分流到独立文件。

### 日志文件

启动后日志写入 `logs/` 目录：

| 文件 | 对应 Logger | 业务场景 |
|------|------------|---------|
| `logs/app.log` | `app_logger` | 通用业务日志 |
| `logs/request.log` | `request_logger` | HTTP 请求日志（已集成中间件，自动写入） |
| `logs/slow_request.log` | `slow_logger` | 慢请求日志，超过 `SLOW_REQUEST_MS` 自动记录 |
| `logs/pay.log` | `pay_logger` | 支付回调用 |
| `logs/sql.log` | `sql_logger` | SQL 审计 |
| `logs/ws.log` | `ws_logger` | WebSocket 日志 |
| `logs/collect.log` | `collect_logger` | 采集/爬虫日志 |
| `logs/task.log` | `task_logger` | 定时任务日志 |

### 使用方式

```python
# 1. 用预定义全局 Logger — 推荐方式
from app.core.logging import pay_logger, request_logger, app_logger

pay_logger.info("支付回调: order_no={}, amount={}", order_no, amount)
pay_logger.error("验签失败: order_no={}", order_no)

# 2. 用 get_logger() — 适合 utils/services 通用模块
from app.core.logging import get_logger

logger = get_logger(__name__)
logger.warning("登录失败: ip={}", ip)
logger.info("用户注册成功: email={}", email)
```

> loguru 使用 `{}` 占位符，不是 `%s` 也不是 f-string。

### 特性

- 按天自动切割，保留 14 天
- 控制台彩色输出（开发友好）
- 响应头返回 `X-Trace-Id` 和 `X-Process-Time`
- query 参数 `password/token/access_token/authorization/code` 自动脱敏
- 未捕获异常自动记录堆栈

## 数据库迁移

当前使用 Alembic 管理表结构：

```bash
alembic upgrade head
alembic revision --autogenerate -m "change description"
```

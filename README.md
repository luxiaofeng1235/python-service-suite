# FastAPI AI Service

企业级 FastAPI 三层架构 AI 接口服务脚手架，内置用户鉴权与 SSE 流式输出示例。

## 架构分层

```
Controller → Service → Model
```

- **Controller**：路由、参数校验、返回响应
- **Service**：核心业务逻辑（AI 推理、数据处理）
- **Model**：Pydantic 数据模型（请求体、响应体）

## 目录结构

```
app/
├── main.py              # 入口文件
├── routes/              # 路由聚合，main.py 只注册 api_router
├── core/                # 核心配置（config、security、dependency）
│   ├── config.py        # 配置管理（所有配置项集中在此，从 .env 读取）
│   ├── security.py      # JWT 令牌创建/验证
│   ├── dependency.py    # 依赖注入（获取当前用户等）
│   └── response.py      # 统一响应格式
├── common/              # 公共工具（exception 处理等）
├── utils/               # 工具模块
│   ├── email.py         # 邮件发送工具（SMTP）
│   └── sse.py           # SSE 流式响应工具
├── models/              # Pydantic 数据模型（请求体、响应体）
├── services/            # 业务逻辑层
├── controllers/         # 路由控制器层
└── web/                 # 预留 Web 业务模块
```

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

表结构变更统一用 Alembic 管理。`AUTO_CREATE_TABLES=True` 仅建议本地临时初始化使用。

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

当前仓库已接入千问兼容模式，并兼容旧接口的聊天参数：

- `POST /api/ai/chat`：返回完整回复
- `POST /api/ai/chat/send_stream_sse`：返回 SSE 流式分片
- `GET /api/ai/chats`：对话列表（登录后按用户隔离）
- `GET /api/ai/chats/{chat_id}`：对话详情
- `DELETE /api/ai/chats/{chat_id}`：删除对话
- `POST /api/ai/chats/{chat_id}/clear`：清空上下文

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

- 两个接口现已支持接入千问兼容模式接口
- 需在 `.env` 中配置 `QWEN_API_KEY`
- `/api/ai/chat/send_stream_sse` 返回 `text/event-stream`
- AI 对话接口无需登录；如果携带登录 Token，会按当前用户保存和查询上下文
- 流式输出兼容旧协议：`data:` 直接返回增量文本
- 流结束时依次返回 `data: [LOG_ID]:<chat_id>` 和 `data: [DONE]`
- 深度思考片段返回 JSON 字符串：`{"type":"reasoning_content","data":"..."}`
- `chat_id=0` 表示新建对话；传已有 `chat_id` 表示续聊
- `restart=1` 表示重生成上一条 AI 回复
- `model` 取值为 `0,1,2,3`，具体上游模型和 system 提示词由服务端配置

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
Controller → 业务 Service (ConstellationService 等) → RAG / Agent Service → AIService → LLM 模型
```

各层职责：

| 层级 | 职责 |
|------|------|
| **Controller** | 参数校验、认证鉴权、路由分发 |
| **业务 Service** | 数据查询、业务规则、定价、权限校验，不拼 prompt、不调 LLM |
| **Agent** | 意图识别、知识检索、工具调用编排，业务数据通过 Service 获取 |
| **AIService** | prompt 组装、上下文管理、流式输出、多模型切换 |
| **LLM 模型** | 语义理解、自然语言生成、推理总结，不接触价格/权限/订单 |

全链路示例（星座问答）：

```text
用户：我是双鱼座，今天运势怎么样？
  ↓
Controller → ChatService → AgentRouterService（意图路由）
  ↓
Agent 层落地：
  ├── 调用 ConstellationService（星座日期、星象、运势评分）
  ├── 调用 RagService（星座知识库检索）
  └── 生成指令给 AIService
  ↓
AIService 组装 prompt → 调用 LLM（千问/DeepSeek）→ SSE 流式返回
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
  "code": 0,
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
- Token 有效时长由 `.env` 的 `TOKEN_EXPIRE_HOURS` 控制
- 退出登录立即失效当前 Token，不影响其他设备
- 忘记密码流程：`POST /api/user/forgot-password` 发邮件 → 查收 6 位验证码 → `POST /api/user/reset-password` 提交新密码
- `GET /api/user/list` 支持 `page` 和 `size` 参数，`size` 最大 100
- `DELETE /api/user/delete` 为软删除（标记 `is_deleted=True`），同时清空该用户所有 Token
- `DELETE /api/user/tokens/expired` 需 `users.is_super=1` 管理员权限
- 免登录路径由 `.env` 的 `AUTH_WHITE_LIST` 统一配置，逗号分隔

## 日志

- `logs/app.log`：应用日志，按天切割
- `logs/request.log`：请求日志，按天切割
- `logs/slow_request.log`：慢请求日志，默认超过 `SLOW_REQUEST_MS=1000` 记录
- 响应头会返回 `X-Trace-Id` 和 `X-Process-Time`
- query 参数里的 `password/token/access_token/authorization/code` 会脱敏
- 未捕获异常会记录堆栈到应用日志

## 数据库迁移

当前使用 Alembic 管理表结构：

```bash
alembic upgrade head
alembic revision --autogenerate -m "change description"
```

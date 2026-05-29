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

后续如果扩展星座、知识库、Agent 等 LLM 业务，建议继续保持当前分层：

```text
Controller
  ↓
业务 Service，例如 ConstellationService
  ↓
RAG / Agent Service
  ↓
AIService 调用千问或其他模型
```

推荐路线：

- 星座、命理、行业知识等垂直问答优先做 `RagService`，由后端控制事实来源和业务规则。
- RAG 框架可优先调研 `LlamaIndex`，适合文档索引、知识库检索、检索增强问答。
- Agent / 多步骤流程编排可后续调研 `LangGraph`，适合意图路由、工具调用、多服务协作。
- 不建议早期把所有业务都交给 Agent 自由决策；先用明确的后端 service 和规则路由更稳定。
- LLM 更适合作为语义理解、资料整理、自然语言表达层；核心事实、权限、订单、价格、业务规则仍由后端服务控制。

星座 RAG 示例链路：

```text
用户：双鱼座的性格是什么？
  ↓
AgentRouterService / 规则路由判断为 constellation_qa
  ↓
ConstellationService 抽取星座=双鱼座，问题类型=性格
  ↓
RagService 检索星座资料、性格标签、知识库文档
  ↓
AIService 基于检索结果生成回答
  ↓
SSE 返回并保存对话记录
```

建议预留目录：

```text
app/services/constellation_service.py
app/services/rag_service.py
app/services/agent_router_service.py
app/models/db_constellation_profile.py
app/models/constellation.py
```

## 用户与权限

- `POST /api/user/login` 返回 32 位短 Token
- `POST /api/user/logout` 使当前 Token 失效
- `DELETE /api/user/tokens/expired` 清理过期 Token，需管理员权限
- `users.is_super=1` 表示管理员
- 免登录路径由 `.env` 的 `AUTH_WHITE_LIST` 统一配置

请求需登录接口时：

```bash
curl -H "Authorization: Bearer <token>" http://localhost:8000/api/user/me
```

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

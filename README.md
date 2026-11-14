# OmniCore Platform — 全领域综合业务核心平台

> **OmniCore** 是项目简称，**OmniCore Platform** 是平台全称，定位为**全领域综合业务核心平台**。基于 FastAPI 三层架构，统一提供用户鉴权、后台权限、数据库访问、文件存储与 AI 接入等公共能力。  
> 面向 **AI 应用、电商业务、内容管理、SaaS 平台、API 服务**及垂直领域扩展，复用统一的业务底座；当前已具备流式对话、星座与商品 Agent、多模态、内容生成及通用附件上传等能力。

---

## 特性概览

| 能力 | 说明 |
|------|------|
| **三层架构** | Controller → Service → Model 清晰分层，业务代码与基础设施解耦 |
| **用户鉴权体系** | 注册/登录/Token 鉴权/管理员/密码找回，开箱即用 |
| **AI 模型接入** | OpenAI 兼容接口，当前接入千问，后续可扩展 DeepSeek / OpenAI 等任意兼容服务 |
| **SSE 流式输出** | 标准 Server-Sent Events，兼容旧协议，前端直接对接 |
| **多模态与语音** | 文字、音频 SSE 原样转发；文本转语音返回音频地址 |
| **图片与视频生成** | 异步任务提交、进度查询、作品存储；视频支持 FFmpeg 水印 |
| **通用 OSS 上传** | 单接口上传图片或视频，保存附件信息并返回配置的访问地址 |
| **对话管理** | 完整 CRUD + 上下文清除 + 重生成，按用户隔离 |
| **数据库迁移** | Alembic 管理表结构变更，开发用 SQLite，生产切 MySQL |
| **Docker 一键部署** | FastAPI + Redis 容器运行，连接宿主机 MySQL |
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

按目录说明职责，业务文件在对应目录内扩展。

```text
项目根目录/
├── app/                     # 应用代码
│   ├── api/                 # 前台业务模块
│   │   ├── controllers/     # 接收请求、调用服务、返回响应
│   │   └── services/        # 前台业务逻辑和数据库操作
│   ├── admin/               # 后台管理模块
│   │   ├── controllers/     # 后台接口控制器
│   │   └── services/        # 后台业务逻辑
│   ├── services/            # 跨模块复用的公共服务
│   ├── models/              # ORM 数据库表映射
│   ├── schemas/             # 请求校验和响应序列化
│   ├── templates/           # 服务端 HTML 模板，按模块组织页面
│   ├── constants/           # 业务常量、状态枚举和静态业务数据
│   ├── routes/              # 前台、后台路由聚合
│   ├── setup/               # 应用生命周期、中间件和路由注册
│   ├── core/                # 配置汇聚、鉴权依赖和核心机制
│   ├── common/              # 统一响应、异常、分页等公共组件
│   ├── pkg/                 # 日志、Redis、第三方客户端等基础设施
│   ├── storage/             # 本地文件、OSS、资源下载和水印处理
│   ├── utils/               # 通用辅助工具
│   ├── middleware/          # 请求处理、日志、验签等中间件
│   └── web/                 # 预留 Web 业务模块
├── config/                  # 配置默认值，支持环境变量覆盖
├── migrations/              # Alembic 数据库迁移
│   └── versions/            # 迁移版本脚本
├── script/                  # Model / Schema 生成器及模板
├── sql/                     # 初始化和补充 SQL 脚本
├── public/                  # 公开静态资源、水印素材
├── uploads/                 # 本地上传文件和生成资源
└── logs/                    # 运行日志
```

**新增模块只需四步**：创建 `model`（如需新表）→ 创建 `service` → 创建 `controller` → 在 `routes/api.py` 或 `routes/admin.py` 注册。

---

## 依赖说明

| 依赖 | 说明 |
|------|------|
| `fastapi` | Web 框架 |
| `uvicorn[standard]` | ASGI 服务器 |
| `jinja2` | 服务端 HTML 模板渲染 |
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

## 页面模板渲染

服务端页面统一放在 `app/templates/`，使用 `app.common.view.display` 渲染，类似 PHP 的 `display`。首页模板为 `app/templates/index.html`，后续页面可按模块建立子目录，例如 `app/templates/admin/users.html`。

```python
from fastapi import Request
from fastapi.responses import HTMLResponse

from app.common.view import display


@router.get("/page", response_class=HTMLResponse)
async def page(request: Request) -> HTMLResponse:
    """渲染页面并传入模板数据。"""
    return display(request, "index.html", {"title": "项目介绍"})
```

模板使用 `{{ title }}` 读取数据，可使用 Jinja2 的循环、条件和模板继承。公开的图片、CSS 和 JavaScript 放在 `public/`，模板通过 `{{ url_for('public', path='/index_intro.jpg') }}` 获取资源地址。HTML 模板通过 `display` 返回，JSON API 继续使用统一的 `Response` 工具类。

## 环境变量配置

在项目根目录创建 `.env` 文件：

```bash
cp .env.example .env
```

然后按本地环境填写数据库、SMTP、千问等配置。README 不展示任何真实密钥或密钥格式示例，敏感配置只放在本地 `.env` 中。

## 快速启动

运行依赖统一维护在 `requirements.txt`，新增或调整依赖只修改这一处。`pyproject.toml` 保留项目元信息、开发依赖和 Ruff / pytest 配置；项目安装时也从 `requirements.txt` 读取运行依赖。

```bash
# 1. 安装依赖
pip3 install -r requirements.txt

# 2. 配置环境变量
cp .env.example .env    # 从模板创建本地配置
# 编辑 .env 填入自己的密钥、邮箱授权码等敏感信息

# 3. 初始化或升级数据库
alembic upgrade head

# 4. 启动服务
# 进入项目根目录（以下为示例路径）
cd /path/to/omnicore-platform
uvicorn app.main:app --reload --host 0.0.0.0 --port 8001
```

表结构变更统一用 Alembic 管理。`AUTO_CREATE_TABLES=True` 仅建议本地临时初始化使用测试。

## 里程碑

已完善的功能流程：

- **流式对话**：用户提问 → 读取历史上下文 → 普通回答或深度思考 → 流式返回 → 保存聊天记录。
- **多模态流式转发**：`POST /api/chat/stream_new` 提交消息数组 → 后端补充模型、音色和音频格式 → 原样转发文字、音频和用量 SSE 分片；上下文由请求提供。
- **文本转语音**：`POST /api/chat/chattts` 提交文本 → 后端补充模型、音色和语言 → 返回音频临时地址、过期时间及用量。
- **图片生成**：支持文生图和参考图生图，默认 `wan2.7-image`（`model=1`），专业版 `wan2.7-image-pro`（`model=2`）→ 返回任务 ID → 查询生成进度 → 保存图片并上传 OSS → 返回图片地址，支持多张图片。
- **视频生成**：`wan3.0-video` 标准版统一支持文生视频与首帧图生视频，默认 720P、5 秒 → 返回任务 ID → 查询生成进度 → 下载视频并加水印 → 上传 OSS → 返回视频地址。
- **任务与作品查询**：按登录用户隔离任务，生成中返回进度，完成后读取缓存结果，失败返回原因；图片缓存支持缺失补传。
- **通用 OSS 附件上传**：`POST /api/file/upload/oss` 公共上传图片或视频 → 校验格式和大小 → 上传 OSS → 保存附件记录 → 返回完整地址及原文件名等信息；无需 Token 和验签。

公共能力统一复用：文字对话、多模态和语音请求由 `app/services/qwen_ai_service.py` 管理；图片、视频的异步任务请求由 `app/pkg/qwen_client.py` 管理。两者均从后端读取千问密钥并集中处理各自的认证和请求异常。生成资源与附件上传共用 `app/storage/oss.py`，访问域名、Bucket 和密钥按部署环境配置。

各业务的详细流程和调用示例见 [业务流程与调用示例](docs/business.md)，后续扩展见 [LLM / RAG 待开发规划](docs/business.md#llm--rag-待开发规划)。

## Docker 部署

Docker Compose 启动 FastAPI 和 Redis；MySQL 使用宿主机上已运行的实例，不会作为容器启动。应用容器内监听 `8000`，默认从宿主机 `18000` 端口访问，Redis 默认映射到宿主机 `16379`。

应用服务名为 `omnicore`，镜像名为 `omnicore-platform`，Redis 容器名为 `omnicore-redis`。从旧命名部署升级时，先执行 `docker compose down --remove-orphans`，再按下方步骤重新构建并启动；保留现有数据卷。

### 前置条件

- Docker & Docker Compose v2+
- 宿主机 MySQL 已启动，数据库已创建，并允许来自 Docker 网络的连接


### Docker 启动（连接本机 MySQL）

```bash
# 1. 首次部署且尚无 .env 时，从模板创建配置
cp .env.example .env
# DATABASE_URL 用于宿主机直接运行；DOCKER_DATABASE_URL 用于容器连接宿主机 MySQL
# DOCKER_DATABASE_URL=mysql+aiomysql://用户名:密码@host.docker.internal:3306/数据库名?charset=utf8mb4

# 2. 构建镜像
make build

# 3. 启动 FastAPI 和 Redis（不会启动 MySQL 容器）
make docker-up

# 4. 首次部署时执行数据库迁移
docker compose exec omnicore alembic upgrade head
```

`host.docker.internal` 在 Compose 中映射到宿主机网关。若 MySQL 有网络访问限制，还需确认它监听 Docker 可达的地址，并允许对应来源连接。

本机直接运行服务时使用 `.env` 中的 `DATABASE_URL`；容器启动时 Compose 用 `DOCKER_DATABASE_URL` 覆盖它。两者可以分别使用 `127.0.0.1` 和 `host.docker.internal`，避免影响本机开发。

### 常用 Docker 命令

```bash
make build           # 构建镜像
make docker-up       # 启动服务
make docker-down     # 停止服务
make docker-restart  # 重启
make docker-logs     # 查看日志
make docker-shell    # 进入容器
make docker-clean    # 删除当前项目容器和 Redis 数据卷
```

### 验证

```bash
# 健康检查
curl http://localhost:18000/api/health

# 登录测试
curl -X POST http://localhost:18000/api/user/login \
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
- Swagger UI：http://localhost:8001/docs
- ReDoc：http://localhost:8001/redoc

## 通用 OSS 上传

调用流程：`file_controller.py → api/services/file_service.py` 校验附件 → `storage/oss.py` 上传文件流 → 保存 `attachment` → 返回附件地址与元数据。入库失败时回滚，并尝试删除本次上传的 OSS 文件。

详细说明见 [通用 OSS 上传](docs/business.md#通用-oss-上传)。

## AI 流式输出

核心流程：从 Token 获取用户 → 创建或读取当前用户的对话 → 组装系统提示词和历史消息 → 请求千问并逐段返回 SSE → 将用户消息、完整回复和推理内容保存到 `ai_chat_log.chat`。流式服务独立管理数据库会话，异常或客户端断开时尝试保存已收到的部分结果；系统提示词不入库，消息按原始文本保存。

普通对话和 Agent 的上游流式请求统一使用 `AsyncOpenAI` SDK，业务层继续负责工具调用、消息存储和前端 SSE 事件。详细说明见 [AI 流式输出](docs/business.md#ai-流式输出)。

## Agent 流式对话（Function Calling）

`POST /api/agent/astrology/stream`：星座知识问答与每日运势解读，使用 `Authorization: Bearer <token>` 认证，返回 SSE 事件。

```json
{
  "message": "帮我看看双鱼座今天的运势。"
}
```

续聊时增加 `session_id`，使用首个 `session` 事件返回的会话 ID。客户端按事件的 `type` 处理工具状态、回答分片和结束通知。

`POST /api/agent/goods/stream`：商品只读查询，复用千问 Function Calling、登录认证、会话存储和上述请求体。例如提交 `{"message":"帮我找适合出差使用的降噪耳机，列出规格、价格和库存。"}`。后端通过 Chroma 语义召回商品 ID，再从 MySQL 核验上架状态、品牌、SKU 规格、实时售价和库存；支持品牌筛选、多商品推荐及多轮追问。

商品 Agent 默认使用 `qwen-flash`，先通过 `delta` 简述商品用途和选购要点，再查询平台商品，最终推荐说明目标约 300 字。查询完成后通过 `type=data`、`data.kind=products` 返回 `data.products` 商品数组，包含 `cover_image`、规格、售价、库存和查询时间，随后继续输出平台推荐文字，收到 `done` 后结束本轮。开场使用模型一般知识，具体商品数据来自后端查询；封面为空时返回空字符串，无有效商品时返回空数组。

部署时运行 `alembic upgrade head`，会补建 `goods_categories`、`goods_brands`、`goods_products`、`goods_skus` 四表，已有表保留，商品数据需另行准备。启用后由 `app/setup/agents.py` 在后台初始化：分批读取 MySQL 商品资料 → 千问 `text-embedding-v4` 向量化 → Chroma 本地持久化。后续请求和重启复用有效索引，每次语义搜索只为查询文本生成向量。

Docker 已挂载 `data/chroma_db`，同一索引路径使用单个应用进程。商品资料或品牌、类目变动及重新导入数据后，通过内部 `refresh_index` / `rebuild_index` 同步；价格、库存和封面直接回查 MySQL，无需重建向量。当前不提供商品增删改或索引维护 HTTP 接口。配置和维护说明见 [商品 Agent](docs/agent-development.md#4-商品查询与向量索引)。

开发流程、缓存机制和完整调用示例见 [Function Calling LLM / Agent 开发流程](docs/agent-development.md)。

## 多模态流式转发

`POST /api/chat/stream_new`：携带项目登录 Token，提交 `message` 消息数组 → 后端补充模型和音频配置 → 请求千问 → 将文字、音频、用量及结束分片按原始 SSE 格式转发给前端。

详细说明见 [多模态流式转发](docs/business.md#多模态流式转发)。

## 文本转语音

`POST /api/chat/chattts`：携带项目登录 Token，提交 `text` → 后端补充 `qwen3-tts-flash`、音色和语言 → 请求千问 → 返回完整音频地址及过期时间。

详细说明见 [文本转语音](docs/business.md#文本转语音)。

## 文生图服务和接口

上游图片、视频任务统一通过官方 DashScope 异步 SDK 提交和查询，由 `app/pkg/qwen_client.py` 适配。图片默认使用 `wan2.7-image`（`model=1`），`model=2` 使用 `wan2.7-image-pro`；同一 `POST /api/ai/to_image` 接口不传参考图为文生图，传 `image_urls` 为图生图。尺寸默认 `2K`，兼容 `1024~1024` 等格式，专业版文生图支持 `4K`。继续通过 `GET /api/ai/get_image` 轮询并返回 `data.image`；模型和地址在 `config/qwenai.py` 维护，修改后重启服务。

核心流程沿用 PHP 的 `toImage` / `getImage`：提交千问异步任务并将参数保存到 `ai_to_work` → 返回 `task_id` → 前端轮询进度 → 生成完成后逐张下载原图并上传 OSS → 全部上传成功后保存 URL 数组、标记任务成功 → 返回 `data.image`。水印开关只传给千问，本地不叠加 PNG。已完成任务读取缓存，OSS 缺失且本地文件仍在时自动补传；下载或上传失败可重试。

详细说明见 [文生图服务和接口](docs/business.md#文生图服务和接口)。

## 文生视频服务和接口

**运行环境必须安装 FFmpeg**，用于生成视频后的水印处理；安装 Python 依赖不会安装 FFmpeg。安装方式见 [FFmpeg 安装与检查](docs/business.md#ffmpeg-安装与检查)。

统一使用 `wan3.0-video` 标准版：`POST /api/ai/to_video` 默认 `to=2` 文生视频，传 `to=1` 和 `image_url` 为首帧图生视频（兼容 `img_url`）；`to` 只选择生成方式，两者使用同一模型。默认 720P、5 秒、16:9、带声音，可通过 `resolution`、`duration`、`ratio`、`audio` 调整；模型及默认参数在 `config/qwenai.py` 维护。原文生视频请求参数继续可用，进度和结果统一通过 `GET /api/ai/get_video` 查询，完成返回 `data.video`。

沿用 PHP 的作品处理流程：提交异步任务 → 保存 `ai_to_work`（`type=2`、`status=0`）→ 前端轮询 → 下载视频到本地 → FFmpeg 叠加 PNG 水印 → 上传 OSS → 保存 URL 数组并设置 `status=1` → 删除本地成片。上传或入库失败时保留成片供重试，关闭 OSS 时保留本地文件。查询已完成任务直接返回缓存。

详细说明见 [文生视频服务和接口](docs/business.md#文生视频服务和接口)。

## LLM / RAG 待开发规划

当前已实现原生 Function Calling 星座 Agent，以及结合 Chroma 语义召回和 MySQL 实时核验的商品 Agent。开发方式见 [Agent 开发流程](docs/agent-development.md) 和 [商品 Agent](docs/agent-development.md#4-商品查询与向量索引)。LangChain / LangGraph 编排和通用文档知识库作为后续扩展。

早期规划参考见 [LLM / RAG 待开发规划](docs/business.md#llm--rag-待开发规划)，当前代码分层以 Agent 开发文档为准。

## 用户与权限

当前已预留的用户接口（`/api/user/*`）：

| 方法 | 路径 | 说明 | 登录要求 |
|------|------|------|---------|
| `POST` | `/api/user/register` | 用户注册 | 否 |
| `POST` | `/api/user/login` | 用户登录，返回 32 位短 Token | 否 |
| `POST` | `/api/user/logout` | 退出登录，使当前 Token 立即失效 | 是 |
| `POST` | `/api/user/forgot-password` | 忘记密码，发送验证码邮件 | 否 |
| `POST` | `/api/user/reset-password` | 重置密码，验证码 + 新密码 | 否 |
| `GET` | `/api/user/list` | 用户展示目录（分页），只返回 ID、用户名和昵称 | 是 |
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
curl -H "Authorization: Bearer <token>" http://localhost:8001/api/user/me
```

### 接口说明

- 注册时用户名 2-50 字符，密码 6-128 字符，邮箱、昵称可选
- Token 有效时长由 `.env` 的 `ACCESS_TOKEN_EXPIRE_MINUTES` 控制
- 退出登录立即失效当前 Token，不影响其他设备
- 忘记密码流程：`POST /api/user/forgot-password` 发邮件 → 查收 6 位验证码 → `POST /api/user/reset-password` 提交新密码
- 重置密码只接受数据库中最后签发且未使用、未过期的验证码；成功后撤销该用户所有登录 Token，需重新登录。Redis 缓存异常不会使已使用验证码重新生效。
- `GET /api/user/list` 支持 `page` 和 `size` 参数，`size` 最大 100；仅展示启用且未注销的用户，返回 `id`、`username`、`nickname`。查看邮箱等管理信息使用受 `user:list` 权限控制的 `/admin/users/list`。
- `DELETE /api/user/delete` 为软删除（标记 `is_deleted=True`），同时清空该用户所有 Token
- `DELETE /api/user/tokens/expired` 需 `users.is_super=1` 管理员权限
- 免登录路径由 `.env` 的 `AUTH_WHITE_LIST` 统一配置，逗号分隔

## 抽奖系统

抽奖模块采用 **引擎 + 服务 + 业务** 三层解耦设计，核心算法与业务流程完全分离：

| 模式 | 引擎函数 | 说明 |
|------|---------|------|
| **单层** | `draw_pool()` | 一组奖品按权重直接抽取，物品级可嵌套子池（再抽一次） |
| **层级** | `draw_tiered()` | 先抽奖池层（概率层），再抽层内物品：适用于"抽卡→抽角色→抽取具体道具"的多级场景 |
| **批量** | `draw_batch()` | 指定次数反复抽，返回抽奖结果列表 |

详细说明见 [抽奖系统](docs/business.md#抽奖系统)。

## 接口加解密签名

前后端接口防篡改、防重放，前端传 `sign` + `timestamp`，服务端验签通过才处理请求。

| 规则 | 说明 |
|------|------|
| 使用场景 | POST / PUT 请求（GET 不验签） |
| 白名单 | `.env` 的 `AUTH_WHITE_LIST` 配置的路径跳过签名校验 |
| 请求格式 | JSON、URL 编码表单、multipart 表单使用相同签名规则；启用验签时不支持的格式、空请求或缺签名返回 403 |
| 表单字段 | `sign`、`timestamp` 与业务文本字段一起提交，不允许重复字段；multipart 文件内容不参与签名，仍由上传服务校验，公共 OSS 上传保持免验签 |
| 参数限制 | 只允许标量（字符串/数字），禁止数组和嵌套对象 |
| bool 类型 | 禁止直接传 `true`/`false`，需转为 `"1"`/`"0"` 字符串 |
| 时间戳 | 13 位毫秒，不参与参数排序，追加在拼接串末尾（secret_key 之前） |
| 时间窗口 | 客户端与服务端时间偏差超过 5 分钟，返回 403 |
| 密钥位置 | `secret_key` 拼在拼接串最末尾 |
| 开关 | `.env` 配置 `API_ENCRYPT_ENABLED=true/false`（false 则明文传输） |

详细说明见 [接口加解密签名](docs/business.md#接口加解密签名)。

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

## Model / Schema 生成器

先在 MySQL 创建业务表，再通过 CLI 生成 Model 和基础请求、响应 Schema。配置统一放在项目根目录 `generator.yaml`，输出目录和特殊命名均可配置，已有文件默认整组跳过。生成代码包含中文文件头、类说明及字段说明，业务验证和响应结构由开发者继续完善。

```bash
python -m script.codegen --table demo_articles --dry-run
python -m script.codegen --table demo_articles
```

使用方式及边界见 [生成器说明](script/README.md)。

## 数据库迁移

当前使用 Alembic 管理表结构：

```bash
alembic upgrade head
alembic revision --autogenerate -m "change description"
```

## 详细文档

AI、OSS 上传、抽奖和接口签名等说明见 [业务流程与调用示例](docs/business.md)；Agent 编排、工具调用、运势缓存、商品检索及结构化 SSE 输出见 [Function Calling LLM / Agent 开发流程](docs/agent-development.md)。

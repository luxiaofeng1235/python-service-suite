# 业务流程与调用示例

[返回项目 README](../README.md)

本文集中保存从 README 拆出的详细业务流程、参数和调用示例，流程内容沿用原文。

## 目录

- [通用 OSS 上传](#通用-oss-上传)
- [AI 流式输出](#ai-流式输出)
- [多模态流式转发](#多模态流式转发)
- [文本转语音](#文本转语音)
- [文生图服务和接口](#文生图服务和接口)
- [文生视频服务和接口](#文生视频服务和接口)
- [LLM / RAG 待开发规划](#llm--rag-待开发规划)
- [抽奖系统](#抽奖系统)
- [接口加解密签名](#接口加解密签名)

## 通用 OSS 上传

调用流程：`file_controller.py → api/services/file_service.py` 校验附件 → `storage/oss.py` 上传文件流 → 保存 `attachment` → 返回附件地址与元数据。入库失败时回滚，并尝试删除本次上传的 OSS 文件。

- 统一接口：`POST /api/file/upload/oss`，根据文件扩展名自动识别图片或视频。
- 公共接口，无需 Token、`sign` 或 `timestamp`，通过 `multipart/form-data` 的 `file` 字段直接上传；与现有公共上传一致，`user_id=0`、`owner_type=user`、`owner_id=0`。
- 接口已加入默认免登录、免验签白名单；如果 `.env` 自定义了 `AUTH_WHITE_LIST`，也需包含 `/api/file/upload/oss`。
- 复用本地上传的格式、大小配置（图片默认 10 MB、视频默认 200 MB），通过公共 OSS SDK 上传，服务端读取已有 OSS 配置。此接口始终上传 OSS，`OSS_ENABLED` 仍仅控制 AI 生成资源的同步。
- 上传完成后写入 `attachment`，返回 `data.url`、`id`、`originName`（原文件名）、`storedName`（存储文件名）、`fileSize`（字节数）、`fileType`（image/video）、`mimeType` 和 `createdAt`（上传时间）。完整地址由当前部署的 `OSS_VIEW_DOMAIN` 与对象路径拼接；文件列表兼容本地相对路径和 OSS 完整地址。
- OSS 路径为 `uploads/images/YYYY/MM/<随机文件名>` 或 `uploads/videos/YYYY/MM/<随机文件名>`。复用请求的临时文件流，不另存一份本地文件，也不添加水印。
- 已有数据库需执行附件归属字段迁移：`alembic upgrade 20260612_0001`（首次部署按项目迁移流程执行 `alembic upgrade head`）。

```bash
curl -sS 'http://127.0.0.1:8001/api/file/upload/oss' \
  -F 'file=@/path/to/image.png'

curl -sS 'http://127.0.0.1:8001/api/file/upload/oss' \
  -F 'file=@/path/to/video.mp4'
```

## AI 流式输出

调用链：`app/api/controllers/ai_controller.py → app/api/services/ai_service.py → app/services/ai_stream_service.py → app/services/qwen_ai_service.py → 千问`。

核心流程：从 Token 获取用户 → 创建或读取当前用户的对话 → 组装系统提示词和历史消息 → 请求千问并逐段返回 SSE → 将用户消息、完整回复和推理内容保存到 `ai_chat_log.chat`。流式服务独立管理数据库会话，异常或客户端断开时尝试保存已收到的部分结果；系统提示词不入库，消息按原始文本保存。

接口如下：

- `POST /api/ai/chat/send_stream`：返回 SSE 流式分片，`model`、`chat_id`、`msg`、`restart` 必传
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

- 上游使用 OpenAI 兼容协议，通过公共 `AsyncOpenAI` SDK 请求和解析分片，普通对话与 Agent 共用；当前流程按千问模型与联网搜索策略处理
- 后端从 `.env` 读取 `QWEN_API_KEY`，从 `config/ai.py` 读取 `QWEN_CHAT_URL`，调用千问时自动附加认证；前端无需传千问密钥
- 两个流式接口均返回 `Content-Type: text/event-stream`、`Cache-Control: no-cache`、`X-Accel-Buffering: no`
- AI 对话接口使用项目登录 Token 校验用户身份并隔离上下文；此 Token 与千问 API Key 无关
- 流式输出兼容旧协议：`data:` 直接返回增量文本
- 正常结束时依次返回两条独立 SSE 消息：`data: [LOG_ID]:<chat_id>`、`data: [DONE]`
- **出错时不会返回 `[DONE]`**：先返回一条错误文本（业务错误为具体提示，系统异常为 `上游流式调用失败: ...`），再返回 `data: [EXCEPTION]` 作为结束标记。前端需同时处理 `[DONE]` 和 `[EXCEPTION]` 两种收尾
- 深度思考片段返回 JSON 字符串：`{"type":"reasoning_content","data":"..."}`
- `chat_id=0` 表示新建对话；传已有 `chat_id` 表示续聊
- `restart=1` 表示重新生成：丢弃历史中的最后一条消息且不追加本轮 `msg`，让模型基于剩余上下文重答（`restart=0` 时才会把 `msg` 作为新一轮用户提问追加）
- `is_deep_reflection=1` 使用 `qwq-plus` 深度思考；为 `0` 或不传时使用 `qwen-max`，该流程不受 `config/ai.py` 的 `QWEN_MODEL` 影响
- `model` 当前仅支持取值 `1`（对应千问 qwen-max）；对话列表接口 `GET /api/ai/chats` 的 `model_id` 查询参数同样限定为 `1`
- 上述两个文字对话流接口默认开启千问联网搜索（`enable_search=true`）

`curl` 示例：

```bash
curl -N \
  -H "Accept: text/event-stream" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -X POST http://localhost:8001/api/ai/chat/send_stream \
  -d '{"model":1,"chat_id":0,"msg":"你好，介绍一下这个服务","restart":0}'
```

## 多模态流式转发

`POST /api/chat/stream_new`：携带项目登录 Token，提交 `message` 消息数组 → 后端补充模型和音频配置 → 请求千问 → 将文字、音频、用量及结束分片按原始 SSE 格式转发给前端。

- 复用 `QWEN_CHAT_URL` 和后端 `.env` 的 `QWEN_API_KEY`；模型 `qwen3-omni-flash`、音色 `Cherry`、音频格式 `wav` 集中维护在 `config/ai.py`。
- 兼容 `messages` 字段和 PHP 的表单提交方式，消息 `content` 可为文本或多模态内容数组；历史上下文由请求提供，不重复拼接，也不写入聊天记录。
- 返回原始 `choices/delta/audio/usage` 结构，完整转发空 `choices` 的用量分片和上游结束标记。前端自行解析 SSE、解码音频并播放。
- 通过公共 SDK 的原始流式响应转发字节，不重复解析或包装 SSE；连接中断时关闭响应及客户端，不伪造正常结束标记。
- 此入口不附加普通对话的联网搜索参数；实时天气等问题需要另外接入实时数据。

```bash
curl -N -X POST 'http://127.0.0.1:8001/api/chat/stream_new' \
  -H 'Authorization: Bearer <token>' \
  -H 'Content-Type: application/json' \
  -d '{"message":[{"role":"user","content":"你好，请介绍一下自己"}]}'
```

## 文本转语音

`POST /api/chat/chattts`：携带项目登录 Token，提交 `text` → 后端补充 `qwen3-tts-flash`、音色和语言 → 请求千问 → 返回完整音频地址及过期时间。

- 支持 JSON、URL 编码表单和 multipart 表单，文本必填，最多 600 字符。
- 地址 `QWEN_TTS_URL`、模型 `QWEN_TTS_MODEL`、音色 `QWEN_TTS_VOICE`（`Cherry`）和语言 `QWEN_TTS_LANGUAGE_TYPE`（`Chinese`）维护在 `config/ai.py`，复用后端 `.env` 的 `QWEN_API_KEY`。
- 返回项目统一 JSON，原始千问结果保留在 `data`：音频地址读取 `data.output.audio.url`，过期时间读取 `data.output.audio.expires_at`，用量读取 `data.usage.characters`。地址是上游临时链接，此流程不写聊天记录、不下载音频或上传 OSS。

```bash
curl -sS -X POST 'http://127.0.0.1:8001/api/chat/chattts' \
  -H 'Authorization: Bearer <token>' \
  -H 'Content-Type: application/json' \
  -d '{"text":"你好，欢迎使用文本转语音服务。"}'
```

## 文生图服务和接口

调用链：`app/api/controllers/ai_controller.py → app/api/services/ai_service.py → app/services/ai_image_service.py → app/storage/ai_image.py → app/storage/oss.py`。

核心流程沿用 PHP 的 `toImage` / `getImage`：提交千问异步任务并将参数保存到 `ai_to_work` → 返回 `task_id` → 前端轮询进度 → 生成完成后逐张下载原图并上传 OSS → 全部上传成功后保存 URL 数组、标记任务成功 → 返回 `data.image`。水印开关只传给千问，本地不叠加 PNG。已完成任务读取缓存，OSS 缺失且本地文件仍在时自动补传；下载或上传失败可重试。

接口如下：

- `POST /api/ai/to_image`：提交文生图任务，支持 JSON、URL 编码表单和 multipart 表单。
- `GET /api/ai/get_image`：通过查询参数 `task_id` 获取生成进度和结果。
- 两个接口均需要项目登录 Token，用户 ID 由后端从 Token 获取，前端无需传 `user_id`。任务保存和查询始终限定当前登录用户。千问密钥仍由后端读取。
- 提交参数全部必传：`model`（1或2）、`prompt`（1～500字符）、`size`（如 `1024~1024`）、`n`（1～4）、`watermark`（1开启、2关闭）。宽高各为720～1440整数，总像素不超过200万。
- 水印与 PHP 一致：`watermark=1` 请求千问添加默认水印，`watermark=2` 关闭。`getImage` 仅下载原图并上传 OSS，不再叠加本地 `public/watermark.png`。需要无水印图片时传 `watermark=2`；历史已完成图片仍返回原有结果。

```bash
curl -X POST 'http://127.0.0.1:8001/api/ai/to_image' \
  -H 'Authorization: Bearer <token>' \
  -H 'Content-Type: application/json' \
  -d '{"model":1,"prompt":"一只小猫","size":"1024~1024","n":1,"watermark":2}'

curl -G 'http://127.0.0.1:8001/api/ai/get_image' \
  -H 'Authorization: Bearer <token>' \
  --data-urlencode 'task_id=<提交时返回的任务ID>'
```

提交成功及生成中返回 `{"code":1,"msg":"图片生成中","data":"任务ID"}`；成功后返回 `{"code":1,"msg":"图片生成成功","data":{"image":[...]}}`。

- `app/services/ai_image_service.py`：提交任务、按用户查询任务、下载生成图片和缓存结果。
- 图片、视频服务按任务查询、缓存读取、上游状态分发、成功和失败处理拆分。数据库状态由 `app/constants/ai.py` 的 `TaskStatus` 枚举维护；`app/services/ai_task_service.py` 共用 JSON 记录解析、缓存错误提取和失败落库方法。
- `app/pkg/qwen_client.py`：图片和视频共用的千问任务客户端，统一通过官方 `dashscope==2.0.4` 的 `AsyncClient` 调用 `images.jobs.create/fetch` 和 `videos.jobs.create/fetch`，集中维护后端认证、任务结果兼容和错误转换。提交只返回任务 ID，不使用 SDK 的等待完成方法；前端继续轮询原有接口。
- SDK 根地址由现有 `QWEN_IMAGE_URL`、`QWEN_VIDEO_URL`、`QWEN_TASK_URL` 派生，无需新增 `.env` 配置。请求与连接超时继续使用 `config/ai.py` 的 `QWEN_REQUEST_TIMEOUT`、`QWEN_CONNECT_TIMEOUT`。禁用 SDK 自动重试，避免重复提交生成任务；正常结束、异常和取消时均关闭客户端连接。
- SDK 返回值在请求层还原为原有 `output` 结构。查询得到明确失败任务时，交给业务层保存 `status=2` 和错误信息；网络或格式异常只返回错误，保留任务待处理状态。生成后的下载、图片 OSS 同步、视频 FFmpeg 水印及上传流程保持原有职责分层。
- `app/api/services/ai_service.py`：提供 `to_image(db, req, user_id)`、`get_image(db, task_id, user_id)` 调用入口。
- `app/models/ai_to_work.py`：按现有 PHP `ai_to_work` 表映射，`task_id` 为可空的 `VARCHAR(255)`，`work` 可空；`type=1` 图片、`type=2` 视频；状态为 `0` 生成中、`1` 成功、`2` 失败、`3` 已删除。文生图只处理图片任务，已删除任务按不存在处理。
- 已有 `ai_to_work` 表可直接复用；新环境或缺表环境执行 `alembic upgrade head`，迁移会补建任务表并保留已有数据。
- 认证复用后端 `.env` 的 `QWEN_API_KEY`。`QWEN_IMAGE_URL` 和 `QWEN_TASK_URL` 统一维护在 `config/ai.py`，使用 PHP 中的 DashScope 地址。
- 模型沿用 PHP：`model=1` 为 `wanx2.1-t2i-turbo`，`model=2` 为 `wanx2.1-t2i-plus`。
- 图片按千问返回内容原样下载到 `UPLOAD_DIR/ai_images/`。启用 `OSS_ENABLED=True` 后，再通过公共 `app/storage/oss.py` 上传至 `OSS_BUCKET` 的 `uploads/ai_images/...`，所有图片上传成功后才保存作品地址并设置 `status=1`。返回域名使用 `OSS_VIEW_DOMAIN`，只填写域名，不包含 `/uploads`。
- 已完成任务查询时会检查本站图片是否存在于 OSS：存在则直接复用；缺失且本地文件还在时自动补传，无需重新生成。上传或查询异常不会伪装成成功，也不会把已有本地文件删除。
- 关闭 OSS 时仍保留原本地存储方式，访问域名前缀使用 `FILE_BASE_URL`；这个前缀只用于拼接 URL，本身不会上传文件。只有域名正确映射到本地目录时才能直接访问。

公共 OSS 配置写入后端 `.env`，密钥不要写入源码或提交到 Git：

```env
OSS_ENABLED=True
OSS_ACCESS_KEY_ID=your-oss-access-key-id
OSS_ACCESS_KEY_SECRET=your-oss-access-key-secret
OSS_ENDPOINT=oss-cn-shanghai.aliyuncs.com
OSS_REGION=cn-shanghai
OSS_BUCKET=your-oss-bucket
OSS_VIEW_DOMAIN=https://assets.example.com/
```

以上域名和 Bucket 均为示例，部署时替换为自己的存储配置；`OSS_VIEW_DOMAIN` 可以使用已绑定到存储空间的自定义域名或 CDN 域名，视频访问前缀单独配置 `AI_VIDEO_BASE_URL`。

配置默认值在 `config/oss.py`，统一通过 `settings` 读取。`OSS_ROLEARN`、`OSS_TOKENEXPIRETIME`、`OSS_POLICYFILE` 保留给后续 STS 临时授权，当前服务端上传直接使用后端 AccessKey，不签发前端临时凭证，也不读取 PolicyFile。新增的 `oss2` 依赖需要在部署时安装，Docker 需要重新构建。

公共上传方法（均为异步，成功返回完整访问 URL，失败抛出统一 `AppException`）：

```python
from app.storage.oss import OSSStorage

url = await OSSStorage.upload_file("./uploads/example.png", "uploads/images/example.png")
url = await OSSStorage.upload_bytes(content, "uploads/images/example.png", content_type="image/png")
url = await OSSStorage.upload_url(source_url, "uploads/images/example.png", max_size=10 * 1024 * 1024)
exists = await OSSStorage.object_exists("uploads/images/example.png")
```

调用示例（`db` 为异步数据库会话，`user_id` 为已认证用户 ID）：

```python
from app.api.services.ai_service import AIService
from app.schemas.ai import ImageRequest

req = ImageRequest(model=1, prompt="一只小猫", size=[1024, 1024], n=1, watermark=2)
task_id = await AIService.to_image(db, req, user_id)
result = await AIService.get_image(db, task_id, user_id)
```

生成中返回任务 ID；成功返回 `{"image": [...]}`。失败抛出项目统一的 `AppException`。成功和明确失败的任务会入库缓存，后续查询不再访问千问。网络、下载或 OSS 上传异常保留待处理状态，可以重试查询。

## 文生视频服务和接口

**运行环境必须安装 FFmpeg**，用于生成视频后的水印处理；安装 Python 依赖不会安装 FFmpeg。安装方式见下方“FFmpeg 安装与检查”。

沿用 PHP `toVideo/getVideo`：提交异步任务 → 保存 `ai_to_work`（`type=2`、`status=0`）→ 前端轮询 → 下载视频到本地 → FFmpeg 叠加 PNG 水印 → 上传 OSS → 保存 URL 数组并设置 `status=1`。查询已完成任务直接返回缓存。

- `POST /api/ai/to_video`：支持 JSON、URL 编码表单和 multipart 表单；`prompt` 必传，1～500 字符，`to=2` 可省略。模型固定为 PHP 的 `wanx2.1-t2v-turbo`，当前只接文生视频。
- `GET /api/ai/get_video?task_id=...`：生成中返回任务 ID，完成返回 `{"code":1,"msg":"视频生成成功","data":{"video":["https://video.example.com/uploads/ai_videos/xxx.mp4"]}}`，域名取部署时配置的 `AI_VIDEO_BASE_URL`。
- 两个接口均使用项目登录 Token，用户 ID 从 Token 获取；千问和 OSS 密钥均由后端 `.env` 读取。
- 水印默认使用 `public/watermark.png`，与 PHP `public/uploads/222.png` 是相同图片。FFmpeg 使用 `overlay=W-w-10:H-h-10`，按水印原始尺寸叠加，右边、底边各留 10 像素。
- MySQL 8 行锁覆盖任务查询和文件处理，同一任务被占用时其他轮询直接返回生成中；`status=3` 只表示已删除。下载、转码或上传失败保持待处理，可重试；上游明确失败保存 `status=2`。
- 上传前保留本地加水印成片，OSS 上传失败后重试可复用；输入视频及临时输出自动清理。成片保存在 `UPLOAD_DIR/ai_videos/`，OSS 对象使用 `uploads/ai_videos/` 前缀。视频访问域名单独取 `AI_VIDEO_BASE_URL`，图片访问域名取 `OSS_VIEW_DOMAIN`；关闭 OSS 时取 `FILE_BASE_URL`。
- 原片下载和成片均受 `FILE_VIDEO_MAX_SIZE` 限制。FFmpeg 异步调用，超时或请求取消会终止进程。处理期间当前查询请求会等待，客户端和反向代理超时应覆盖下载、转码和上传耗时，建议每 3～5 秒轮询。

调用链：`ai_controller.py → api/services/ai_service.py → services/ai_video_service.py → storage/ai_video.py → storage/oss.py`。复用现有作品表，无需新增表结构。

上游任务提交和查询复用 `app/pkg/qwen_client.py` 中的 DashScope 异步 SDK 适配，分别调用 `videos.jobs.create`、`videos.jobs.fetch`；接口仍按“提交任务 → 轮询结果”交互，查询成功后才进入本地下载、水印和 OSS 上传流程。

AI 地址、默认模型、水印文件、视频访问域名、FFmpeg 路径和超时统一维护在 `config/ai.py`；AI 相关 `.env` 配置只维护 `QWEN_API_KEY`。修改配置后重启服务。Docker 已补充 FFmpeg，部署时需要重新构建镜像。

```python
# config/ai.py
QWEN_VIDEO_URL = "https://dashscope.aliyuncs.com/api/v1/services/aigc/video-generation/video-synthesis"
QWEN_TASK_URL = "https://dashscope.aliyuncs.com/api/v1/tasks"
AI_VIDEO_WATERMARK_PATH = "./public/watermark.png"
AI_VIDEO_BASE_URL = "https://video.example.com"
FFMPEG_BIN = "ffmpeg"
AI_VIDEO_FFMPEG_TIMEOUT = 600
```

### FFmpeg 安装与检查

Alpine Linux（使用 `apk`，以 root 执行）：

```bash
apk add ffmpeg
ffmpeg -version
```

Ubuntu / Debian / Ubuntu WSL：

```bash
sudo apt-get update
sudo apt-get install -y ffmpeg
ffmpeg -version
```

当前项目 Docker 镜像基于 `python:3.12-slim`（Debian），`Dockerfile` 已通过 `apt-get` 安装 FFmpeg。部署时重新构建并创建应用容器，再在容器内检查：

```bash
docker compose up -d --build ai-server
docker compose exec ai-server ffmpeg -version
```

FFmpeg 必须安装在实际运行后端的环境中；Docker 部署时在应用容器内检查，本机运行时在本机检查。默认 `config/ai.py` 的 `FFMPEG_BIN = "ffmpeg"`，通过 PATH 查找；自定义安装位置时可改为可执行文件的绝对路径。所用 FFmpeg 需支持 `overlay` 滤镜和 `libx264` 编码器。提交视频任务前会检查 FFmpeg 和水印文件，缺少 FFmpeg 时提示“FFmpeg 未安装或 FFMPEG_BIN 配置错误”。

### 接口调用示例

```bash
curl -X POST 'http://127.0.0.1:8001/api/ai/to_video' \
  -H 'Authorization: Bearer <token>' \
  -H 'Content-Type: application/json' \
  -d '{"to":2,"prompt":"一只小猫在花园里慢慢行走，阳光温暖，镜头平稳移动"}'

curl -G 'http://127.0.0.1:8001/api/ai/get_video' \
  -H 'Authorization: Bearer <token>' \
  --data-urlencode 'task_id=<提交时返回的任务ID>'
```

## LLM / RAG 待开发规划

> 本节保留早期扩展设想，其中 LangChain / LangGraph、RAG 和示例目录尚未落地。当前已实现原生 Function Calling，实际分层、星座运势生成与缓存机制以 [Function Calling LLM / Agent 开发流程](agent-development.md) 为准。

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

## 抽奖系统

### 架构设计

抽奖模块采用 **引擎 + 服务 + 业务** 三层解耦设计，核心算法与业务流程完全分离：

```
业务 Service（签到/充值/活动/任务奖励）
         │
         ├─ 校验次数 / 库存 / 记录
         ├─ 调用 draw_result()
         ├─ 扣库存 / 写中奖记录 / 发奖
         └─ 返回前端
               │
               ▼
    LotteryDrawService.draw_result()           ← app/services/lottery_service.py
         │
         ├─ 加载配置（DB → JSON 降级 → 抛错）
         ├─ 调用引擎
         └─ 返回奖品结果
               │
               ▼
        核心引擎（纯函数，无状态）                ← app/core/lottery.py
         ├─ 最大余额法权重归一化
         ├─ 单层抽奖（pick_by_weight）
         ├─ 层级抽奖（draw_tiered）
         ├─ 批量抽奖（draw_batch）
         └─ 动态权重修饰器（apply_weight_modifier）
```

### 各层职责

| 层 | 文件 | 负责 | 不负责 |
|----|------|------|--------|
| **引擎** | `app/core/lottery.py` | 概率归一化、随机抽取、层级展开、动态权重 | 配置来源、业务校验 |
| **服务** | `app/services/lottery_service.py` | 加载奖池配置（DB→JSON→抛错）、调用引擎 | 用户鉴权、次数限制 |
| **业务 Service** | 各场景自己的 service | 次数/库存/记录/发奖 | 概率算法、配置管理 |

### 配置加载链路

```
请求抽奖（config_key + level + batch_count）
    │
    ├─ ① 查询 DB lottery_configs 表
    │      └─ 有数据 → 解析 JSON 配置 → 调用引擎
    │
    ├─ ② DB 无数据 → 读取 config/lottery/{key}.json
    │      └─ 文件存在 → 解析 JSON → 回写 DB（缓存）→ 调用引擎
    │
    └─ ③ JSON 文件也不存在 → 抛出配置不存在错误
```

### 抽奖模式

| 模式 | 引擎函数 | 说明 |
|------|---------|------|
| **单层** | `draw_pool()` | 一组奖品按权重直接抽取，物品级可嵌套子池（再抽一次） |
| **层级** | `draw_tiered()` | 先抽奖池层（概率层），再抽层内物品：适用于"抽卡→抽角色→抽取具体道具"的多级场景 |
| **批量** | `draw_batch()` | 指定次数反复抽，返回抽奖结果列表 |

### 配置格式（JSON）

单层配置示例 (`config/lottery/default.json`)：
```json
{
  "mode": "pool",
  "total": 100,
  "items": [
    { "id": "prize_1", "name": "金币", "v": 50, "type": "coin", "amount": 100, "desc": "100 金币" },
    { "id": "prize_2", "name": "钻石", "v": 30, "type": "diamond", "amount": 10, "desc": "10 钻石" },
    { "id": "prize_3", "name": "谢谢参与", "v": 20, "type": "none", "amount": 0 }
  ]
}
```

层级配置示例：
```json
{
  "mode": "tiered",
  "tiers": [
    { "name": "稀有", "v": 30, "items": [ ... ] },
    { "name": "普通", "v": 70, "items": [ ... ] }
  ]
}
```

### 现有接口

| 方法 | 路径 | 说明 | 鉴权 |
|------|------|------|------|
| `POST` | `/api/lottery/draw` | 单次/批量抽奖 | 无需登录 |

请求体：
```json
{
  "config_key": "default",
  "level": 0,
  "batch_count": 1
}
```

返回体：
```json
{
  "amount": 100,
  "desc": "100 金币",
  "prize_id": "prize_1",
  "props": null,
  "type": "coin"
}
```

## 接口加解密签名

### 设计目的

前后端接口防篡改、防重放，前端传 `sign` + `timestamp`，服务端验签通过才处理请求。

### 工作原理

```
客户端                                   服务端
   │                                       │
   ├─ 构造业务参数 {username, password}     │
   ├─ 生成 13 位毫秒时间戳                  │
   ├─ 按 key 字典序排序拼接                 │
   │   password123usernameadmin             │
   ├─ 末尾追加时间戳                        │
   │   password123usernameadmin1700000000000 │
   ├─ 末尾追加密钥 (API_ENCRYPT_KEY)        │
   │   password123usernameadmin1700000000000mysecret │
   ├─ sha256 → sign                         │
   ├─ 发送 {params + sign + timestamp}      │
   │ ───────────────────────────────────────→ │
   │                                       ├─ 检查 API_ENCRYPT_ENABLED
   │                                       ├─ 白名单放行
   │                                       ├─ 提取 sign + timestamp
   │                                       ├─ 校验 timestamp 在 5 分钟内
   │                                       ├─ 去掉 sign，剩余参数排序拼接
   │                                       ├─ 末尾补 timestamp + secret_key
   │                                       ├─ sha256 比对 sign
   │                                       └─ 通过 → 进入路由 / 拒绝 → 403
```

### 协议约定

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

### 模块文件

| 文件 | 说明 |
|------|------|
| `app/middleware/encrypt.py` | ASGI 中间件：拦截请求、验签、放行或 403 |
| `app/utils/crypto.py` | `compute_sign()` 计算签名 + `verify_sign()` 验签 |
| `app/utils/rsa.py` | RSA 公钥加密/私钥解密、AES-ECB/CFB 加解密工具 |

### 签名计算示例

```python
参数:  {"username": "admin", "password": "123"}
排序:  password123usernameadmin
加时间戳:  password123usernameadmin1700000000000
加密钥:   password123usernameadmin1700000000000mysecret
签名:    sha256(上述字符串)
```

### 前端对接要点

1. 对业务参数按 key 字典序排序（排除 `sign`）
2. 拼接为 `key1value1key2value2...` 格式，不拼接符号
3. 末尾追加 `timestamp` 再追加 `API_ENCRYPT_KEY`
4. 计算 `sha256` 作为 `sign` 字段传入
5. 时间戳使用 `Date.now()`，单位毫秒
6. 如果关闭加密（`API_ENCRYPT_ENABLED=false`），无需传 `sign` 和 `timestamp`

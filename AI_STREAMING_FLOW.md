# AI 流式输出完整流程梳理

## 📊 整体架构

```
┌─────────────────────────────────────────────────────────────────┐
│                         前端 (浏览器)                             │
│   EventSource 监听 /api/ai/chat/send_stream_sse                   │
└──────────────────────┬──────────────────────────────────────────┘
                       │ HTTP SSE 流式连接
                       │
┌──────────────────────▼──────────────────────────────────────────┐
│                    FastAPI 应用层                                 │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │ Controller (ai_controller.py)                               │ │
│  │ POST /api/ai/chat/send_stream_sse                           │ │
│  │ - 参数验证 (ChatRequest)                                    │ │
│  │ - 鉴权 (get_current_user)                                   │ │
│  │ - 调用 AIService.stream_chat()                              │ │
│  │ - 返回 EventSourceResponse                                  │ │
│  └─────────────────┬───────────────────────────────────────────┘ │
│                    │                                              │
│  ┌─────────────────▼───────────────────────────────────────────┐ │
│  │ Service Layer (ai_service.py / ai_stream_service.py)        │ │
│  │                                                              │ │
│  │ 1. 获取/创建对话记录 (AiChatLog)                             │ │
│  │    - 若 chat_id=0，创建新对话                               │ │
│  │    - 若 chat_id>0，查询已有对话                             │ │
│  │                                                              │ │
│  │ 2. 解析模型配置 (QwenChatConfig)                             │ │
│  │    - model=1 → qwen-max 或 qwq-plus (深度思考)              │ │
│  │    - system_prompt 设定                                     │ │
│  │    - enable_search=True (联网搜索)                          │ │
│  │                                                              │ │
│  │ 3. 组装消息列表 (messages)                                   │ │
│  │    - 添加 system prompt                                     │ │
│  │    - 加载历史消息 (从 chat.chat JSON)                       │ │
│  │    - 处理重生成模式 (restart=1 删除最后一条)                │ │
│  │    - 追加当前用户消息                                        │ │
│  │                                                              │ │
│  │ 4. 流式调用上游 Qwen API                                    │ │
│  │    (QwenAIService.stream_completion)                        │ │
│  └─────────────────┬───────────────────────────────────────────┘ │
│                    │                                              │
└────────────────────┼──────────────────────────────────────────────┘
                     │
┌────────────────────▼──────────────────────────────────────────────┐
│              千问 API (外部服务 - DashScope)                        │
│  HTTP POST https://dashscope.aliyuncs.com/compatible-mode/.../   │
│  Content-Type: application/json                                   │
│  Authorization: Bearer <QWEN_API_KEY>                             │
│                                                                   │
│  请求体:                                                          │
│  {                                                               │
│    "model": "qwen-max" | "qwq-plus",                             │
│    "messages": [...],                                            │
│    "stream": true,                                               │
│    "enable_search": true                                         │
│  }                                                               │
│                                                                   │
│  响应: Server-Sent Events (SSE) 格式                              │
│  data: {"choices": [{"delta": {"content": "你好..."}}]}          │
│  data: {"choices": [{"delta": {"content": "，我是..."}}]}        │
│  ...                                                             │
│  data: [DONE]                                                    │
└────────────────────┬───────────────────────────────────────────────┘
                     │
        ┌────────────┴────────────┐
        │                         │
   正常完成              异常处理(超时、错误等)
```

---

## 🔄 详细的请求流程

### 1️⃣ 前端发起请求

```javascript
// 浏览器端 JavaScript
const response = await fetch('/api/ai/chat/send_stream_sse', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer <token>'
  },
  body: JSON.stringify({
    model: 1,              // 模型 ID (固定为 1 = 千问)
    chat_id: 0,            // 0 = 新建对话, >0 = 续聊
    msg: '你好',           // 用户消息
    restart: 0,            // 0 = 正常, 1 = 重生成(删除上一条)
    is_deep_reflection: 0  // 0 = 普通, 1 = 深度思考 (qwq-plus)
  })
});

// 监听流式响应
const reader = response.body.getReader();
const decoder = new TextDecoder();

while (true) {
  const { done, value } = await reader.read();
  if (done) break;
  
  const chunk = decoder.decode(value);
  // 处理 SSE 事件
  // - 普通文本: "你好，"
  // - JSON 推理: {"type":"reasoning_content","data":"让我思考..."}
  // - 结束: "[DONE]" 或 "[EXCEPTION]"
}
```

---

### 2️⃣ Controller 层处理

**文件**: `app/api/controllers/ai_controller.py`

```python
@router.post("/ai/chat/send_stream_sse", response_class=EventSourceResponse)
async def chat_stream(
    req: ChatRequest,  # 1. Pydantic 参数验证
    current_user: dict = Depends(get_current_user),  # 2. 鉴权
) -> EventSourceResponse:
    """
    流程:
    1. ChatRequest 自动解析 JSON
       - model: 1
       - chat_id: 0
       - msg: "你好"
       - restart: 0
       - is_deep_reflection: 0
    
    2. get_current_user 依赖获取登录用户
       - 从 Token 中解析 user_id
       - 白名单路由跳过鉴权
    
    3. 调用 AIService.stream_chat()
       - 这是个异步生成器，返回 AsyncGenerator[str, None]
    
    4. 用 SSEUtil.stream_response() 包装生成器
       - 转换为 EventSourceResponse
       - 设置响应头 (no-cache, no-buffering)
    """
    return SSEUtil.stream_response(
        AIService.stream_chat(req, user_id=current_user.get("user_id") or 0),
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # 禁止 Nginx 缓冲
        },
    )
```

**关键参数**:
- `response_class=EventSourceResponse` — 告诉 FastAPI 这是流式响应
- `Cache-Control: no-cache` — 禁用浏览器缓存
- `X-Accel-Buffering: no` — 禁止反向代理缓冲

---

### 3️⃣ Service 层处理（核心逻辑）

#### **层级 1**: `app/api/services/ai_service.py` (接口层)

```python
class AIService(CoreAIService):
    @staticmethod
    async def stream_chat(req: ChatRequest, user_id: int = 0) -> AsyncGenerator[str, None]:
        """
        职责: 包装核心 AI 服务，复用对话管理能力
        """
        # 直接代理 CoreAIService 的流式对话
        async for chunk in CoreAIService.stream_chat(req, user_id):
            yield chunk  # 逐块转发到客户端
```

#### **层级 2**: `app/services/ai_stream_service.py` (核心服务)

这是**最核心的流程控制**，包含所有业务逻辑：

```python
class AIService:
    @staticmethod
    async def stream_chat(req: ChatRequest, user_id: int = 0):
        """
        ════════════════════════════════════════════════════════
        核心流程 — 完整的对话生命周期管理
        ════════════════════════════════════════════════════════
        """
        # ⚠️ 自建 DB Session，避免 FastAPI yield 依赖提前关闭连接
        async with async_session() as db:
            chat: AiChatLog | None = None
            messages: list[dict] | None = None
            reply = ""        # 累积完整回复
            reasoning = ""    # 累积深度思考内容
            
            try:
                # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                # 第 1 步: 获取或创建对话记录
                # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                chat = await AIService._get_or_create_chat_log(
                    db, 
                    req.chat_id,    # 0 = 创建新对话, >0 = 查询已有
                    req.model,      # 模型 ID
                    user_id         # 用户 ID（权限隔离）
                )
                
                # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                # 第 2 步: 解析模型配置
                # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                config = QwenAIService.resolve_config(
                    req.model,              # 1
                    req.is_deep_reflection  # 0 | 1
                )
                # 返回值:
                # QwenChatConfig(
                #   model="qwen-max" | "qwq-plus",
                #   system_prompt="你是一个...",
                #   enable_search=True
                # )
                
                # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                # 第 3 步: 组装消息列表（关键！）
                # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                messages = AIService._prepare_messages(
                    chat,                      # 对话记录对象
                    req.msg,                   # 当前用户消息
                    req.restart,               # 0 | 1（重生成模式）
                    config.system_prompt       # System prompt
                )
                
                # messages 最终结构:
                # [
                #   {"role": "system", "content": "你是一个..."},
                #   {"role": "user", "content": "过去消息1"},
                #   {"role": "assistant", "content": "过去回复1", "reasoning_content": "..."},
                #   ...
                #   {"role": "user", "content": "当前消息"},  # 新消息
                # ]
                
                # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                # 第 4 步: 建立流式连接到上游 Qwen API
                # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                async for event_type, content in QwenAIService.stream_completion(
                    messages,
                    config,
                ):
                    # 每次迭代都会从 Qwen API 收到一个 SSE 事件
                    
                    if event_type == "delta":  # 普通文本
                        reply += content       # 累积完整回复
                        yield AIService._format_stream_content(content)
                        # → 直接转发给客户端浏览器
                        
                    elif event_type == "reasoning":  # 深度思考片段
                        reasoning += content   # 累积推理内容
                        yield json.dumps(
                            {
                                "type": "reasoning_content",
                                "data": AIService._format_stream_content(content),
                            },
                            ensure_ascii=False,
                        )
                        # → 包装为 JSON，转发给客户端
                
                # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                # 第 5 步: 流结束 — 持久化完整对话到数据库
                # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                await AIService._save_chat_log(
                    db, 
                    chat,                           # 对话对象
                    messages,                       # 完整消息列表
                    assistant_content=reply,        # 完整 AI 回复
                    reasoning_content=reasoning     # 完整推理过程
                )
                await db.commit()
                
                # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                # 第 6 步: 返回完成标记
                # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                yield f"[LOG_ID]:{chat.id}"  # 返回对话 ID
                yield "[DONE]"               # 流结束标记
                
            # ════════════════════════════════════════════════════════
            # 异常处理
            # ════════════════════════════════════════════════════════
            except AppException as exc:  # 业务异常
                # 保存已接收的部分回复
                await AIService._save_partial_chat(db, chat, messages, reply, reasoning)
                yield str(exc)        # 错误信息
                yield "[EXCEPTION]"   # 结束标记
                
            except asyncio.CancelledError:  # 客户端断连
                # 保存已接收的部分回复
                await AIService._save_partial_chat(db, chat, messages, reply, reasoning)
                raise
                
            except Exception as exc:  # 系统异常
                # 保存已接收的部分回复
                await AIService._save_partial_chat(db, chat, messages, reply, reasoning)
                app_logger.exception("AI 流式对话异常")
                yield f"上游流式调用失败: {exc!s}"
                yield "[EXCEPTION]"
```

---

### 4️⃣ Qwen API 层（外部服务）

**文件**: `app/services/qwen_ai_service.py`

```python
class QwenAIService:
    @classmethod
    async def stream_completion(cls, messages, config) -> AsyncGenerator[tuple[str, str], None]:
        """
        职责: 建立 httpx 流式连接，解析 Qwen SSE 响应
        """
        # 创建异步 HTTP 客户端
        async with cls._create_client() as client:
            # 发起 POST 请求到千问 API
            async with client.stream(
                "POST",
                settings.QWEN_CHAT_URL,  # https://dashscope.aliyuncs.com/...
                headers={
                    "Authorization": f"Bearer {settings.QWEN_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": config.model,              # "qwen-max" | "qwq-plus"
                    "messages": messages,               # 完整消息历史
                    "stream": True,                     # 启用流式响应
                    "enable_search": config.enable_search,  # True
                },
                timeout=httpx.Timeout(300.0, connect=30.0),  # 5分钟超时
            ) as response:
                # 检查 HTTP 状态码
                if response.status_code >= 400:
                    body = await response.aread()
                    raise AppException(msg=cls._extract_error_message(...))
                
                # 逐行读取 SSE 流
                async for raw_line in response.aiter_lines():
                    # 解析 SSE 行
                    # data: {"choices": [{"delta": {"content": "..."}}]}
                    for event_type, content in cls._parse_sse_line(raw_line):
                        # ("delta", "你好")
                        # ("reasoning", "我在思考...")
                        yield event_type, content
```

**SSE 行格式**:
```
data: {"choices":[{"delta":{"content":"你"}}]}
data: {"choices":[{"delta":{"content":"好"}}]}
data: {"choices":[{"delta":{"reasoning_content":"思考中"}}]}
data: [DONE]
```

---

### 5️⃣ 数据库持久化

**文件**: `app/models/ai_chat_log.py`

```python
class AiChatLog(Base):
    """AI 对话记录表"""
    __tablename__ = "ai_chat_log"
    
    id: int                 # 对话 ID（主键）
    user_id: int            # 用户 ID（权限隔离）
    model_id: int           # 模型类型（1=千问）
    chat: list[dict]        # JSON 格式的消息历史
    create_time: datetime   # 创建时间
    update_time: datetime   # 更新时间
```

**chat 字段结构** (JSON):
```json
[
  {
    "role": "user",
    "content": "你好"
  },
  {
    "role": "assistant",
    "content": "你好，我是千问助手",
    "reasoning_content": ""
  },
  {
    "role": "user",
    "content": "深度思考一下"
  },
  {
    "role": "assistant",
    "content": "思考结果是...",
    "reasoning_content": "首先... 其次... 最后..."
  }
]
```

---

## 🔀 消息历史处理逻辑

### 场景 1: 新建对话 (chat_id=0)

```
请求:
{
  chat_id: 0,
  msg: "你好",
  restart: 0,
  is_deep_reflection: 0
}

处理:
1. 创建新的 AiChatLog 记录
2. chat = [](空列表)
3. 组装消息:
   messages = [
     {role: "system", content: "你是一个..."},
     {role: "user", content: "你好"}
   ]
4. 调用 Qwen API → 得到回复
5. 保存到数据库:
   chat.chat = [
     {role: "user", content: "你好"},
     {role: "assistant", content: "你好，我是..."}
   ]
```

### 场景 2: 续聊 (chat_id>0, restart=0)

```
当前数据库中已有:
chat.chat = [
  {role: "user", content: "你好"},
  {role: "assistant", content: "你好，我是..."}
]

请求:
{
  chat_id: 123,
  msg: "请介绍一下你的功能",
  restart: 0
}

处理:
1. 查询已有对话 chat_id=123
2. 加载历史消息
3. 追加新消息:
   messages = [
     {role: "system", content: "你是一个..."},
     {role: "user", content: "你好"},
     {role: "assistant", content: "你好，我是..."},
     {role: "user", content: "请介绍一下你的功能"}  ← 新追加
   ]
4. 调用 Qwen API
5. 保存到数据库（更新 chat.chat 字段）
```

### 场景 3: 重生成 (restart=1)

```
当前数据库中已有:
chat.chat = [
  {role: "user", content: "你好"},
  {role: "assistant", content: "你好，我是..."},
  {role: "user", content: "介绍功能"},
  {role: "assistant", content: "我有多个功能..."}  ← 要删除
]

请求:
{
  chat_id: 123,
  msg: "任意值（会被忽略）",
  restart: 1
}

处理:
1. 查询已有对话
2. 加载历史消息
3. 删除最后一条消息（assistant）
4. 不追加新消息（msg 被忽略）:
   messages = [
     {role: "system", content: "你是一个..."},
     {role: "user", content: "你好"},
     {role: "assistant", content: "你好，我是..."},
     {role: "user", content: "介绍功能"}  ← 保留，让模型重新回答
   ]
5. 调用 Qwen API → 得到新回复
6. 保存到数据库（覆盖旧的 assistant 消息）
```

---

## 🌊 流式数据流向

```
┌─────────────────────────────────────────────────────────────┐
│ 前端 EventSource 监听                                        │
└────────────────────┬────────────────────────────────────────┘
                     ▲ 接收 SSE 事件
                     │
     ┌───────────────┴────────────────┐
     │ 事件 1: "你"                    │ 事件 N: "[DONE]"
     │ 事件 2: "好"                    │
     │ 事件 3: "，我是..."             │
     │ 事件 M: "{"type":"reasoning"..."} │
     │
┌────┴──────────────────────────────────┐
│ FastAPI SSEUtil.stream_response()      │
│ - 接收生成器的 yield                    │
│ - 转换为 SSE 格式: data: <content>    │
└────┬──────────────────────────────────┘
     │
┌────▼──────────────────────────────────┐
│ AIService.stream_chat() 生成器          │
│ - yield "你"                           │
│ - yield "好"                           │
│ - yield "，我是..."                    │
│ - yield "[DONE]"                      │
└────┬──────────────────────────────────┘
     │
┌────▼──────────────────────────────────┐
│ QwenAIService.stream_completion()      │
│ - 逐行读取 Qwen API SSE 流             │
│ - 解析并转换为 (event_type, content)   │
│ - yield ("delta", "你")                │
│ - yield ("delta", "好")                │
│ - yield ("delta", "，我是...")         │
└────┬──────────────────────────────────┘
     │
┌────▼──────────────────────────────────┐
│ Qwen API (外部服务)                    │
│ data: {"choices":[{"delta":{"content":"你"}}]}   │
│ data: {"choices":[{"delta":{"content":"好"}}]}   │
│ data: {"choices":[{"delta":{"content":"，我是..."}}]} │
│ data: [DONE]                           │
└────────────────────────────────────────┘
```

---

## ⚡ 关键细节

### 1. 为什么要自建 DB Session？

```python
async with async_session() as db:  # ✅ 自建 session
    async for chunk in QwenAIService.stream_completion(...):
        yield chunk  # 流式 yield
    # 流结束后才关闭 session
```

❌ **错误做法**（使用 FastAPI 依赖注入）:
```python
@router.post(...)
async def chat_stream(db: AsyncSession = Depends(get_session)):
    async for chunk in AIService.stream_chat():
        yield chunk  # ⚠️ FastAPI 可能提前关闭 db
```

原因：FastAPI 的依赖注入会在生成器第一次 yield 时记录退出点，可能导致 DB 连接提前关闭。

### 2. 重生成模式（restart=1）的细节

```python
def _prepare_messages(chat, msg, restart, system_prompt):
    history = _load_history(chat.chat)
    
    if restart == 1:
        # 删除最后一条 assistant 消息，让模型重新回答
        if history:
            history.pop()
        # ⚠️ msg 被忽略，不会追加新消息
    else:
        # 正常模式：追加新用户消息
        history.append({"role": "user", "content": msg})
    
    return [{"role": "system", "content": system_prompt}, *history]
```

### 3. 深度思考模式（is_deep_reflection=1）

```python
def resolve_config(model_id, is_deep_reflection):
    if is_deep_reflection == 1:
        model = "qwq-plus"  # 改用深度思考模型
    else:
        model = "qwen-max"  # 普通快速回复
    
    return QwenChatConfig(model=model, ...)
```

**qwq-plus 特点**：
- 返回 `reasoning_content` 字段（思考过程）
- 返回 `content` 字段（最终答案）
- 可通过 SSE 流式返回思考过程

### 4. 异常处理与部分保存

```python
try:
    async for chunk in QwenAIService.stream_completion(...):
        reply += chunk
        yield chunk
    # 正常保存
    await _save_chat_log(db, chat, messages, reply, reasoning)
    await db.commit()
    
except (AppException, Exception) as exc:
    # ⚠️ 流断开或上游出错
    # 但已接收的部分回复仍需保存
    await _save_partial_chat(db, chat, messages, reply, reasoning)
    await db.commit()
    yield str(exc)
    yield "[EXCEPTION]"
```

这样确保即使客户端断连或上游出错，已接收的回复仍被保存。

---

## 📍 完整数据流示例

### 用户请求

```json
POST /api/ai/chat/send_stream_sse
Content-Type: application/json
Authorization: Bearer abc123

{
  "model": 1,
  "chat_id": 0,
  "msg": "什么是 FastAPI？",
  "restart": 0,
  "is_deep_reflection": 0
}
```

### 数据库状态变化

**请求前**：无对话记录

**请求中**：
1. 创建 `AiChatLog { user_id: 10, model_id: 1, chat: [] }`
2. 获得 `chat_id: 123`
3. 消息列表组装完成
4. 开始流式调用 Qwen API

**流式响应**（SSE 格式）：
```
data: FastAPI
data: 是
data: 一个
data: 现代化
...
data: [DONE]
```

**请求后**：
```json
{
  "id": 123,
  "user_id": 10,
  "model_id": 1,
  "chat": [
    {
      "role": "user",
      "content": "什么是 FastAPI？"
    },
    {
      "role": "assistant",
      "content": "FastAPI 是一个现代化...",
      "reasoning_content": ""
    }
  ],
  "create_time": "2026-11-09 10:30:00",
  "update_time": "2026-11-09 10:30:05"
}
```

---

## 🎯 总结

| 阶段 | 关键类 | 职责 |
|------|--------|------|
| **1. 接收** | `ai_controller.py` | 参数验证、鉴权、路由 |
| **2. 组织** | `ai_service.py` | 调用核心服务，代理流 |
| **3. 核心** | `ai_stream_service.py` | 对话管理、消息组装、持久化 |
| **4. 上游** | `qwen_ai_service.py` | HTTP 流式连接、SSE 解析 |
| **5. 工具** | `sse.py` | SSE 流式响应包装 |
| **6. 数据** | `ai_chat_log.py` | 对话记录持久化 |

**完整链路**：
```
请求 → Controller → Service → Qwen API → SSE 响应 → 保存到数据库
```

每一步都有明确的职责，异常处理完善，流式处理正确。

# AI 文生图完整逻辑梳理（已更新）

OSS 上传已接入：`getImage → save_generated_image → OSSStorage.upload_file`。先下载、叠加本地水印，再上传到 `OSS_BUCKET` 的 `uploads/ai_images/...`；全部上传成功后才设置任务成功。域名使用 `.env` 中的 `OSS_VIEW_DOMAIN`。历史已完成任务在查询时检查 OSS，对缺失对象从现有本地文件补传；仅拼接 `FILE_BASE_URL` 不会上传文件。公共文件、字节和远程 URL 上传方法见 `app/storage/oss.py`。

## 📊 整体架构

```
┌─────────────────────────────────────────────────────────────────┐
│                         前端 (浏览器)                             │
│  1. 提交生图任务: POST /api/ai/to_image                           │
│  2. 轮询进度:    GET /api/ai/get_image?task_id=...              │
└──────────────────────┬──────────────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────────────┐
│                    FastAPI 应用层                                 │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │ Controller (ai_controller.py)                               │ │
│  │ - to_image(): 提交生图任务 (POST)                           │ │
│  │ - get_image(): 查询生图进度 (GET)                           │ │
│  └────────────────────┬──────────────────────────────────────┘  │
│                       │                                          │
│  ┌────────────────────▼──────────────────────────────────────┐  │
│  │ Service (ai_service.py / ai_image_service.py)             │  │
│  │ - to_image(): 异步提交任务，保存到 DB                     │  │
│  │ - get_image(): 查询任务状态或下载图片                     │  │
│  └────────────────────┬──────────────────────────────────────┘  │
│                       │                                          │
│  ┌────────────────────▼──────────────────────────────────────┐  │
│  │ Storage (ai_image.py)                                     │  │
│  │ - save_generated_image(): 下载、添加水印并上传 OSS        │  │
│  └────────────────────┬──────────────────────────────────────┘  │
│                       │                                          │
│  ┌────────────────────▼──────────────────────────────────────┐  │
│  │ Database (ai_to_work.py)                                  │  │
│  │ - 存储任务 ID、生成参数、任务状态、生成结果               │  │
│  └────────────────────┬──────────────────────────────────────┘  │
└──────────────────────┼──────────────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────────────┐
│                千问 API (DashScope)                               │
│  1. POST /api/v1/services/aigc/text2image/image-synthesis       │
│     (异步提交，立即返回 task_id)                                 │
│  2. GET /api/v1/tasks/<task_id>                                 │
│     (轮询查询任务状态和生成结果)                                 │
└──────────────────────┬──────────────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────────────┐
│                    宿主机文件系统                                  │
│  uploads/ai_images/<uuid>_1.png                                  │
│  uploads/ai_images/<uuid>_2.png (带水印)                         │
│  ...                                                             │
└──────────────────────────────────────────────────────────────────┘
```

---

## 🔄 完整流程（3 个阶段）

### 📍 阶段 1：提交生图任务

#### ✅ 前端请求（已简化）

```json
POST /api/ai/to_image
Content-Type: application/json
Authorization: Bearer <token>

{
  "model": 1,              // 模型类型：1=turbo (快速), 2=plus (高质量)
  "prompt": "一只可爱的猫咪",  // 生图提示词（文字描述）
  "size": "1024~1024",     // 图片尺寸："宽~高"，范围 720-1440
  "n": 2,                  // 生成数量（1-4 张）
  "watermark": 1           // 是否添加水印：1=是, 2=否
  // ⚠️ 不再需要传 user_id（已移除）
}
```

#### ✅ Controller 处理（已简化）

```python
# app/api/controllers/ai_controller.py

@router.post("/ai/to_image", summary="提交AI文生图任务")
async def to_image(
    req: ToImageRequest = Depends(_parse_to_image_request),
    db: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
):
    """
    关键变化：
    1. 移除了 request_user_id 参数验证
       ❌ 旧：request_user_id=req.user_id（冗余校验）
       ✅ 新：直接用 current_user["user_id"]
    
    2. 简化了权限校验逻辑
       - 前端不再需要传 user_id
       - 直接用登录用户的 user_id
       - 防止误操作
    """
    task_id = await AIService.to_image(
        db,
        req,
        user_id=current_user["user_id"],  # ← 直接用登录用户
        # request_user_id 已移除 ✓
    )
    return Response.success(data=task_id, msg="图片生成中")
```

**业务逻辑**：
- 🔐 所有生图操作绑定到当前登录用户
- ❌ 前端不能为他人生成图片
- ✅ 防止权限混乱

---

### 📍 阶段 2：轮询查询进度（前端）

#### ✅ 前端请求（已简化）

```bash
# 原来的
GET /api/ai/get_image?task_id=edc78df4...&user_id=10

# 现在的 ✅
GET /api/ai/get_image?task_id=edc78df4...
# user_id 已移除，由后端自动从 Token 提取
```

#### ✅ Controller 处理（已简化）

```python
# app/api/controllers/ai_controller.py

@router.get("/ai/get_image", summary="获取AI生图进度和结果")
async def get_image(
    task_id: str = Query(..., min_length=1, max_length=255),  # ← 只有 task_id
    db: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
):
    """
    关键变化：
    1. 移除了 user_id 查询参数
       ❌ 旧：user_id = Query(...) 需要前端传
       ✅ 新：user_id 从 current_user 获取
    
    2. 移除了 request_user_id 权限校验
       ❌ 旧：request_user_id=user_id（冗余校验）
       ✅ 新：直接用 current_user["user_id"]
    
    3. API 调用简化
    """
    result = await AIService.get_image(
        db,
        task_id,
        user_id=current_user["user_id"],  # ← 直接从 Token 获取
        # request_user_id 已移除 ✓
    )
    return Response.success(
        data=result,
        msg="图片生成中" if isinstance(result, str) else "图片生成成功",
    )
```

**业务逻辑**：
- 🔐 用户只能查询自己的任务（user_id 从 Token 来）
- ✅ 无法查询他人的任务
- ✅ 简化了 API 调用

---

### 📍 阶段 3：Service 层处理

#### ✅ to_image() 方法（已简化）

```python
# app/services/ai_image_service.py

@classmethod
async def to_image(cls, db: AsyncSession, req: ImageRequest, user_id: int) -> str:
    """
    提交生图任务
    
    参数变化：
    ❌ 移除: request_user_id（冗余校验）
    ✅ 保留: user_id（直接来自 current_user）
    """
    # 1. 调用千问 API
    data = await cls._request(
        "POST",
        settings.QWEN_IMAGE_URL,
        json={
            "model": cls.IMAGE_MODELS[req.model],
            "input": {"prompt": req.prompt},
            "parameters": {
                "size": f"{req.size[0]}*{req.size[1]}",
                "n": req.n,
                "watermark": False,
            },
        },
    )
    
    # 2. 提取 task_id
    output = data.get("output") or {}
    task_id = output.get("task_id")
    
    if not isinstance(task_id, str) or not task_id or len(task_id) > 255:
        raise AppException(msg="图片生成失败，" + str(data.get("message")))
    
    # 3. 保存到 DB
    task = AiToWork(
        user_id=user_id,                    # ← 来自 current_user
        task_id=task_id,
        params=req.model_dump(mode="json"),
        type=1,
        status=0,
        work=None,
    )
    db.add(task)
    await db.commit()
    
    return task_id
```

**关键改进**：
- ✅ 权限校验单一清晰（直接用 current_user）
- ✅ 不需要前端传递冗余的 user_id
- ✅ 防止权限混乱

---

#### ✅ get_image() 方法（已简化）

```python
# app/services/ai_image_service.py

@classmethod
async def get_image(
    cls, db: AsyncSession, task_id: str, user_id: int
) -> dict[str, list[str]] | str:
    """
    查询生图进度和结果
    
    参数变化：
    ❌ 移除: request_user_id（冗余校验）
    ✅ 保留: user_id（直接来自 current_user）
    """
    
    # 1. 权限校验 - 用户只能查询自己的任务
    result = await db.execute(
        select(AiToWork).where(
            AiToWork.task_id == task_id,
            AiToWork.user_id == user_id,  # ← user_id 从 current_user 来
            AiToWork.type == 1,
        )
    )
    task = result.scalar_one_or_none()
    
    if task is None or task.status == 3:
        raise AppException(msg="任务不存在")
    
    # 2. 根据任务状态返回
    if task.status == 1:  # 已完成
        return cls._image_result(cls._load_work(task.work))
    
    if task.status == 2:  # 已失败
        work = cls._load_work(task.work)
        message = "服务错误，请稍后再试"
        if isinstance(work, dict):
            message = work.get("error") or message
        raise AppException(msg=f"图片生成失败，{message}")
    
    # 3. 生成中 - 查询千问 API
    if not settings.QWEN_TASK_URL:
        raise AppException(msg="QWEN_TASK_URL 未配置")
    
    data = await cls._request(
        "GET", f"{settings.QWEN_TASK_URL.rstrip('/')}/{quote(task_id, safe='')}"
    )
    
    output = data.get("output") or {}
    status = output.get("task_status")
    
    # 3a. 还在生成
    PENDING_STATUSES = {"PENDING", "RUNNING", "SUSPENDED"}
    if status in PENDING_STATUSES:
        return task_id  # 返回 task_id，前端继续轮询
    
    # 3b. 生成完成 - 下载图片
    if status == "SUCCEEDED":
        params = task.params
        if isinstance(params, str):
            params = json.loads(params)
        
        watermark = params.get("watermark") in (1, "1")
        urls: list[str] = []
        
        for index, item in enumerate(output.get("results") or [], start=1):
            if not isinstance(item, dict) or not item.get("url"):
                continue
            
            path = await save_generated_image(
                item["url"],
                task_id,
                index,
                watermark=watermark
            )
            
            prefix = settings.FILE_BASE_URL.rstrip("/")
            urls.append(f"{prefix}/uploads/{path}")
        
        if not urls:
            await cls._fail_task(db, task, "未返回可用图片")
        
        # 更新 DB
        task.work = urls
        task.status = 1
        await db.commit()
        
        return cls._image_result(urls)
    
    # 3c. 生成失败
    if status in {"FAILED", "CANCELED", "UNKNOWN"}:
        error_message = "任务不存在" if status == "UNKNOWN" else "任务已取消或生成失败"
        if output.get("code"):
            error_message = cls._error_message(output["code"])
        
        await cls._fail_task(db, task, error_message)
    
    # 网络错误 - 让前端继续轮询
    raise AppException(msg="图片任务查询失败，请稍后重试")
```

---

## 🌊 简化后的数据流

### 场景 1：完整生图流程

```
前端请求 1:
POST /api/ai/to_image
{
  model: 1,
  prompt: "猫咪",
  size: "1024~1024",
  n: 2,
  watermark: 1
  // ❌ 不需要 user_id
}

后端处理:
1. current_user["user_id"] = 10（从 Token 获取）
2. 调用千问 API 提交
3. 保存 DB：AiToWork { user_id: 10, task_id: "abc...", status: 0 }

响应 1:
{
  code: 1,
  data: "abc...",
  msg: "图片生成中"
}

───────────────────────── 5秒后 ─────────────────────────

前端请求 2:
GET /api/ai/get_image?task_id=abc...
// ❌ 不需要 user_id（自动从 Token 获取）

后端处理:
1. current_user["user_id"] = 10
2. 查询 DB：user_id=10 AND task_id=abc...
3. 查询千问 API：status=SUCCEEDED
4. 下载 2 张图片 → uploads/ai_images/xyz_1.png + xyz_2.png
5. 更新 DB：status=1, work=[urls]

响应 2:
{
  code: 1,
  data: {
    image: ["https://static.jsss999.com/uploads/ai_images/xyz_1.png", ...],
    iamge: [...]  // PHP 兼容
  },
  msg: "图片生成成功"
}
```

---

## 📋 API 端点对比

### 提交任务

| 项 | 原版 | 新版 ✅ |
|----|------|--------|
| 端点 | POST /api/ai/to_image | POST /api/ai/to_image |
| 参数 | model, prompt, size, n, watermark, **user_id** | model, prompt, size, n, watermark |
| 权限校验 | request_user_id vs current_user["user_id"] | 直接用 current_user["user_id"] |
| 简化程度 | 需要两次校验 | 单一校验 |

### 查询进度

| 项 | 原版 | 新版 ✅ |
|----|------|--------|
| 端点 | GET /api/ai/get_image | GET /api/ai/get_image |
| 查询参数 | task_id, **user_id** | task_id |
| 权限校验 | request_user_id vs current_user["user_id"] | 直接用 current_user["user_id"] |
| 简化程度 | 需要两次校验 | 单一校验 |

---

## 🔐 权限校验流程（已简化）

### 原来的流程（复杂）

```
前端提交
  ↓
Controller 收到 user_id（前端传的）
  ↓
Controller 检查 user_id == current_user["user_id"]
  ↓
Service 再检查一遍 request_user_id
  ↓
DB 查询时再用 user_id 过滤
  
⚠️ 三层校验，容易出错
```

### 新的流程（简化）✅

```
前端提交（不传 user_id）
  ↓
Controller 从 Token 获取 current_user["user_id"]
  ↓
Service 直接用这个 user_id
  ↓
DB 查询时用 user_id 过滤
  
✅ 单一校验，清晰可靠
```

---

## 💡 改进要点

### 1. **消除冗余参数**
```python
# ❌ 旧：前端传 user_id，后端再校验
await AIService.to_image(..., request_user_id=req.user_id)

# ✅ 新：直接用登录用户
await AIService.to_image(..., user_id=current_user["user_id"])
```

### 2. **防止权限混乱**
```python
# ❌ 旧：user_id 来自前端，可能被伪造
user_id = Query(...)  # 前端传入

# ✅ 新：user_id 只来自 Token
user_id = current_user["user_id"]  # 不可伪造
```

### 3. **简化 API 调用**
```python
# ❌ 旧
GET /api/ai/get_image?task_id=xxx&user_id=10

# ✅ 新
GET /api/ai/get_image?task_id=xxx
# user_id 自动从 Authorization: Bearer <token> 中提取
```

### 4. **减少前端工作量**
- 前端不需要维护 user_id
- 不需要担心权限问题
- 只需传 task_id 查询

---

## 📝 前端迁移指南

### 旧代码
```javascript
const response = await fetch('/api/ai/get_image?task_id=abc&user_id=10', {
  headers: {'Authorization': 'Bearer <token>'}
});
```

### 新代码 ✅
```javascript
const response = await fetch('/api/ai/get_image?task_id=abc', {
  headers: {'Authorization': 'Bearer <token>'}
  // user_id 已自动从 Token 提取，不需要显式传入
});
```

---

## 🎯 总结

| 方面 | 变化 |
|------|------|
| **提交生图** | 前端不再传 `user_id`，后端从 Token 直接获取 |
| **查询进度** | 移除了 `user_id` 查询参数，改用 Token 中的用户信息 |
| **权限校验** | 从三层校验简化为单一校验 |
| **API 安全** | 增强，用户无法为他人生成或查询图片 |
| **代码可维护性** | 提升，逻辑更清晰 |
| **前端复杂度** | 降低，不需要维护 user_id |

这次改动是一次**安全性和易用性的同步提升** ✅

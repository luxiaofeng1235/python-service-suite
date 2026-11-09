# AI 文生图完整逻辑梳理

## 📊 整体架构

```
┌─────────────────────────────────────────────────────────────────┐
│                         前端 (浏览器)                             │
│  1. 提交生图任务: POST /api/ai/to_image                           │
│  2. 轮询进度:    GET /api/ai/get_image?task_id=...&user_id=...  │
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
│  │ - save_generated_image(): 下载图片并添加水印             │  │
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

#### 前端请求

```json
POST /api/ai/to_image
Content-Type: application/json
Authorization: Bearer <token>

{
  "model": 1,              // 模型类型：1=turbo (快速), 2=plus (高质量)
  "user_id": 10,           // 用户 ID（必须与登录用户一致，用于权限校验）
  "prompt": "一只可爱的猫咪",  // 生图提示词（文字描述）
  "size": "1024~1024",     // 图片尺寸："宽~高"，范围 720-1440
  "n": 2,                  // 生成数量（1-4 张）
  "watermark": 1           // 是否添加水印：1=是, 2=否
}
```

#### Controller 处理

```python
# app/api/controllers/ai_controller.py

@router.post("/ai/to_image", summary="提交AI文生图任务")
async def to_image(
    req: ToImageRequest = Depends(_parse_to_image_request),  # 参数解析（支持 JSON/Form）
    db: AsyncSession = Depends(get_session),                 # 数据库会话
    current_user: dict = Depends(get_current_user),          # 鉴权
):
    """
    处理流程：
    1. _parse_to_image_request() 自定义解析器
       - 支持 application/json
       - 支持 application/x-www-form-urlencoded
       - 支持 multipart/form-data (PHP 兼容)
    
    2. ToImageRequest 参数验证
       - model: 1 or 2
       - prompt: min_length=1, max_length=500
       - size: 720-1440 像素，最大 200 万像素
       - n: 1-4
       - watermark: 1 or 2
    
    3. 权限校验
       - 检查 req.user_id == current_user["user_id"]
       - 防止用户为其他人生成图片
    
    4. 调用 AIService.to_image()
    """
    task_id = await AIService.to_image(
        db,
        req,
        user_id=current_user["user_id"],
        request_user_id=req.user_id,  # 用于权限校验
    )
    return Response.success(data=task_id, msg="图片生成中")
```

#### Service 处理（核心逻辑）

```python
# app/services/ai_image_service.py

class AIImageService:
    IMAGE_MODELS = {
        1: "wanx2.1-t2i-turbo",  # 快速模型
        2: "wanx2.1-t2i-plus"    # 高质量模型
    }
    
    @classmethod
    async def to_image(cls, db: AsyncSession, req: ImageRequest, user_id: int) -> str:
        """
        职责：异步提交任务到千问 API，保存到数据库
        返回：任务 ID (task_id)
        """
        # ════════════════════════════════════════════════════
        # 第 1 步：调用千问 API 提交生图任务（异步）
        # ════════════════════════════════════════════════════
        data = await cls._request(
            "POST",
            settings.QWEN_IMAGE_URL,  # https://dashscope.aliyuncs.com/api/v1/...
            json={
                "model": cls.IMAGE_MODELS[req.model],  # "wanx2.1-t2i-turbo"
                "input": {
                    "prompt": req.prompt,              # "一只可爱的猫咪"
                },
                "parameters": {
                    "size": f"{req.size[0]}*{req.size[1]}",  # "1024*1024"
                    "n": req.n,                                # 2
                    "watermark": False,                        # 上游不加水印（由我们后加）
                },
            },
        )
        
        # ════════════════════════════════════════════════════
        # 第 2 步：从响应中提取 task_id
        # ════════════════════════════════════════════════════
        output = data.get("output") or {}
        task_id = output.get("task_id")  # 千问返回的任务 ID
        
        # 验证 task_id 格式
        if not isinstance(task_id, str) or not task_id or len(task_id) > 255:
            raise AppException(msg="图片生成失败，" + str(data.get("message")))
        
        # ════════════════════════════════════════════════════
        # 第 3 步：保存任务记录到数据库（AiToWork 表）
        # ════════════════════════════════════════════════════
        task = AiToWork(
            user_id=user_id,                           # 用户 ID（权限隔离）
            task_id=task_id,                           # 千问任务 ID
            params=req.model_dump(mode="json"),        # 保存生图参数（用于查询时重用）
            type=1,                                    # 1=图片, 2=视频
            status=0,                                  # 0=生成中, 1=已完成, 2=失败, 3=已删除
            work=None,                                 # 生成结果（未完成时为 None）
        )
        db.add(task)
        await db.commit()
        
        # ════════════════════════════════════════════════════
        # 第 4 步：返回 task_id 给前端
        # ════════════════════════════════════════════════════
        return task_id
```

**DB 记录状态** (任务提交后):
```
AiToWork {
  id: 1,
  user_id: 10,
  task_id: "edc78df4-5fb3-42f8-ab30-d2eac42e5e8a",  ← 千问返回
  params: {
    model: 1,
    user_id: 10,
    prompt: "一只可爱的猫咪",
    size: [1024, 1024],
    n: 2,
    watermark: 1
  },
  work: null,                                      ← 还没有结果
  type: 1,
  status: 0,                                       ← 生成中
  create_time: "2026-11-09 10:30:00",
  update_time: "2026-11-09 10:30:00"
}
```

---

### 📍 阶段 2：轮询查询进度（前端）

前端收到 task_id 后，轮询调用：

```javascript
// 前端轮询逻辑
const taskId = "edc78df4-5fb3-42f8-ab30-d2eac42e5e8a";
const userId = 10;

const pollImage = async () => {
  while (true) {
    const response = await fetch(
      `/api/ai/get_image?task_id=${taskId}&user_id=${userId}`,
      {
        headers: {
          'Authorization': 'Bearer <token>'
        }
      }
    );
    
    const result = await response.json();
    
    if (result.code === 1) {
      // 成功
      const data = result.data;
      if (typeof data === 'string') {
        // 还在生成中，data 是 task_id
        console.log("还在生成...", data);
        await new Promise(resolve => setTimeout(resolve, 2000));  // 等 2 秒再查
      } else if (data.image) {
        // 生成完成，data.image 是图片 URL 数组
        console.log("生成完成！", data.image);
        break;
      }
    } else {
      // 失败
      console.error("生成失败", result.msg);
      break;
    }
  }
};
```

---

### 📍 阶段 3：查询进度和下载图片

#### 前端请求

```bash
GET /api/ai/get_image?task_id=edc78df4-5fb3-42f8-ab30-d2eac42e5e8a&user_id=10
Authorization: Bearer <token>
```

#### Controller 处理

```python
# app/api/controllers/ai_controller.py

@router.get("/ai/get_image", summary="获取AI生图进度和结果")
async def get_image(
    user_id: int = Query(..., ge=1),              # 查询参数：用户 ID
    task_id: str = Query(..., min_length=1),     # 查询参数：任务 ID
    db: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
):
    """
    处理流程：
    1. 从 URL 查询参数获取 task_id 和 user_id
    2. 权限校验：user_id == current_user["user_id"]
    3. 调用 AIService.get_image()
    4. 返回：
       - 如果还在生成：返回 task_id（字符串）
       - 如果已完成：返回 {"image": [...], "iamge": [...]}
       - 如果失败：抛异常
    """
    result = await AIService.get_image(
        db,
        task_id,
        user_id=current_user["user_id"],
        request_user_id=user_id,  # 权限校验
    )
    return Response.success(
        data=result,
        msg="图片生成中" if isinstance(result, str) else "图片生成成功",
    )
```

#### Service 处理（核心状态机）

```python
# app/services/ai_image_service.py

@classmethod
async def get_image(cls, db: AsyncSession, task_id: str, user_id: int):
    """
    查询图片生成状态。可能返回三种情况：
    1. 还在生成中 → 返回 task_id（前端继续轮询）
    2. 已生成成功 → 返回图片 URLs
    3. 生成失败 → 抛异常
    """
    
    # ════════════════════════════════════════════════════
    # 第 1 步：权限校验（防止用户查询他人的任务）
    # ════════════════════════════════════════════════════
    result = await db.execute(
        select(AiToWork).where(
            AiToWork.task_id == task_id,
            AiToWork.user_id == user_id,
            AiToWork.type == 1,  # 只查图片任务
        )
    )
    task = result.scalar_one_or_none()
    
    if task is None or task.status == 3:  # status=3 表示已删除
        raise AppException(msg="任务不存在")
    
    # ════════════════════════════════════════════════════
    # 第 2 步：状态机 - 根据当前状态做出不同操作
    # ════════════════════════════════════════════════════
    
    # 情况 A：status=1 (已完成，结果已在数据库中)
    if task.status == 1:
        return cls._image_result(cls._load_work(task.work))
    
    # 情况 B：status=2 (已失败，返回失败信息)
    if task.status == 2:
        work = cls._load_work(task.work)
        message = "服务错误，请稍后再试"
        if isinstance(work, dict):
            message = work.get("error") or message
        raise AppException(msg=f"图片生成失败，{message}")
    
    # 情况 C：status=0 (生成中，需要查询上游)
    # ────────────────────────────────────────────────────
    data = await cls._request(
        "GET",
        f"{settings.QWEN_TASK_URL}/{quote(task_id, safe='')}"
        # 查询地址：https://dashscope.aliyuncs.com/api/v1/tasks/<task_id>
    )
    
    output = data.get("output") or {}
    status = output.get("task_status")  # PENDING, RUNNING, SUSPENDED, SUCCEEDED, FAILED, CANCELED, UNKNOWN
    
    # 情况 C1：还在生成中
    PENDING_STATUSES = {"PENDING", "RUNNING", "SUSPENDED"}
    if status in PENDING_STATUSES:
        return task_id  # 返回 task_id，前端继续轮询
    
    # 情况 C2：生成成功 SUCCEEDED
    if status == "SUCCEEDED":
        """
        关键流程：下载图片并保存到本地
        """
        params = task.params
        if isinstance(params, str):
            params = json.loads(params)
        
        watermark = params.get("watermark") in (1, "1")  # 是否需要加水印
        urls: list[str] = []
        
        # 逐个下载图片
        for index, item in enumerate(output.get("results") or [], start=1):
            if not isinstance(item, dict) or not item.get("url"):
                continue
            
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # 调用 save_generated_image()
            # - 下载图片
            # - 如需要，添加水印
            # - 保存到本地 uploads/ai_images/
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            path = await save_generated_image(
                item["url"],  # 千问返回的图片 URL
                task_id,
                index,
                watermark=watermark
            )
            
            # 组装访问 URL
            prefix = settings.FILE_BASE_URL.rstrip("/")
            urls.append(f"{prefix}/uploads/{path}")
        
        if not urls:
            await cls._fail_task(db, task, "未返回可用图片")
        
        # ════════════════════════════════════════════════════
        # 第 3 步：更新数据库（标记为已完成）
        # ════════════════════════════════════════════════════
        task.work = urls                 # 保存图片 URLs
        task.status = 1                  # 标记为已完成
        await db.commit()
        
        return cls._image_result(urls)  # 返回给前端
    
    # 情况 C3：生成失败
    if status in {"FAILED", "CANCELED", "UNKNOWN"}:
        error_message = "任务不存在" if status == "UNKNOWN" else "任务已取消或生成失败"
        if output.get("code"):
            error_message = cls._error_message(output["code"])
        
        await cls._fail_task(db, task, error_message)
    
    # 情况 C4：网络问题或不完整响应（不做任何操作，让前端继续轮询）
    raise AppException(msg="图片任务查询失败，请稍后重试")
```

---

## 🖼️ 图片下载和水印处理

**文件**: `app/storage/ai_image.py`

### 图片下载流程

```python
async def save_generated_image(
    url: str,                    # 千问返回的图片 URL
    task_id: str,               # 任务 ID（用于生成本地文件名）
    index: int,                 # 第几张图片（1, 2, ...）
    *,
    watermark: bool = False     # 是否需要添加水印
) -> str:
    """
    职责：
    1. 下载图片到本地
    2. 可选：添加水印
    3. 返回相对路径
    """
    
    # ════════════════════════════════════════════════════
    # 第 1 步：生成本地文件名
    # ════════════════════════════════════════════════════
    # 使用 UUID 而不是原始 task_id，避免 task_id 中的特殊字符问题
    safe_id = uuid.uuid5(uuid.NAMESPACE_URL, task_id).hex
    relative_path = f"ai_images/{safe_id}_{index}.png"
    file_path = Path(settings.UPLOAD_DIR) / relative_path
    # 完整路径：./uploads/ai_images/abc123def456_1.png
    
    # ════════════════════════════════════════════════════
    # 第 2 步：下载图片
    # ════════════════════════════════════════════════════
    temporary_path = file_path.with_name(f"{file_path.name}.{uuid.uuid4().hex}.tmp")
    # 使用临时文件，确保原子性（要么完全写入，要么不写入）
    
    async with httpx.AsyncClient(timeout=120.0, trust_env=False, follow_redirects=True) as client:
        async with client.stream("GET", url) as response:
            response.raise_for_status()
            
            size = 0
            with temporary_path.open("wb") as output:
                # 分块下载（每块 64KB）
                async for chunk in response.aiter_bytes(chunk_size=64 * 1024):
                    size += len(chunk)
                    
                    # 检查大小是否超过限制
                    if size > settings.FILE_IMAGE_MAX_SIZE:
                        raise AppException(msg="生成图片大小超过存储限制")
                    
                    await asyncio.to_thread(output.write, chunk)
            
            if size == 0:
                raise AppException(msg="生成图片内容为空")
    
    # ════════════════════════════════════════════════════
    # 第 3 步：可选 - 添加水印
    # ════════════════════════════════════════════════════
    if watermark:
        # 在线程中执行 CPU 密集的图片处理（避免阻塞事件循环）
        await asyncio.to_thread(_apply_watermark, temporary_path)
        
        # 检查加水印后的大小
        if await asyncio.to_thread(lambda: temporary_path.stat().st_size > settings.FILE_IMAGE_MAX_SIZE):
            raise AppException(msg="加水印后的图片大小超过存储限制")
    
    # ════════════════════════════════════════════════════
    # 第 4 步：原子性移动到正式位置
    # ════════════════════════════════════════════════════
    await asyncio.to_thread(temporary_path.replace, file_path)
    
    return relative_path
```

### 水印处理逻辑

```python
def _apply_watermark(image_path: Path) -> None:
    """
    在图片右下角添加水印
    水印配置：
    - 宽度：原图宽度的 25%
    - 边距：原图最小边长的 2%
    """
    watermark_path = Path(settings.AI_IMAGE_WATERMARK_PATH)
    
    with Image.open(image_path) as source, Image.open(watermark_path) as mark_source:
        # 1. 转为 RGBA（支持透明通道）
        image = ImageOps.exif_transpose(source).convert("RGBA")
        mark = mark_source.convert("RGBA")
        
        # 2. 计算水印大小
        margin = max(1, round(min(image.size) * WATERMARK_MARGIN_RATIO))  # 2% 边距
        max_width = max(1, min(image.width - 2 * margin, round(image.width * WATERMARK_WIDTH_RATIO)))
        max_height = max(1, image.height - 2 * margin)
        mark.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)
        
        # 3. 计算水印位置（右下角）
        x = max(0, image.width - mark.width - margin)
        y = max(0, image.height - mark.height - margin)
        
        # 4. 添加阴影（使白色水印在浅色图片上仍可辨认）
        shadow = Image.new("RGBA", mark.size, (0, 0, 0, 0))
        shadow.putalpha(mark.getchannel("A"))
        image.alpha_composite(shadow, (min(x + 1, image.width - mark.width),
                                       min(y + 1, image.height - mark.height)))
        
        # 5. 贴上水印
        image.alpha_composite(mark, (x, y))
        
        # 6. 保存为 PNG
        image.save(image_path, format="PNG")
```

---

## 💾 数据库模型

### AiToWork 表

```python
class AiToWork(Base):
    """AI 生成作品记录表"""
    
    id: int                 # 主键
    user_id: int            # 用户 ID（权限隔离）
    task_id: str            # 千问任务 ID（唯一）
    params: JSON            # 生成参数（保存请求体，用于查询时重用）
    work: JSON              # 生成结果
                            # - status=0: null
                            # - status=1: ["http://...", "http://..."]
                            # - status=2: {"error": "敏感内容"}
    type: int               # 1=图片, 2=视频
    status: int             # 0=生成中, 1=已完成, 2=失败, 3=已删除
    create_time: datetime
    update_time: datetime
```

**生命周期**:
```
status=0 (生成中)
  ↓
  [轮询查询千问 API]
  ↓
status=1 (已完成，work=[图片URLs])  或  status=2 (失败，work={error:...})
```

---

## 🌊 数据流向

### 场景 1：快速提交，稍后查询

```
前端请求 1:
POST /api/ai/to_image
{model: 1, prompt: "猫咪", size: "1024~1024", n: 2, watermark: 1}

响应 1:
{code: 1, data: "edc78df4-5fb3-42f8-ab30-d2eac42e5e8a", msg: "图片生成中"}

DB 状态:
AiToWork {status: 0, work: null}

───────────────────────── 2秒后 ─────────────────────────

前端请求 2:
GET /api/ai/get_image?task_id=edc78df4...&user_id=10

后端处理:
1. 查询 DB：status=0
2. 查询千问 API：task_status=PENDING
3. 返回 task_id (继续轮询)

响应 2:
{code: 1, data: "edc78df4-5fb3-42f8-ab30-d2eac42e5e8a", msg: "图片生成中"}

───────────────────────── 5秒后 ─────────────────────────

前端请求 3:
GET /api/ai/get_image?task_id=edc78df4...&user_id=10

后端处理:
1. 查询 DB：status=0
2. 查询千问 API：task_status=SUCCEEDED
3. 下载 2 张图片 → uploads/ai_images/abc123_1.png (带水印) + abc123_2.png (带水印)
4. 更新 DB：status=1, work=[urls]
5. 返回图片 URLs

响应 3:
{
  code: 1,
  data: {
    image: ["http://localhost:18000/uploads/ai_images/abc123_1.png", ...],
    iamge: ["http://localhost:18000/uploads/ai_images/abc123_1.png", ...]  ← PHP 兼容
  },
  msg: "图片生成成功"
}
```

### 场景 2：查询已完成的任务（不再查上游）

```
前端请求:
GET /api/ai/get_image?task_id=edc78df4...&user_id=10

后端处理:
1. 查询 DB：status=1, work=[urls]  ← 直接返回，不查上游
2. 返回图片 URLs

响应:
{code: 1, data: {image: [urls]}, msg: "图片生成成功"}
```

---

## 🔐 关键安全机制

### 1. 用户隔离

```python
# 权限校验：防止用户为他人生成图片或查询他人的任务
if req.user_id != current_user["user_id"]:
    raise AppException(msg="user_id 与当前登录用户不一致")

if task.user_id != user_id:
    raise AppException(msg="任务不存在")
```

### 2. 大小限制

```python
# 文件大小限制
if size > settings.FILE_IMAGE_MAX_SIZE:
    raise AppException(msg="生成图片大小超过存储限制")

# 像素限制（提示词验证时）
if value[0] * value[1] > 2_000_000:
    raise AppException(msg="尺寸过大，像素不能超过200万")
```

### 3. 内容安全检查

```python
# 千问 API 返回的错误码转换
error_codes = {
    "DataInspectionFailed": "敏感内容，生成失败",
    "data_inspection_failed": "敏感内容，生成失败",
    "IPInfringementSuspect": "IP侵权，生成失败",
}
```

### 4. 原子性写入

```python
# 使用临时文件确保图片完整性
temporary_path = file_path.with_name(f"{file_path.name}.{uuid.uuid4().hex}.tmp")
# 下载完成后原子性移动
await asyncio.to_thread(temporary_path.replace, file_path)
```

---

## 📡 外部 API 接口

### 千问文生图 API

**提交任务**:
```http
POST https://dashscope.aliyuncs.com/api/v1/services/aigc/text2image/image-synthesis
Authorization: Bearer <QWEN_API_KEY>
Content-Type: application/json
X-DashScope-Async: enable

{
  "model": "wanx2.1-t2i-turbo",
  "input": {
    "prompt": "一只可爱的猫咪"
  },
  "parameters": {
    "size": "1024*1024",
    "n": 2,
    "watermark": false
  }
}

响应:
{
  "output": {
    "task_id": "edc78df4-5fb3-42f8-ab30-d2eac42e5e8a",
    "task_status": "SUBMITTED"
  },
  "usage": {...}
}
```

**查询任务**:
```http
GET https://dashscope.aliyuncs.com/api/v1/tasks/edc78df4-5fb3-42f8-ab30-d2eac42e5e8a
Authorization: Bearer <QWEN_API_KEY>

响应 (生成中):
{
  "output": {
    "task_id": "edc78df4-5fb3-42f8-ab30-d2eac42e5e8a",
    "task_status": "RUNNING"
  }
}

响应 (已完成):
{
  "output": {
    "task_id": "edc78df4-5fb3-42f8-ab30-d2eac42e5e8a",
    "task_status": "SUCCEEDED",
    "results": [
      {"url": "https://...image1.png"},
      {"url": "https://...image2.png"}
    ]
  }
}
```

---

## 📋 API 端点总结

| 端点 | 方法 | 功能 | 登录 | 参数 |
|------|------|------|------|------|
| `/api/ai/to_image` | POST | 提交生图任务 | ✅ 是 | model, prompt, size, n, watermark, user_id |
| `/api/ai/get_image` | GET | 查询进度/下载 | ✅ 是 | task_id, user_id |

---

## ⚡ 关键细节

### 1. 为什么使用异步任务？

- 用户不想等待（可能需要 10-30 秒）
- 前端可以轮询查询，期间做其他事情
- 后端不需要保持连接

### 2. 为什么保存 params？

```python
params=req.model_dump(mode="json")
```

- 用于查询时重新使用（特别是 watermark 参数）
- 记录生图的具体配置，便于用户查看历史

### 3. 为什么分两个字段 iamge 和 image？

```python
return {"iamge": urls, "image": urls}  # PHP 兼容（iamge 是 typo）
```

这是对原有 PHP 代码的兼容，PHP 代码中有个拼写错误（iamge）。

### 4. 为什么要下载图片？

- 千问 API 的 URL 可能过期或有访问限制
- 本地保存后可以：
  - 长期保存
  - 添加水印
  - 提供稳定的访问链接

### 5. 水印为什么在下载时添加而不是提交时？

- 千问 API 的水印参数不可控
- 在下载时添加可以：
  - 自定义水印样式
  - 可选添加或不添加
  - 保留原始无水印版本

---

## 🎯 完整生命周期示例

```
┌─────────────────────────────────────────────────────────────┐
│ 用户提交请求                                                 │
│ POST /api/ai/to_image                                        │
│ {model:1, prompt:"猫咪", size:"1024~1024", n:2, watermark:1} │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
        ┌──────────────────────────────┐
        │ FastAPI Controller           │
        │ - 参数验证                    │
        │ - 权限校验                    │
        └──────────────┬───────────────┘
                       │
                       ▼
        ┌──────────────────────────────┐
        │ AIImageService.to_image()    │
        │ - 调用千问 API 提交          │
        │ - 获取 task_id               │
        └──────────────┬───────────────┘
                       │
                       ▼
        ┌──────────────────────────────┐
        │ 千问 API 返回 task_id        │
        │ "edc78df4..."                │
        └──────────────┬───────────────┘
                       │
                       ▼
        ┌──────────────────────────────┐
        │ 保存到 DB                     │
        │ AiToWork {                   │
        │   task_id: "edc78df4...",    │
        │   status: 0,                 │
        │   work: null                 │
        │ }                            │
        └──────────────┬───────────────┘
                       │
                       ▼
        ┌──────────────────────────────┐
        │ 返回给前端                    │
        │ data: "edc78df4..."          │
        │ msg: "图片生成中"             │
        └──────────────┬───────────────┘
                       │
        ┌──────────────┴──────────────┐
        │   前端轮询查询               │
        │   GET /api/ai/get_image?... │
        │   (每 2-5 秒一次)            │
        └──────────────┬───────────────┘
                       │
          ┌────────────┴─────────────┐
          │                          │
          ▼                          ▼
    ┌──────────────┐        ┌──────────────┐
    │ 还在生成中    │        │ 已经生成完成  │
    │ task_status  │        │ task_status  │
    │ =PENDING/    │        │ =SUCCEEDED   │
    │ RUNNING      │        │              │
    │ ↓            │        │ ↓            │
    │ 返回         │        │ 下载图片     │
    │ task_id      │        │ 添加水印     │
    │ （继续轮询） │        │ 保存本地     │
    └──────────────┘        │ 更新 DB      │
                            │ status: 1    │
                            │ work: [URLs] │
                            │ ↓            │
                            │ 返回图片 URLs │
                            └──────────────┘
```

---

## 🔧 配置项

```env
# .env

# 千问 API 配置
QWEN_API_KEY=xxx

# 文生图 API 地址
QWEN_IMAGE_URL=https://dashscope.aliyuncs.com/api/v1/services/aigc/text2image/image-synthesis

# 查询任务状态 API 地址
QWEN_TASK_URL=https://dashscope.aliyuncs.com/api/v1/tasks

# 水印配置
AI_IMAGE_WATERMARK_PATH=config/watermark.png

# 文件上传限制
FILE_IMAGE_MAX_SIZE=10485760  # 10MB

# 文件访问基础 URL
FILE_BASE_URL=http://localhost:18000
```

这就是完整的生图逻辑！✅

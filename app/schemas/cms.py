"""
============================================
CMS 文章数据模型
============================================
定义文章相关的 Pydantic 请求体、响应体、数据校验。
"""

from datetime import datetime

from pydantic import BaseModel, Field, field_serializer


# ==================== 文章分类 ====================


class ArticleCategory(BaseModel):
    """文章分类配置"""

    id: int = Field(..., description="分类ID")
    name: str = Field(..., description="分类名称")
    slug: str = Field(..., description="分类别名")
    description: str | None = Field(None, description="分类描述")


class CategoryListResponse(BaseModel):
    """分类列表响应"""

    categories: list[ArticleCategory] = Field(..., description="分类列表")


# ==================== 文章请求体 ====================


class ArticleCreateRequest(BaseModel):
    """创建文章请求体"""

    title: str = Field(..., min_length=1, max_length=255, description="文章标题")
    slug: str = Field(..., min_length=1, max_length=255, description="URL别名，唯一")
    category_id: int = Field(..., ge=1, description="所属分类ID")
    author: str | None = Field(None, max_length=100, description="作者/编辑")
    summary: str | None = Field(None, max_length=500, description="文章摘要")
    content: str = Field(..., min_length=1, description="文章正文内容")
    cover_image: str | None = Field(None, max_length=255, description="封面图URL")
    tag_ids: list[int] | None = Field(None, description="关联标签ID列表")
    status: int = Field(0, ge=0, le=2, description="状态: 0-草稿, 1-已发布, 2-下架")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "title": "FastAPI 入门教程",
                    "slug": "fastapi-intro",
                    "category_id": 1,
                    "author": "技术团队",
                    "summary": "本文介绍 FastAPI 的基本用法",
                    "content": "FastAPI 是一个高性能的 Python Web 框架...",
                    "cover_image": "/uploads/cover.jpg",
                    "status": 1,
                }
            ]
        }
    }


class ArticleUpdateRequest(BaseModel):
    """更新文章请求体"""

    title: str | None = Field(None, min_length=1, max_length=255, description="文章标题")
    slug: str | None = Field(None, min_length=1, max_length=255, description="URL别名")
    category_id: int | None = Field(None, ge=1, description="所属分类ID")
    author: str | None = Field(None, max_length=100, description="作者")
    summary: str | None = Field(None, max_length=500, description="文章摘要")
    content: str | None = Field(None, min_length=1, description="文章正文")
    cover_image: str | None = Field(None, max_length=255, description="封面图URL")
    tag_ids: list[int] | None = Field(None, description="关联标签ID列表")
    status: int | None = Field(None, ge=0, le=2, description="状态")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "title": "更新后的标题",
                    "status": 1,
                }
            ]
        }
    }


# ==================== 标签请求/响应体 ====================


class TagCreateRequest(BaseModel):
    """创建标签请求体"""

    name: str = Field(..., min_length=1, max_length=50, description="标签名称")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "name": "Python",
                }
            ]
        }
    }


class TagUpdateRequest(BaseModel):
    """更新标签请求体"""

    name: str = Field(..., min_length=1, max_length=50, description="标签名称")


class TagResponse(BaseModel):
    """标签响应体"""

    id: int = Field(..., description="标签ID")
    name: str = Field(..., description="标签名称")
    created_at: datetime | None = Field(None, description="创建时间")

    @field_serializer("created_at")
    def serialize_datetime(self, dt: datetime | None) -> str | None:
        """将 datetime 序列化为字符串"""
        if dt is None:
            return None
        return dt.strftime("%Y-%m-%d %H:%M:%S")

    model_config = {"from_attributes": True}


class TagListResponse(BaseModel):
    """标签列表响应体"""

    items: list[TagResponse] = Field(..., description="标签列表")
    total: int = Field(..., description="总记录数")
    page: int = Field(..., description="当前页码")
    size: int = Field(..., description="每页条数")


# ==================== 文章响应体 ====================


class ArticleResponse(BaseModel):
    """文章详情响应体"""

    id: int = Field(..., description="文章ID")
    title: str = Field(..., description="文章标题")
    slug: str = Field(..., description="URL别名")
    category_id: int = Field(..., description="所属分类ID")
    author: str | None = Field(None, description="作者")
    summary: str | None = Field(None, description="文章摘要")
    content: str = Field(..., description="文章正文")
    cover_image: str | None = Field(None, description="封面图URL")
    status: int = Field(..., description="状态: 0-草稿, 1-已发布, 2-下架")
    view_count: int = Field(0, description="浏览次数")
    tag_ids: list[int] | None = Field(None, description="关联标签ID列表")
    tags: list[TagResponse] | None = Field(None, description="关联标签列表（含name）")
    published_at: datetime | None = Field(None, description="发布时间")
    created_at: datetime | None = Field(None, description="创建时间")
    updated_at: datetime | None = Field(None, description="更新时间")

    @field_serializer("published_at", "created_at", "updated_at")
    def serialize_datetime(self, dt: datetime | None) -> str | None:
        """将 datetime 序列化为字符串"""
        if dt is None:
            return None
        return dt.strftime("%Y-%m-%d %H:%M:%S")

    model_config = {"from_attributes": True}


class ArticleListResponse(BaseModel):
    """文章列表响应体"""

    items: list[ArticleResponse] = Field(..., description="文章列表")
    total: int = Field(..., description="总记录数")
    page: int = Field(..., description="当前页码")
    size: int = Field(..., description="每页条数")
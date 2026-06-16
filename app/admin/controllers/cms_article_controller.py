"""
============================================
CMS 文章管理控制器
============================================
提供文章的增删改查、发布、下架等后台管理接口。
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.services.cms_article_service import CmsArticleService, CmsTagService
from app.common.pagination import PageParams
from app.common.response import Response
from app.core.admin_auth import get_current_admin_user
from app.core.rbac import require_permission
from app.database import get_session
from app.schemas.cms import (
    ArticleCreateRequest,
    ArticleListResponse,
    ArticleResponse,
    ArticleUpdateRequest,
    CategoryListResponse,
    TagCreateRequest,
    TagListResponse,
    TagResponse,
    TagUpdateRequest,
)

router = APIRouter(prefix="/admin/cms", tags=["后台-CMS文章管理"])


# ==================== 分类管理 ====================


@router.get(
    "/categories",
    summary="获取文章分类列表",
    response_model=CategoryListResponse,
)
async def get_categories():
    """获取所有文章分类（从JSON配置加载）"""
    categories = CmsArticleService.get_categories()
    return Response.success(data={"categories": categories}, msg="获取成功")


# ==================== 文章管理 ====================


@router.post(
    "/articles",
    summary="创建文章",
    dependencies=[Depends(require_permission("cms", "create"))],
)
async def create_article(
    req: ArticleCreateRequest,
    db: AsyncSession = Depends(get_session),
    current_admin: dict = Depends(get_current_admin_user),
):
    """创建新文章"""
    article = await CmsArticleService.create_article(db, req)
    return Response.success(
        data=ArticleResponse.model_validate(article),
        msg="文章创建成功",
    )


@router.get(
    "/articles",
    summary="文章列表（分页）",
    dependencies=[Depends(require_permission("cms", "list"))],
)
async def list_articles(
    page_params: PageParams = Depends(),
    category_id: int | None = Query(None, description="分类ID筛选"),
    status: int | None = Query(None, ge=0, le=2, description="状态筛选"),
    keyword: str | None = Query(None, description="关键词搜索"),
    db: AsyncSession = Depends(get_session),
):
    """分页获取文章列表"""
    data = await CmsArticleService.get_article_list(
        db, page_params, category_id, status, keyword
    )
    items = [ArticleResponse.model_validate(item) for item in data["items"]]
    return Response.success(
        data={
            "items": items,
            "total": data["total"],
            "page": data["page"],
            "size": data["size"],
        }
    )


@router.get(
    "/articles/{article_id}",
    summary="文章详情",
    dependencies=[Depends(require_permission("cms", "read"))],
)
async def get_article(
    article_id: int,
    db: AsyncSession = Depends(get_session),
):
    """根据ID获取文章详情"""
    article = await CmsArticleService.get_article_by_id(db, article_id)
    return Response.success(
        data=ArticleResponse.model_validate(article),
        msg="获取成功",
    )


@router.put(
    "/articles/{article_id}",
    summary="更新文章",
    dependencies=[Depends(require_permission("cms", "update"))],
)
async def update_article(
    article_id: int,
    req: ArticleUpdateRequest,
    db: AsyncSession = Depends(get_session),
):
    """更新文章信息"""
    article = await CmsArticleService.update_article(db, article_id, req)
    return Response.success(
        data=ArticleResponse.model_validate(article),
        msg="更新成功",
    )


@router.delete(
    "/articles/{article_id}",
    summary="删除文章",
    dependencies=[Depends(require_permission("cms", "delete"))],
)
async def delete_article(
    article_id: int,
    db: AsyncSession = Depends(get_session),
):
    """删除文章"""
    data = await CmsArticleService.delete_article(db, article_id)
    return Response.success(data=data, msg="删除成功")


@router.post(
    "/articles/{article_id}/toggle-status",
    summary="切换文章状态",
    dependencies=[Depends(require_permission("cms", "update"))],
)
async def toggle_article_status(
    article_id: int,
    db: AsyncSession = Depends(get_session),
):
    """
    切换文章状态（草稿↔发布↔下架）

    - 草稿(0) → 发布(1)
    - 发布(1) → 下架(2)
    - 下架(2) → 发布(1)
    """
    article = await CmsArticleService.toggle_article_status(db, article_id)
    status_text = {0: "草稿", 1: "已发布", 2: "已下架"}
    return Response.success(
        data=ArticleResponse.model_validate(article),
        msg=f"状态已切换为：{status_text.get(article.status, '未知')}",
    )


# ==================== 标签管理 ====================


@router.post(
    "/tags",
    summary="创建标签",
    dependencies=[Depends(require_permission("cms", "create"))],
)
async def create_tag(
    req: TagCreateRequest,
    db: AsyncSession = Depends(get_session),
):
    """创建新标签"""
    tag = await CmsTagService.create_tag(db, req)
    return Response.success(
        data=TagResponse.model_validate(tag),
        msg="标签创建成功",
    )


@router.get(
    "/tags",
    summary="标签列表（分页）",
    dependencies=[Depends(require_permission("cms", "list"))],
)
async def list_tags(
    page_params: PageParams = Depends(),
    db: AsyncSession = Depends(get_session),
):
    """分页获取标签列表"""
    data = await CmsTagService.get_tag_list(db, page_params)
    items = [TagResponse.model_validate(item) for item in data["items"]]
    return Response.success(
        data={
            "items": items,
            "total": data["total"],
            "page": data["page"],
            "size": data["size"],
        }
    )


@router.get(
    "/tags/{tag_id}",
    summary="标签详情",
    dependencies=[Depends(require_permission("cms", "read"))],
)
async def get_tag(
    tag_id: int,
    db: AsyncSession = Depends(get_session),
):
    """根据ID获取标签详情"""
    tag = await CmsTagService.get_tag_by_id(db, tag_id)
    return Response.success(data=TagResponse.model_validate(tag))


@router.put(
    "/tags/{tag_id}",
    summary="更新标签",
    dependencies=[Depends(require_permission("cms", "update"))],
)
async def update_tag(
    tag_id: int,
    req: TagUpdateRequest,
    db: AsyncSession = Depends(get_session),
):
    """更新标签名称"""
    tag = await CmsTagService.update_tag(db, tag_id, req)
    return Response.success(
        data=TagResponse.model_validate(tag),
        msg="更新成功",
    )


@router.delete(
    "/tags/{tag_id}",
    summary="删除标签",
    dependencies=[Depends(require_permission("cms", "delete"))],
)
async def delete_tag(
    tag_id: int,
    db: AsyncSession = Depends(get_session),
):
    """删除标签"""
    data = await CmsTagService.delete_tag(db, tag_id)
    return Response.success(data=data, msg="删除成功")

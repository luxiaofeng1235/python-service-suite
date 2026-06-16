"""
============================================
CMS 文章管理业务服务
============================================
提供文章的增删改查、发布、下架等业务逻辑。
"""

import json
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.exception import AppException
from app.common.pagination import PageParams, paginate
from app.models.cms_article import CmsArticle
from app.models.cms_tag import CmsTag
from app.pkg.logging import app_logger
from app.schemas.cms import (
    ArticleCategory,
    ArticleCreateRequest,
    ArticleUpdateRequest,
    TagCreateRequest,
    TagUpdateRequest,
)


class CmsArticleService:
    """文章管理业务服务"""

    # 分类配置文件路径
    _category_config_path = Path(__file__).parent.parent.parent / "config" / "cms" / "categories.json"

    @staticmethod
    def _load_categories() -> list[ArticleCategory]:
        """从 JSON 配置文件加载文章分类"""
        try:
            config_path = CmsArticleService._category_config_path
            if not config_path.exists():
                app_logger.warning("分类配置文件不存在: {}", config_path)
                return []

            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                categories = [ArticleCategory(**item) for item in data.get("categories", [])]
                app_logger.info("加载文章分类 {} 个", len(categories))
                return categories
        except Exception as e:
            app_logger.error("加载文章分类失败: {}", e)
            return []

    @staticmethod
    def get_categories() -> list[ArticleCategory]:
        """获取所有文章分类"""
        return CmsArticleService._load_categories()

    @staticmethod
    def get_category_by_id(category_id: int) -> ArticleCategory | None:
        """根据ID获取分类"""
        categories = CmsArticleService.get_categories()
        for cat in categories:
            if cat.id == category_id:
                return cat
        return None

    @staticmethod
    async def create_article(
        db: AsyncSession,
        req: ArticleCreateRequest,
    ) -> CmsArticle:
        """
        创建文章

        Args:
            db: 数据库会话
            req: 创建请求体

        Returns:
            创建的文章对象

        Raises:
            AppException: 分类不存在 / slug 已存在
        """
        # 1. 校验分类是否存在
        category = CmsArticleService.get_category_by_id(req.category_id)
        if not category:
            raise AppException(msg="分类不存在")

        # 2. 检查 slug 是否已存在
        result = await db.execute(select(CmsArticle).where(CmsArticle.slug == req.slug))
        if result.scalar_one_or_none():
            raise AppException(msg="URL别名已存在，请更换")

        # 3. 创建文章
        article = CmsArticle(
            title=req.title,
            slug=req.slug,
            category_id=req.category_id,
            author=req.author,
            summary=req.summary,
            content=req.content,
            cover_image=req.cover_image,
            tag_ids=req.tag_ids,
            status=req.status,
            view_count=0,
            published_at=datetime.now() if req.status == 1 else None,
        )
        db.add(article)
        await db.commit()
        await db.refresh(article)

        app_logger.info(
            "创建文章成功: id={}, title={}, category={}",
            article.id,
            article.title,
            category.name,
        )
        return article

    @staticmethod
    async def get_article_by_id(db: AsyncSession, article_id: int) -> CmsArticle:
        """
        根据ID获取文章详情

        Raises:
            AppException: 文章不存在
        """
        result = await db.execute(select(CmsArticle).where(CmsArticle.id == article_id))
        article = result.scalar_one_or_none()
        if not article:
            raise AppException(msg="文章不存在")
        return article

    @staticmethod
    async def get_article_list(
        db: AsyncSession,
        page_params: PageParams,
        category_id: int | None = None,
        status: int | None = None,
        keyword: str | None = None,
    ) -> dict:
        """
        分页获取文章列表

        Args:
            db: 数据库会话
            page_params: 分页参数
            category_id: 分类ID筛选
            status: 状态筛选
            keyword: 关键词搜索（标题）

        Returns:
            分页结果
        """
        stmt = select(CmsArticle).order_by(CmsArticle.id.desc())

        # 分类筛选
        if category_id is not None:
            stmt = stmt.where(CmsArticle.category_id == category_id)

        # 状态筛选
        if status is not None:
            stmt = stmt.where(CmsArticle.status == status)

        # 关键词搜索
        if keyword:
            stmt = stmt.where(CmsArticle.title.like(f"%{keyword}%"))

        return await paginate(db, stmt, page_params)

    @staticmethod
    async def update_article(
        db: AsyncSession,
        article_id: int,
        req: ArticleUpdateRequest,
    ) -> CmsArticle:
        """
        更新文章

        Raises:
            AppException: 文章不存在 / 分类不存在 / slug 已存在
        """
        # 1. 获取文章
        article = await CmsArticleService.get_article_by_id(db, article_id)

        # 2. 更新字段
        update_data = req.model_dump(exclude_unset=True)

        # 校验分类
        if "category_id" in update_data:
            category = CmsArticleService.get_category_by_id(update_data["category_id"])
            if not category:
                raise AppException(msg="分类不存在")

        # 校验 slug 唯一性
        if "slug" in update_data and update_data["slug"] != article.slug:
            result = await db.execute(
                select(CmsArticle).where(CmsArticle.slug == update_data["slug"])
            )
            if result.scalar_one_or_none():
                raise AppException(msg="URL别名已存在，请更换")

        # 发布状态变更时更新发布时间
        if "status" in update_data:
            if update_data["status"] == 1 and article.status != 1:
                if article.published_at is None:  # 只首次发布时设，已发布过的重新发布不覆盖
                    update_data["published_at"] = datetime.now()
            elif update_data["status"] != 1:
                update_data["published_at"] = None

        # 执行更新
        for field, value in update_data.items():
            setattr(article, field, value)

        await db.commit()
        await db.refresh(article)

        app_logger.info("更新文章成功: id={}, title={}", article.id, article.title)
        return article

    @staticmethod
    async def delete_article(db: AsyncSession, article_id: int) -> dict:
        """
        删除文章

        Raises:
            AppException: 文章不存在
        """
        article = await CmsArticleService.get_article_by_id(db, article_id)

        await db.delete(article)
        await db.commit()

        app_logger.info("删除文章成功: id={}, title={}", article.id, article.title)
        return {"id": article_id, "message": "删除成功"}

    @staticmethod
    async def toggle_article_status(db: AsyncSession, article_id: int) -> CmsArticle:
        """
        Toggle article status.

        Status flow: draft(0) → published(1) → offline(2) → published(1).

        Args:
            db: Database session.
            article_id: Article ID.

        Returns:
            Updated article.

        Raises:
            AppException: Article not found.
        """
        article = await CmsArticleService.get_article_by_id(db, article_id)

        if article.status == 0:
            # 草稿 → 发布
            article.status = 1
            article.published_at = datetime.now()
        elif article.status == 1:
            # 发布 → 下架
            article.status = 2
            article.published_at = None
        else:
            # 下架 → 发布
            article.status = 1
            article.published_at = datetime.now()

        await db.commit()
        await db.refresh(article)

        app_logger.info("切换文章状态: id={}, title={}, status={}", article.id, article.title, article.status)
        return article


class CmsTagService:
    """标签管理业务服务"""

    @staticmethod
    async def create_tag(db: AsyncSession, req: TagCreateRequest) -> CmsTag:
        """
        创建标签

        Raises:
            AppException: 标签名称已存在
        """
        result = await db.execute(select(CmsTag).where(CmsTag.name == req.name))
        if result.scalar_one_or_none():
            raise AppException(msg="标签名称已存在")

        tag = CmsTag(name=req.name)
        db.add(tag)
        await db.commit()
        await db.refresh(tag)

        app_logger.info("创建标签成功: id={}, name={}", tag.id, tag.name)
        return tag

    @staticmethod
    async def get_tag_list(db: AsyncSession, page_params: PageParams) -> dict:
        """分页获取标签列表"""
        stmt = select(CmsTag).order_by(CmsTag.id.desc())
        return await paginate(db, stmt, page_params)

    @staticmethod
    async def get_tag_by_id(db: AsyncSession, tag_id: int) -> CmsTag:
        """
        根据ID获取标签

        Raises:
            AppException: 标签不存在
        """
        result = await db.execute(select(CmsTag).where(CmsTag.id == tag_id))
        tag = result.scalar_one_or_none()
        if not tag:
            raise AppException(msg="标签不存在")
        return tag

    @staticmethod
    async def update_tag(db: AsyncSession, tag_id: int, req: TagUpdateRequest) -> CmsTag:
        """
        更新标签

        Raises:
            AppException: 标签不存在 / 名称已存在
        """
        tag = await CmsTagService.get_tag_by_id(db, tag_id)

        if req.name != tag.name:
            result = await db.execute(select(CmsTag).where(CmsTag.name == req.name))
            if result.scalar_one_or_none():
                raise AppException(msg="标签名称已存在")

        tag.name = req.name
        await db.commit()
        await db.refresh(tag)

        app_logger.info("更新标签成功: id={}, name={}", tag.id, tag.name)
        return tag

    @staticmethod
    async def delete_tag(db: AsyncSession, tag_id: int) -> dict:
        """
        删除标签

        Raises:
            AppException: 标签不存在
        """
        tag = await CmsTagService.get_tag_by_id(db, tag_id)

        await db.delete(tag)
        await db.commit()

        app_logger.info("删除标签成功: id={}, name={}", tag.id, tag.name)
        return {"id": tag_id, "message": "删除成功"}

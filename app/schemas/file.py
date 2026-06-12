"""
============================================
文件上传数据模型模块
============================================
定义文件上传相关的 Pydantic 响应体。
"""

from datetime import datetime

from pydantic import BaseModel, Field, field_serializer

from app.api.services.file_service import FileService


class AttachmentResponse(BaseModel):
    """文件上传成功后的响应体"""

    id: int = Field(..., description="文件ID")
    owner_type: str = Field("user", description="归属类型：user/admin/system")
    owner_id: int = Field(0, description="归属主体ID")
    original_name: str = Field(..., description="原始文件名")
    stored_name: str = Field(..., description="存储文件名")
    file_path: str = Field(..., description="文件相对路径")
    file_size: int = Field(..., description="文件大小（字节）")
    mime_type: str = Field(..., description="MIME 类型")
    file_type: str = Field(..., description="文件分类：image / video / other")
    url: str = Field(..., description="文件访问 URL")
    created_at: datetime | None = Field(None, description="上传时间")

    @field_serializer("created_at", when_used="always")
    @classmethod
    def serialize_created_at(cls, v):
        """自动将 datetime 转为 ISO 字符串"""
        if isinstance(v, datetime):
            return v.isoformat()
        return v

    model_config = {"from_attributes": True}

    @classmethod
    def from_attachment(cls, obj, base_url: str) -> "AttachmentResponse":
        """从 Attachment ORM 对象构造响应体，自动计算访问 URL。

        注：原方法名 ``from_orm`` 与 Pydantic v1 的 ``BaseModel.from_orm``
        撞名，容易让人误以为是 v1 API（v2 已改用
        ``model_config["from_attributes"]``），故重命名为 ``from_attachment``。

        用法:
            AttachmentResponse.from_attachment(orm_obj, str(request.base_url))
        """
        url = FileService.get_file_url(obj.file_path, base_url)
        data = {
            "id": obj.id,
            "owner_type": getattr(obj, "owner_type", "user"),
            "owner_id": getattr(obj, "owner_id", getattr(obj, "user_id", 0)),
            "original_name": obj.original_name,
            "stored_name": obj.stored_name,
            "file_path": obj.file_path,
            "file_size": obj.file_size,
            "mime_type": obj.mime_type,
            "file_type": obj.file_type,
            "created_at": obj.created_at,
            "url": url,
        }
        return cls.model_validate(data)


class AttachmentListResponse(BaseModel):
    """文件列表响应体"""

    items: list[AttachmentResponse] = Field(..., description="文件列表")
    total: int = Field(..., description="总记录数")
    page: int = Field(..., description="当前页码")
    size: int = Field(..., description="每页条数")
    total_page: int = Field(..., description="总页数")

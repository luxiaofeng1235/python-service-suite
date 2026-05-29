"""
============================================
文件上传数据模型模块
============================================
定义文件上传相关的 Pydantic 响应体。
"""

from pydantic import BaseModel, Field


class AttachmentResponse(BaseModel):
    """文件上传成功后的响应体"""

    id: int = Field(..., description="文件ID")
    original_name: str = Field(..., description="原始文件名")
    stored_name: str = Field(..., description="存储文件名")
    file_path: str = Field(..., description="文件相对路径")
    file_size: int = Field(..., description="文件大小（字节）")
    mime_type: str = Field(..., description="MIME 类型")
    file_type: str = Field(..., description="文件分类：image / video / other")
    url: str = Field(..., description="文件访问 URL")
    created_at: str | None = Field(None, description="上传时间")

    model_config = {"from_attributes": True}


class AttachmentListResponse(BaseModel):
    """文件列表响应体"""

    items: list[AttachmentResponse] = Field(..., description="文件列表")
    total: int = Field(..., description="总记录数")
    page: int = Field(..., description="当前页码")
    size: int = Field(..., description="每页条数")

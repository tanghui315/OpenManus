from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime
from uuid import UUID


class TemplateRequest(BaseModel):
    """模板创建/更新请求模型"""

    name: str = Field(..., description="模板名称")
    description: str = Field(..., description="模板描述")
    document_type: str = Field(..., description="文档类型")
    content: str = Field(..., description="模板内容")
    variables: Dict[str, Any] = Field(default_factory=dict, description="模板变量定义")
    tags: List[str] = Field(default_factory=list, description="模板标签")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="额外元数据")


class TemplateResponse(BaseModel):
    """模板响应模型"""

    id: str = Field(..., description="模板ID")
    name: str = Field(..., description="模板名称")
    description: str = Field(..., description="模板描述")
    document_type: str = Field(..., description="文档类型")
    content: str = Field(..., description="模板内容")
    variables: Dict[str, Any] = Field(..., description="模板变量定义")
    tags: List[str] = Field(..., description="模板标签")
    metadata: Dict[str, Any] = Field(..., description="额外元数据")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: Optional[datetime] = Field(None, description="最后更新时间")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class TemplateListResponse(BaseModel):
    """模板列表响应模型"""

    items: List[TemplateResponse] = Field(..., description="模板列表")
    total: int = Field(..., description="总记录数")
    page: int = Field(..., description="当前页码")
    page_size: int = Field(..., description="每页记录数")


class TemplateDeleteResponse(BaseModel):
    """模板删除响应模型"""

    success: bool = Field(..., description="是否删除成功")
    id: str = Field(..., description="被删除的模板ID")

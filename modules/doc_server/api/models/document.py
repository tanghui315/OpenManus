from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class DocumentType(str, Enum):
    """文档类型枚举"""

    GENERAL = "general"
    REQUIREMENT = "requirement"
    DESIGN = "design"
    API = "api"
    CODE_REVIEW = "code_review"
    REPORT = "report"
    MEETING = "meeting"


class IntentType(str, Enum):
    """意图类型枚举"""

    CREATE = "create"
    EDIT = "edit"
    REVIEW = "review"
    ANALYZE = "analyze"


class DocumentChunk(BaseModel):
    """文档块模型"""

    section_id: str = Field(..., description="节点ID")
    section_title: str = Field(..., description="节点标题")
    section_type: str = Field(default="text", description="节点类型")
    content: str = Field(..., description="节点内容")
    timestamp: Optional[str] = Field(None, description="生成时间戳")


class DocumentRequest(BaseModel):
    """文档创建请求模型"""

    title: Optional[str] = Field(None, description="文档标题")
    document_type: Optional[DocumentType] = Field(None, description="文档类型")
    template_id: Optional[str] = Field(None, description="模板ID")
    user_query: str = Field(..., description="用户请求/需求描述")
    reference_documents: Optional[List[str]] = Field(None, description="参考文档ID列表")
    metadata: Optional[Dict[str, Any]] = Field(None, description="额外元数据")


class DocumentResponse(BaseModel):
    """文档响应模型"""

    document_id: str = Field(..., description="文档ID")
    title: str = Field(..., description="文档标题")
    content: str = Field(..., description="文档内容")
    template_used: Optional[str] = Field(None, description="使用的模板ID")
    created_at: str = Field(..., description="创建时间")
    chunks: List[DocumentChunk] = Field(default_factory=list, description="文档块列表")
    metadata: Optional[Dict[str, Any]] = Field(None, description="额外元数据")


class DocumentStreamRequest(DocumentRequest):
    """文档流式生成请求模型"""

    streaming: bool = Field(default=True, description="是否使用流式响应")
    max_tokens: Optional[int] = Field(None, description="最大生成Token数")


class DocumentChunkResponse(BaseModel):
    """文档块响应模型，用于流式响应"""

    type: str = Field(default="chunk", description="响应类型：chunk/complete/error")
    document_id: str = Field(..., description="文档ID")
    content: str = Field(..., description="块内容")
    progress: int = Field(default=0, description="生成进度（百分比）")
    metadata: Optional[Dict[str, Any]] = Field(None, description="块元数据")


class DocumentStreamCompleteResponse(BaseModel):
    """文档流式生成完成响应模型"""

    type: str = Field(default="complete", description="响应类型：complete")
    document_id: str = Field(..., description="文档ID")
    content: str = Field(..., description="完整文档内容")
    chunks: List[Dict[str, Any]] = Field(default_factory=list, description="所有文档块")
    progress: int = Field(default=100, description="完成度")
    metadata: Optional[Dict[str, Any]] = Field(None, description="元数据")

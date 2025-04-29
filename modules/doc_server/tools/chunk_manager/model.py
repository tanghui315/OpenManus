"""
文档Chunk管理工具的数据模型
定义用于文档块管理的数据结构
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field

from modules.doc_server.api.models.document import DocumentChunk


class ChunkOperation(str):
    """Chunk操作类型"""

    ADD = "add"  # 添加新块
    UPDATE = "update"  # 更新现有块
    DELETE = "delete"  # 删除块
    MERGE = "merge"  # 合并多个块
    SPLIT = "split"  # 拆分块
    REORDER = "reorder"  # 重新排序块


class ChunkRequest(BaseModel):
    """Chunk请求模型"""

    document_id: str = Field(..., description="文档ID")
    operation: str = Field(..., description="操作类型")
    section_id: Optional[str] = Field(None, description="节点ID，对于添加操作可以为空")
    section_title: Optional[str] = Field(None, description="节点标题")
    section_type: str = Field(default="text", description="节点类型")
    content: Optional[str] = Field(None, description="节点内容")
    position: Optional[int] = Field(None, description="插入位置索引")
    target_ids: Optional[List[str]] = Field(
        None, description="目标节点ID列表，用于合并或拆分操作"
    )


class ChunkResponse(BaseModel):
    """Chunk响应模型"""

    success: bool = Field(..., description="操作是否成功")
    document_id: str = Field(..., description="文档ID")
    operation: str = Field(..., description="执行的操作")
    chunk: Optional[DocumentChunk] = Field(None, description="操作结果块")
    chunks: Optional[List[DocumentChunk]] = Field(None, description="操作结果块列表")
    error: Optional[str] = Field(None, description="错误信息")


class ChunkManagerResult(BaseModel):
    """Chunk管理器操作结果"""

    success: bool = Field(True, description="操作是否成功")
    document_id: str = Field(..., description="文档ID")
    operation: str = Field(..., description="执行的操作")
    chunks: List[DocumentChunk] = Field(
        default_factory=list, description="操作后的文档块列表"
    )
    affected_chunks: List[DocumentChunk] = Field(
        default_factory=list, description="受影响的文档块"
    )
    error: Optional[str] = Field(None, description="错误信息")

    class Config:
        schema_extra = {
            "example": {
                "success": True,
                "document_id": "doc-123456",
                "operation": "add",
                "chunks": [
                    {
                        "section_id": "1",
                        "section_title": "简介",
                        "section_type": "text",
                        "content": "这是文档简介部分",
                    }
                ],
                "affected_chunks": [
                    {
                        "section_id": "1",
                        "section_title": "简介",
                        "section_type": "text",
                        "content": "这是文档简介部分",
                    }
                ],
            }
        }

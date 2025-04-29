"""
计数工具的数据模型
定义用于计数统计的数据结构
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class CountRequest(BaseModel):
    """计数请求模型"""

    text: Optional[str] = Field(None, description="要计算字数的文本")
    document_id: Optional[str] = Field(None, description="文档ID")
    count_type: str = Field(
        default="words", description="计数类型：words/chars/paragraphs/sections"
    )
    include_spaces: bool = Field(default=False, description="是否包含空格")
    include_punctuation: bool = Field(default=True, description="是否包含标点符号")


class CountStats(BaseModel):
    """计数统计结果"""

    words: int = Field(default=0, description="单词数")
    chars: int = Field(default=0, description="字符数")
    chars_no_spaces: int = Field(default=0, description="不包含空格的字符数")
    paragraphs: int = Field(default=0, description="段落数")
    sections: int = Field(default=0, description="章节数")
    sentences: int = Field(default=0, description="句子数")
    reading_time: float = Field(default=0, description="阅读时间（分钟）")


class CountResult(BaseModel):
    """计数工具结果"""

    success: bool = Field(default=True, description="是否成功")
    count_type: str = Field(..., description="计数类型")
    count: int = Field(default=0, description="计数结果")
    stats: CountStats = Field(default_factory=CountStats, description="详细统计信息")
    source: str = Field(default="text", description="计数来源：text/document")
    text_preview: Optional[str] = Field(None, description="文本预览")
    document_id: Optional[str] = Field(None, description="文档ID")
    section_stats: Optional[Dict[str, int]] = Field(None, description="各章节统计")
    error: Optional[str] = Field(None, description="错误信息")

    class Config:
        schema_extra = {
            "example": {
                "success": True,
                "count_type": "words",
                "count": 256,
                "stats": {
                    "words": 256,
                    "chars": 1500,
                    "chars_no_spaces": 1244,
                    "paragraphs": 5,
                    "sections": 3,
                    "sentences": 12,
                    "reading_time": 1.28,
                },
                "source": "document",
                "text_preview": "文档内容预览...",
                "document_id": "doc-123456",
                "section_stats": {"章节1": 100, "章节2": 86, "章节3": 70},
            }
        }

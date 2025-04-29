"""
意图检测模型
定义用于意图检测的数据模型
"""

from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field

from modules.doc_server.config import IntentType


class IntentDetectionResult(BaseModel):
    """意图检测结果模型"""

    intent_type: IntentType = Field(
        default=IntentType.UNKNOWN, description="检测到的主要意图类型"
    )

    confidence: float = Field(default=0.0, description="意图检测的置信度，范围0-1")

    sub_intents: Dict[IntentType, float] = Field(
        default_factory=dict, description="检测到的所有子意图及其置信度"
    )

    original_query: str = Field(default="", description="原始用户查询")

    entities: Dict[str, Any] = Field(
        default_factory=dict, description="从查询中提取的实体"
    )

    explanation: Optional[str] = Field(
        default=None, description="意图检测结果的解释说明"
    )

    error: Optional[str] = Field(default=None, description="意图检测过程中的错误信息")

    class Config:
        schema_extra = {
            "example": {
                "intent_type": "CREATE",
                "confidence": 0.85,
                "sub_intents": {"CREATE": 0.85, "EXPLAIN": 0.25},
                "original_query": "帮我生成一份项目周报",
                "entities": {"document_type": "REPORT", "topic": "项目周报"},
                "explanation": "用户希望创建一份项目周报文档",
            }
        }

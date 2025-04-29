"""
文档服务器配置
包含文档服务相关的配置项和常量
"""

from enum import Enum, auto
from typing import Any, Dict, List, Optional


class IntentType(str, Enum):
    """用户意图类型枚举"""

    CREATE = "CREATE"  # 创建/生成意图
    QUERY = "QUERY"  # 查询/搜索意图
    EXPLAIN = "EXPLAIN"  # 解释/说明意图
    SUMMARIZE = "SUMMARIZE"  # 总结/概括意图
    COMPARE = "COMPARE"  # 比较/对比意图
    LIST = "LIST"  # 列举/枚举意图
    UNKNOWN = "UNKNOWN"  # 未知意图


class DocumentType(str, Enum):
    """文档类型枚举"""

    REPORT = "REPORT"  # 报告
    GUIDE = "GUIDE"  # 指南
    MANUAL = "MANUAL"  # 手册
    TUTORIAL = "TUTORIAL"  # 教程
    ARTICLE = "ARTICLE"  # 文章
    OTHER = "OTHER"  # 其他

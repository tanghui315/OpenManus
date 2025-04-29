"""
文档服务工具集
复用并扩展OpenManus现有工具集
"""

from modules.doc_server.tools.ask_human import AskHumanTool
from modules.doc_server.tools.chunk_manager import ChunkManagerTool
from modules.doc_server.tools.counter import CounterTool
from modules.doc_server.tools.intent_detector import IntentDetectorTool
from modules.doc_server.tools.rag_retriever import RAGRetrieverTool

# 导出所有工具
__all__ = [
    "IntentDetectorTool",
    "RAGRetrieverTool",
    "ChunkManagerTool",
    "CounterTool",
    "AskHumanTool",
    "get_all_tools",
]


def get_all_tools():
    """
    获取所有可用的文档服务工具

    Returns:
        工具列表
    """
    return [
        IntentDetectorTool(),
        RAGRetrieverTool(),
        ChunkManagerTool(),
        CounterTool(),
        AskHumanTool(),
    ]

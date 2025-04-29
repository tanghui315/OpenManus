"""
用户交互工具包
负责与用户交互并获取反馈，复用OpenManus的ask_human工具
"""

from modules.doc_server.tools.ask_human.tool import AskHumanTool

__all__ = ["AskHumanTool"]

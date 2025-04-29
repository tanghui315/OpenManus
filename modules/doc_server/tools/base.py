from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field
import abc

# 复用OpenManus的工具基类，扩展添加doc_server特有功能
from app.tool.base import BaseTool, BaseToolResponse

class DocServerTool(BaseTool):
    """文档服务工具基类，扩展BaseTool添加文档服务特有功能"""

    async def initialize(self):
        """工具初始化方法"""
        await super().initialize()
        # 添加文档服务特有的初始化逻辑

    @classmethod
    def get_tool_config(cls) -> Dict[str, Any]:
        """获取工具配置"""
        config = super().get_tool_config()
        # 添加文档服务特有的配置
        return config

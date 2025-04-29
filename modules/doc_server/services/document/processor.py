from typing import Dict, Any, List, Optional
import json
import os

# 复用OpenManus的LLM交互
from app.llm import LLM
from app.logger import setup_logger

logger = setup_logger("doc_server.document_processor")

class DocumentProcessor:
    """文档处理服务，负责文档生成的核心逻辑"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.llm = LLM()  # 使用OpenManus的LLM

    async def load_template(self, template_id: str) -> List[Dict[str, Any]]:
        """加载文档模板"""
        templates_dir = self.config.get("templates_dir", "modules/doc_server/templates")
        template_path = os.path.join(templates_dir, f"{template_id}.json")

        if not os.path.exists(template_path):
            logger.error(f"Template not found: {template_path}")
            raise FileNotFoundError(f"Template {template_id} not found")

        try:
            with open(template_path, "r", encoding="utf-8") as f:
                template = json.load(f)
            return template
        except Exception as e:
            logger.error(f"Failed to load template {template_id}: {str(e)}")
            raise

    async def process_template_node(self, node: Dict[str, Any], context: Dict[str, Any]) -> str:
        """处理单个模板节点"""
        # 这里实现节点处理逻辑
        # 暂时返回占位内容
        return f"Generated content for {node.get('title', 'Untitled')}"

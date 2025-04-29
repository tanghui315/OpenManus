import os
import json
import uuid
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from pathlib import Path

from modules.doc_server.config import settings

logger = logging.getLogger(__name__)

class TemplateManager:
    """模板管理器，处理模板的创建、查询、更新和删除操作"""

    def __init__(self, db_client=None):
        """
        初始化模板管理器

        Args:
            db_client: 数据库客户端
        """
        self.db_client = db_client
        # 临时存储，实际应用中应使用数据库
        self.templates: Dict[str, Dict[str, Any]] = {}

    async def create_template(self, name: str, document_type: str, content: str, description: Optional[str] = None) -> Dict[str, Any]:
        """
        创建新模板

        Args:
            name: 模板名称
            document_type: 文档类型
            content: 模板内容
            description: 模板描述

        Returns:
            创建的模板信息
        """
        try:
            template_id = str(uuid.uuid4())
            now = datetime.now().isoformat()

            template = {
                "id": template_id,
                "name": name,
                "document_type": document_type,
                "content": content,
                "description": description,
                "created_at": now,
                "updated_at": now
            }

            # 保存到临时存储，实际应用中应保存到数据库
            self.templates[template_id] = template

            return template
        except Exception as e:
            logger.error(f"创建模板失败: {str(e)}")
            raise

    async def get_template(self, template_id: str) -> Optional[Dict[str, Any]]:
        """
        通过ID获取模板

        Args:
            template_id: 模板ID

        Returns:
            模板信息，如果不存在则返回None
        """
        try:
            return self.templates.get(template_id)
        except Exception as e:
            logger.error(f"获取模板失败: {str(e)}")
            raise

    async def list_templates(self, skip: int = 0, limit: int = 10, document_type: Optional[str] = None) -> Dict[str, Any]:
        """
        列出模板

        Args:
            skip: 跳过的记录数
            limit: 返回的记录数
            document_type: 按文档类型过滤

        Returns:
            模板列表及分页信息
        """
        try:
            templates = list(self.templates.values())

            # 按文档类型过滤
            if document_type:
                templates = [t for t in templates if t["document_type"] == document_type]

            # 计算总数量
            total = len(templates)

            # 分页
            paginated_templates = templates[skip:skip + limit]

            return {
                "templates": paginated_templates,
                "total": total,
                "skip": skip,
                "limit": limit
            }
        except Exception as e:
            logger.error(f"列出模板失败: {str(e)}")
            raise

    async def update_template(self, template_id: str, name: str, document_type: str, content: str, description: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        更新模板

        Args:
            template_id: 模板ID
            name: 模板名称
            document_type: 文档类型
            content: 模板内容
            description: 模板描述

        Returns:
            更新后的模板信息，如果模板不存在则返回None
        """
        try:
            template = self.templates.get(template_id)
            if not template:
                return None

            # 更新模板信息
            template["name"] = name
            template["document_type"] = document_type
            template["content"] = content
            template["description"] = description
            template["updated_at"] = datetime.now().isoformat()

            # 保存更新
            self.templates[template_id] = template

            return template
        except Exception as e:
            logger.error(f"更新模板失败: {str(e)}")
            raise

    async def delete_template(self, template_id: str) -> bool:
        """
        删除模板

        Args:
            template_id: 模板ID

        Returns:
            是否成功删除
        """
        try:
            if template_id in self.templates:
                del self.templates[template_id]
                return True
            return False
        except Exception as e:
            logger.error(f"删除模板失败: {str(e)}")
            raise

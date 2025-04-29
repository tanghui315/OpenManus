from typing import Dict, List, Optional
from datetime import datetime
import uuid

from modules.doc_server.api.models.template import TemplateRequest, TemplateResponse
from modules.doc_server.database.template import TemplateStorage


class TemplateService:
    """模板服务类，提供模板的增删改查操作"""

    def __init__(self):
        self.storage = TemplateStorage()

    async def create_template(self, template_data: TemplateRequest) -> TemplateResponse:
        """
        创建新模板

        Args:
            template_data: 模板创建请求数据

        Returns:
            创建的模板响应
        """
        template_id = str(uuid.uuid4())
        now = datetime.now()

        template = {
            "id": template_id,
            "name": template_data.name,
            "document_type": template_data.document_type,
            "content": template_data.content,
            "description": template_data.description,
            "created_at": now,
            "updated_at": now
        }

        await self.storage.save(template)

        return TemplateResponse(**template)

    async def get_template(self, template_id: str) -> Optional[TemplateResponse]:
        """
        获取模板详情

        Args:
            template_id: 模板ID

        Returns:
            模板响应，如果找不到则返回None
        """
        template = await self.storage.get(template_id)

        if not template:
            return None

        return TemplateResponse(**template)

    async def list_templates(
        self,
        page: int = 1,
        page_size: int = 10,
        document_type: Optional[str] = None
    ) -> Dict:
        """
        获取模板列表

        Args:
            page: 页码
            page_size: 每页数量
            document_type: 文档类型过滤

        Returns:
            包含模板列表和分页信息的字典
        """
        skip = (page - 1) * page_size

        templates, total = await self.storage.list(
            skip=skip,
            limit=page_size,
            document_type=document_type
        )

        items = [TemplateResponse(**template) for template in templates]

        return {
            "total": total,
            "items": items,
            "page_info": {
                "page": page,
                "page_size": page_size,
                "total_pages": (total + page_size - 1) // page_size
            }
        }

    async def update_template(
        self,
        template_id: str,
        template_data: TemplateRequest
    ) -> Optional[TemplateResponse]:
        """
        更新模板

        Args:
            template_id: 模板ID
            template_data: 模板更新请求数据

        Returns:
            更新后的模板响应，如果找不到则返回None
        """
        existing_template = await self.storage.get(template_id)

        if not existing_template:
            return None

        template = {
            **existing_template,
            "name": template_data.name,
            "document_type": template_data.document_type,
            "content": template_data.content,
            "description": template_data.description,
            "updated_at": datetime.now()
        }

        await self.storage.update(template_id, template)

        return TemplateResponse(**template)

    async def delete_template(self, template_id: str) -> bool:
        """
        删除模板

        Args:
            template_id: 模板ID

        Returns:
            删除是否成功
        """
        existing_template = await self.storage.get(template_id)

        if not existing_template:
            return False

        await self.storage.delete(template_id)

        return True

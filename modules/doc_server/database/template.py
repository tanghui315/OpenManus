from typing import Dict, List, Optional, Tuple, Any
import motor.motor_asyncio
from bson.objectid import ObjectId
from datetime import datetime

from modules.doc_server.config import get_settings

settings = get_settings()


class TemplateStorage:
    """模板存储类，负责模板数据的存储与检索"""

    def __init__(self):
        """初始化数据库连接"""
        client = motor.motor_asyncio.AsyncIOMotorClient(settings.MONGODB_URL)
        self.db = client[settings.MONGODB_DATABASE]
        self.collection = self.db.templates

    async def save(self, template: Dict[str, Any]) -> str:
        """
        保存模板到数据库

        Args:
            template: 模板数据

        Returns:
            模板ID
        """
        # 如果传入的时间是datetime对象，需要保持原样，MongoDB会自动处理
        result = await self.collection.insert_one(template)
        return str(result.inserted_id)

    async def get(self, template_id: str) -> Optional[Dict[str, Any]]:
        """
        根据ID获取模板

        Args:
            template_id: 模板ID

        Returns:
            模板数据，如果不存在则返回None
        """
        try:
            template = await self.collection.find_one({"id": template_id})
            if not template:
                return None

            # MongoDB的_id字段转为字符串返回
            template["_id"] = str(template["_id"])
            return template
        except Exception as e:
            print(f"获取模板出错: {e}")
            return None

    async def list(
        self,
        skip: int = 0,
        limit: int = 10,
        document_type: Optional[str] = None
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        获取模板列表

        Args:
            skip: 跳过的记录数
            limit: 返回的记录数
            document_type: 文档类型过滤

        Returns:
            包含模板列表和总记录数的元组
        """
        # 构建查询条件
        query = {}
        if document_type:
            query["document_type"] = document_type

        # 获取总记录数
        total = await self.collection.count_documents(query)

        # 查询记录并排序
        cursor = self.collection.find(query).sort("created_at", -1).skip(skip).limit(limit)
        templates = []

        async for template in cursor:
            template["_id"] = str(template["_id"])
            templates.append(template)

        return templates, total

    async def update(self, template_id: str, template: Dict[str, Any]) -> bool:
        """
        更新模板

        Args:
            template_id: 模板ID
            template: 更新的模板数据

        Returns:
            是否更新成功
        """
        try:
            result = await self.collection.update_one(
                {"id": template_id},
                {"$set": template}
            )
            return result.modified_count > 0
        except Exception as e:
            print(f"更新模板出错: {e}")
            return False

    async def delete(self, template_id: str) -> bool:
        """
        删除模板

        Args:
            template_id: 模板ID

        Returns:
            是否删除成功
        """
        try:
            result = await self.collection.delete_one({"id": template_id})
            return result.deleted_count > 0
        except Exception as e:
            print(f"删除模板出错: {e}")
            return False

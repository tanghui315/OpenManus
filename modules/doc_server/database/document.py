"""
文档数据库存储
负责文档和文档块的存储与检索
"""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Union

import motor.motor_asyncio
from bson.objectid import ObjectId

from modules.doc_server.config import get_settings

settings = get_settings()


class DocumentStorage:
    """文档存储类，负责文档和文档块的存储与检索"""

    def __init__(self):
        """初始化数据库连接"""
        client = motor.motor_asyncio.AsyncIOMotorClient(settings.MONGODB_URL)
        self.db = client[settings.MONGODB_DATABASE]
        self.documents = self.db.documents
        self.chunks = self.db.document_chunks

    async def save_document(self, document: Dict[str, Any]) -> str:
        """
        保存文档到数据库

        Args:
            document: 文档数据

        Returns:
            文档ID
        """
        if "id" not in document:
            document["id"] = str(uuid.uuid4())

        if "created_at" not in document:
            document["created_at"] = datetime.now()

        document["updated_at"] = datetime.now()

        result = await self.documents.insert_one(document)
        return document["id"]

    async def get_document(self, document_id: str) -> Optional[Dict[str, Any]]:
        """
        根据ID获取文档

        Args:
            document_id: 文档ID

        Returns:
            文档数据，如果不存在则返回None
        """
        document = await self.documents.find_one({"id": document_id})
        if not document:
            return None

        # MongoDB的_id字段转为字符串返回
        document["_id"] = str(document["_id"])

        # 获取文档的所有块
        chunks = await self.get_document_chunks(document_id)
        if chunks:
            document["chunks"] = chunks

        return document

    async def update_document(self, document_id: str, document: Dict[str, Any]) -> bool:
        """
        更新文档

        Args:
            document_id: 文档ID
            document: 更新的文档数据

        Returns:
            是否更新成功
        """
        document["updated_at"] = datetime.now()

        result = await self.documents.update_one(
            {"id": document_id}, {"$set": document}
        )
        return result.modified_count > 0

    async def delete_document(self, document_id: str) -> bool:
        """
        删除文档及其所有块

        Args:
            document_id: 文档ID

        Returns:
            是否删除成功
        """
        # 删除文档
        result = await self.documents.delete_one({"id": document_id})

        # 删除文档的所有块
        await self.chunks.delete_many({"document_id": document_id})

        return result.deleted_count > 0

    async def save_chunk(self, chunk: Dict[str, Any]) -> str:
        """
        保存文档块到数据库

        Args:
            chunk: 文档块数据

        Returns:
            块ID
        """
        if "id" not in chunk:
            chunk["id"] = str(uuid.uuid4())

        if "created_at" not in chunk:
            chunk["created_at"] = datetime.now()

        chunk["updated_at"] = datetime.now()

        result = await self.chunks.insert_one(chunk)
        return chunk["id"]

    async def get_chunk(self, chunk_id: str) -> Optional[Dict[str, Any]]:
        """
        根据ID获取文档块

        Args:
            chunk_id: 块ID

        Returns:
            块数据，如果不存在则返回None
        """
        chunk = await self.chunks.find_one({"id": chunk_id})
        if not chunk:
            return None

        # MongoDB的_id字段转为字符串返回
        chunk["_id"] = str(chunk["_id"])
        return chunk

    async def get_document_chunks(self, document_id: str) -> List[Dict[str, Any]]:
        """
        获取文档的所有块

        Args:
            document_id: 文档ID

        Returns:
            文档块列表
        """
        cursor = self.chunks.find({"document_id": document_id}).sort("position", 1)
        chunks = []

        async for chunk in cursor:
            chunk["_id"] = str(chunk["_id"])
            chunks.append(chunk)

        return chunks

    async def update_chunk(self, chunk_id: str, chunk: Dict[str, Any]) -> bool:
        """
        更新文档块

        Args:
            chunk_id: 块ID
            chunk: 更新的块数据

        Returns:
            是否更新成功
        """
        chunk["updated_at"] = datetime.now()

        result = await self.chunks.update_one({"id": chunk_id}, {"$set": chunk})
        return result.modified_count > 0

    async def delete_chunk(self, chunk_id: str) -> bool:
        """
        删除文档块

        Args:
            chunk_id: 块ID

        Returns:
            是否删除成功
        """
        result = await self.chunks.delete_one({"id": chunk_id})
        return result.deleted_count > 0

    async def delete_document_chunks(self, document_id: str) -> bool:
        """
        删除文档的所有块

        Args:
            document_id: 文档ID

        Returns:
            是否删除成功
        """
        result = await self.chunks.delete_many({"document_id": document_id})
        return result.deleted_count > 0

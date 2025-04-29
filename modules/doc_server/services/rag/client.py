"""
RAG服务客户端
负责与外部RAG服务进行交互，提供检索功能
"""

import json
from typing import Any, Dict, List, Optional

import aiohttp
from pydantic import BaseModel, Field

from app.logger import setup_logger

logger = setup_logger("doc_server.services.rag.client")


class RAGClientConfig(BaseModel):
    """RAG客户端配置"""

    base_url: str = Field(..., description="RAG服务基础URL")
    api_key: Optional[str] = Field(None, description="RAG服务API密钥")
    default_timeout: int = Field(30, description="默认请求超时时间(秒)")
    retry_count: int = Field(3, description="重试次数")


class RAGClient:
    """RAG服务客户端"""

    def __init__(self, config: Dict[str, Any]):
        """
        初始化RAG客户端

        Args:
            config: 客户端配置
        """
        self.config = RAGClientConfig(**config)
        self.session = None
        logger.info(f"初始化RAG客户端: {self.config.base_url}")

    async def _ensure_session(self):
        """确保HTTP会话已创建"""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(headers=self._get_default_headers())

    def _get_default_headers(self) -> Dict[str, str]:
        """获取默认HTTP请求头"""
        headers = {"Content-Type": "application/json", "Accept": "application/json"}

        # 添加API密钥（如果配置了）
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"

        return headers

    async def close(self):
        """关闭客户端"""
        if self.session and not self.session.closed:
            await self.session.close()
            self.session = None

    async def retrieve(
        self,
        query: str,
        document_ids: Optional[List[str]] = None,
        top_k: int = 5,
        filters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        执行RAG检索

        Args:
            query: 检索查询文本
            document_ids: 限定检索范围的文档ID列表（可选）
            top_k: 返回的最大结果数量
            filters: 检索过滤条件（可选）

        Returns:
            检索结果
        """
        await self._ensure_session()

        endpoint = f"{self.config.base_url.rstrip('/')}/retrieve"

        # 准备请求数据
        payload = {"query": query, "top_k": top_k}

        # 添加可选参数
        if document_ids:
            payload["document_ids"] = document_ids

        if filters:
            payload["filters"] = filters

        try:
            # 发送请求
            async with self.session.post(
                endpoint, json=payload, timeout=self.config.default_timeout
            ) as response:
                # 解析响应
                if response.status == 200:
                    result = await response.json()
                    return {
                        "success": True,
                        "results": result.get("results", []),
                        "metadata": result.get("metadata", {}),
                    }
                else:
                    error_text = await response.text()
                    logger.error(f"RAG检索失败 [{response.status}]: {error_text}")
                    return {
                        "success": False,
                        "error": f"服务错误 ({response.status}): {error_text}",
                    }
        except aiohttp.ClientError as e:
            logger.error(f"RAG检索请求失败: {str(e)}")
            return {"success": False, "error": f"请求错误: {str(e)}"}
        except Exception as e:
            logger.error(f"RAG检索未知错误: {str(e)}")
            return {"success": False, "error": f"未知错误: {str(e)}"}

    async def index_document(
        self, document_id: str, content: str, metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        索引文档内容

        Args:
            document_id: 文档ID
            content: 文档内容
            metadata: 文档元数据（可选）

        Returns:
            索引结果
        """
        await self._ensure_session()

        endpoint = f"{self.config.base_url.rstrip('/')}/index"

        # 准备请求数据
        payload = {"document_id": document_id, "content": content}

        # 添加元数据（如果有）
        if metadata:
            payload["metadata"] = metadata

        try:
            # 发送请求
            async with self.session.post(
                endpoint, json=payload, timeout=self.config.default_timeout
            ) as response:
                # 解析响应
                if response.status == 200:
                    result = await response.json()
                    return {
                        "success": True,
                        "document_id": result.get("document_id", document_id),
                        "metadata": result.get("metadata", {}),
                    }
                else:
                    error_text = await response.text()
                    logger.error(f"文档索引失败 [{response.status}]: {error_text}")
                    return {
                        "success": False,
                        "error": f"服务错误 ({response.status}): {error_text}",
                    }
        except aiohttp.ClientError as e:
            logger.error(f"文档索引请求失败: {str(e)}")
            return {"success": False, "error": f"请求错误: {str(e)}"}
        except Exception as e:
            logger.error(f"文档索引未知错误: {str(e)}")
            return {"success": False, "error": f"未知错误: {str(e)}"}

    async def delete_document(self, document_id: str) -> Dict[str, Any]:
        """
        从RAG服务中删除指定文档的索引

        Args:
            document_id: 文档唯一标识符

        Returns:
            删除操作结果
        """
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.config.base_url}/documents/{document_id}"
                async with session.delete(
                    url,
                    headers=self._get_default_headers(),
                    timeout=self.config.default_timeout,
                ) as response:
                    if response.status not in (200, 204):
                        error_text = await response.text()
                        logger.error(f"删除文档索引失败: {error_text}")
                        return {
                            "success": False,
                            "error": f"删除请求失败: {response.status} - {error_text}",
                        }

                    logger.info(f"文档 {document_id} 索引已删除")
                    return {"success": True, "document_id": document_id}

        except Exception as e:
            logger.error(f"删除文档索引时发生错误: {str(e)}")
            return {"success": False, "error": f"删除请求异常: {str(e)}"}

    async def health_check(self) -> Dict[str, Any]:
        """
        检查RAG服务健康状态

        Returns:
            健康检查结果
        """
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.config.base_url}/health"
                async with session.get(
                    url,
                    headers=self._get_default_headers(),
                    timeout=self.config.default_timeout,
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"RAG服务健康检查失败: {error_text}")
                        return {
                            "status": "error",
                            "message": f"健康检查失败: {response.status} - {error_text}",
                        }

                    result = await response.json()
                    logger.debug("RAG服务健康检查成功")
                    return result

        except Exception as e:
            logger.error(f"RAG服务健康检查时发生错误: {str(e)}")
            return {"status": "error", "message": f"健康检查异常: {str(e)}"}

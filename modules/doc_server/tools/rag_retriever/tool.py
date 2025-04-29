"""
RAG检索工具
负责从外部RAG服务中检索相关内容
"""

import json
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.logger import setup_logger
from modules.doc_server.services.rag.client import RAGClient
from modules.doc_server.tools.base import DocServerTool

logger = setup_logger("doc_server.tools.rag_retriever")


class RAGRetrievalResult(BaseModel):
    """RAG检索结果"""

    results: List[Dict[str, Any]] = Field(
        default_factory=list, description="检索结果列表"
    )
    total_results: int = Field(0, description="结果总数")
    query: str = Field("", description="原始查询")
    document_ids: Optional[List[str]] = Field(None, description="检索范围文档ID列表")

    # 结果元数据
    execution_time: Optional[float] = Field(None, description="执行时间(秒)")
    error: Optional[str] = Field(None, description="错误信息(如有)")


class RAGRetrieverTool(DocServerTool):
    """RAG检索工具，负责从外部RAG服务中检索相关内容"""

    def initialize(self, **kwargs) -> None:
        """
        初始化工具

        Args:
            kwargs: 初始化参数，包括RAG客户端配置
        """
        super().initialize(**kwargs)

        # 从配置中获取RAG客户端配置
        rag_config = kwargs.get("rag_config", {})
        if not rag_config:
            logger.warning("未提供RAG客户端配置，将使用默认配置")
            rag_config = {"base_url": "http://localhost:8000/api/rag", "api_key": None}

        # 创建RAG客户端
        self.rag_client = RAGClient(rag_config)

        # 设置默认参数
        self.default_top_k = kwargs.get("default_top_k", 5)

        logger.info("RAG检索工具初始化完成")

    async def execute(
        self,
        query: str,
        document_ids: Optional[List[str]] = None,
        top_k: Optional[int] = None,
        filters: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> RAGRetrievalResult:
        """
        执行RAG检索

        Args:
            query: 检索查询文本
            document_ids: 限定检索范围的文档ID列表(可选)
            top_k: 返回的最大结果数量(默认使用工具初始化时设置的值)
            filters: 检索过滤条件(可选)
            kwargs: 其他参数

        Returns:
            RAG检索结果
        """
        if not query.strip():
            return RAGRetrievalResult(
                error="查询文本不能为空", query=query, document_ids=document_ids
            )

        # 使用默认top_k如果未指定
        if top_k is None:
            top_k = self.default_top_k

        try:
            # 调用RAG客户端执行检索
            response = await self.rag_client.retrieve(
                query=query, document_ids=document_ids, top_k=top_k, filters=filters
            )

            # 检查响应是否成功
            if not response.get("success", False):
                error_msg = response.get("error", "未知错误")
                logger.error(f"RAG检索失败: {error_msg}")
                return RAGRetrievalResult(
                    error=error_msg, query=query, document_ids=document_ids
                )

            # 提取结果
            results = response.get("results", [])
            metadata = response.get("metadata", {})

            # 创建结果对象
            result = RAGRetrievalResult(
                results=results,
                total_results=len(results),
                query=query,
                document_ids=document_ids,
                execution_time=metadata.get("execution_time"),
            )

            # 记录结果摘要
            result_summary = f"检索到 {result.total_results} 条结果"
            if result.total_results > 0:
                # 添加前几条结果的简短摘要
                sample_results = result.results[: min(3, result.total_results)]
                samples = []
                for idx, res in enumerate(sample_results):
                    content = res.get("content", "")
                    if content:
                        # 截取内容片段
                        content_preview = (
                            content[:100] + "..." if len(content) > 100 else content
                        )
                        samples.append(f"[{idx+1}] {content_preview}")

                if samples:
                    result_summary += f"，包括: {' '.join(samples)}"

            logger.info(f"RAG检索完成: {result_summary}")
            return result

        except Exception as e:
            error_msg = f"执行RAG检索时发生错误: {str(e)}"
            logger.error(error_msg)
            return RAGRetrievalResult(
                error=error_msg, query=query, document_ids=document_ids
            )

    async def cleanup(self) -> None:
        """清理资源"""
        try:
            if hasattr(self, "rag_client"):
                await self.rag_client.close()
                logger.debug("RAG客户端已关闭")
        except Exception as e:
            logger.error(f"清理RAG客户端资源时出错: {str(e)}")

        await super().cleanup()

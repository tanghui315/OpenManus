"""
流式处理工具模块，提供FastAPI的SSE流式响应支持
基于OpenManus现有流式处理能力进行扩展
"""

import asyncio
import json
from typing import Any, AsyncGenerator, Awaitable, Callable, Dict, List, Optional, Union

# 复用OpenManus的日志系统
from app.logger import setup_logger

logger = setup_logger("doc_server.utils.stream")


class StreamProcessor:
    """
    流式处理器，负责处理和格式化流式响应数据
    支持SSE（Server-Sent Events）格式
    """

    def __init__(
        self,
        event_type: str = "message",
        include_id: bool = True,
        include_retry: bool = False,
        retry_timeout: int = 3000,
    ):
        """
        初始化流式处理器

        Args:
            event_type: SSE事件类型
            include_id: 是否包含事件ID
            include_retry: 是否包含重试超时
            retry_timeout: 重试超时时间（毫秒）
        """
        self.event_type = event_type
        self.include_id = include_id
        self.include_retry = include_retry
        self.retry_timeout = retry_timeout
        self.event_id = 0

    def format_sse(
        self, data: Union[str, Dict[str, Any]], event_type: Optional[str] = None
    ) -> str:
        """
        将数据格式化为SSE格式

        Args:
            data: 要发送的数据
            event_type: 事件类型，不提供则使用默认值

        Returns:
            SSE格式的字符串
        """
        if isinstance(data, dict):
            data = json.dumps(data, ensure_ascii=False)

        buffer = []

        # 添加事件类型
        if event_type or self.event_type:
            buffer.append(f"event: {event_type or self.event_type}")

        # 添加事件ID
        if self.include_id:
            self.event_id += 1
            buffer.append(f"id: {self.event_id}")

        # 添加重试超时
        if self.include_retry:
            buffer.append(f"retry: {self.retry_timeout}")

        # 添加数据
        # 对多行数据进行处理，确保每行都有data前缀
        for line in data.split("\n"):
            buffer.append(f"data: {line}")

        # 返回完整的SSE消息
        return "\n".join(buffer) + "\n\n"

    async def process_stream(
        self,
        generator: AsyncGenerator,
        transform_func: Optional[
            Callable[
                [Any], Union[Dict[str, Any], str, Awaitable[Union[Dict[str, Any], str]]]
            ]
        ] = None,
    ) -> AsyncGenerator[str, None]:
        """
        处理异步生成器并转换为SSE格式

        Args:
            generator: 数据源异步生成器
            transform_func: 数据转换函数，将原始数据转换为所需格式

        Yields:
            SSE格式的消息
        """
        try:
            async for data in generator:
                try:
                    if transform_func:
                        result = transform_func(data)
                        if asyncio.iscoroutine(result):
                            result = await result
                        data = result

                    yield self.format_sse(data)
                except Exception as e:
                    logger.error(f"处理流数据时发生错误: {str(e)}")
                    error_data = {"type": "error", "error": str(e)}
                    yield self.format_sse(error_data, event_type="error")
        except Exception as e:
            logger.error(f"流处理器异常: {str(e)}")
            error_data = {"type": "error", "error": f"流处理器异常: {str(e)}"}
            yield self.format_sse(error_data, event_type="error")
        finally:
            # 发送完成消息
            complete_data = {"type": "complete"}
            yield self.format_sse(complete_data, event_type="complete")


class DocumentStreamProcessor(StreamProcessor):
    """
    文档流处理器，专用于处理文档生成的流式响应
    """

    def __init__(
        self,
        document_id: str,
        template_id: Optional[str] = None,
        user_id: Optional[str] = None,
        **kwargs,
    ):
        """
        初始化文档流处理器

        Args:
            document_id: 文档ID
            template_id: 模板ID
            user_id: 用户ID
        """
        super().__init__(**kwargs)
        self.document_id = document_id
        self.template_id = template_id
        self.user_id = user_id
        self.chunks: List[Dict[str, Any]] = []
        self.current_progress: int = 0
        self.total_sections: int = 0
        self.completed_sections: int = 0

    def transform_llm_chunk(self, chunk: Dict[str, Any]) -> Dict[str, Any]:
        """
        转换LLM生成的数据块为标准格式

        Args:
            chunk: LLM生成的原始数据块

        Returns:
            转换后的数据结构
        """
        # 从chunk中提取内容和元数据
        content = chunk.get("content", "")
        metadata = chunk.get("metadata", {})
        is_partial = chunk.get("is_partial", False)

        # 提取或初始化节点信息
        section_id = metadata.get("section_id", "unknown")
        section_title = metadata.get("section_title", "")
        section_type = metadata.get("section_type", "text")

        # 获取进度信息
        if "total_sections" in metadata and metadata["total_sections"] > 0:
            self.total_sections = metadata["total_sections"]
        if "section_index" in metadata and self.total_sections > 0:
            self.completed_sections = metadata["section_index"]
            self.current_progress = min(
                100, int((self.completed_sections / self.total_sections) * 100)
            )

        # 仅当不是部分内容时存储完整块
        if not is_partial:
            chunk_data = {
                "section_id": section_id,
                "section_title": section_title,
                "section_type": section_type,
                "content": content,
                "timestamp": metadata.get("timestamp", ""),
            }
            self.chunks.append(chunk_data)

        # 返回标准化的块数据
        return {
            "type": "chunk",
            "document_id": self.document_id,
            "content": content,
            "progress": self.current_progress,
            "is_partial": is_partial,
            "metadata": {
                "section_id": section_id,
                "section_title": section_title,
                "section_type": section_type,
                "completed_sections": self.completed_sections,
                "total_sections": self.total_sections,
            },
        }

    async def get_document_content(self) -> str:
        """
        获取完整的文档内容

        Returns:
            拼接后的完整文档内容
        """
        # 这里可以根据实际需求定制文档内容的拼接逻辑
        # 例如按节点ID排序、处理特殊格式等

        # 简单实现：按接收顺序拼接内容
        return "\n\n".join([chunk.get("content", "") for chunk in self.chunks])

    async def process_llm_stream(
        self, generator: AsyncGenerator
    ) -> AsyncGenerator[str, None]:
        """
        处理LLM生成的流式数据

        Args:
            generator: LLM数据源生成器

        Yields:
            SSE格式的消息
        """
        async for data in self.process_stream(generator, self.transform_llm_chunk):
            yield data

        # 流结束后，发送完整文档
        try:
            full_content = await self.get_document_content()
            complete_data = {
                "type": "complete",
                "document_id": self.document_id,
                "content": full_content,
                "chunks": self.chunks,
                "progress": 100,
                "metadata": {
                    "template_id": self.template_id,
                    "completed_sections": self.completed_sections,
                    "total_sections": self.total_sections,
                },
            }
            yield self.format_sse(complete_data, event_type="complete")
        except Exception as e:
            logger.error(f"生成完整文档时发生错误: {str(e)}")
            error_data = {"type": "error", "error": f"生成完整文档失败: {str(e)}"}
            yield self.format_sse(error_data, event_type="error")


async def create_stream_response(
    generator: AsyncGenerator,
) -> AsyncGenerator[str, None]:
    """
    创建简单的流式响应

    Args:
        generator: 数据源生成器

    Returns:
        SSE格式的流式响应
    """
    processor = StreamProcessor()
    async for data in processor.process_stream(generator):
        yield data


async def create_document_stream(
    generator: AsyncGenerator, document_id: str, template_id: Optional[str] = None
) -> AsyncGenerator[str, None]:
    """
    创建文档生成的流式响应

    Args:
        generator: 数据源生成器
        document_id: 文档ID
        template_id: 模板ID

    Returns:
        SSE格式的文档流式响应
    """
    processor = DocumentStreamProcessor(
        document_id=document_id, template_id=template_id
    )
    async for data in processor.process_llm_stream(generator):
        yield data

"""
流式响应API路由模块
提供演示和实用的流式接口
"""

import asyncio
import json
import uuid
from datetime import datetime
from typing import Any, AsyncGenerator, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

# 导入流式处理工具
from modules.doc_server.utils.stream_utils import (
    create_document_stream,
    create_stream_response,
)

# 设置路由
router = APIRouter(prefix="/stream", tags=["stream"])


async def mock_generator(
    delay: float = 0.5, count: int = 10
) -> AsyncGenerator[Dict[str, Any], None]:
    """
    模拟数据生成器，产生一系列消息

    Args:
        delay: 每条消息的延迟（秒）
        count: 消息总数

    Yields:
        模拟的消息数据
    """
    for i in range(count):
        await asyncio.sleep(delay)
        yield {
            "type": "message",
            "content": f"这是第{i+1}条消息",
            "timestamp": datetime.now().isoformat(),
        }


async def mock_document_generator(
    delay: float = 0.8, section_count: int = 5
) -> AsyncGenerator[Dict[str, Any], None]:
    """
    模拟文档生成器，产生文档内容块

    Args:
        delay: 每个节点的延迟（秒）
        section_count: 节点总数

    Yields:
        模拟的文档节点数据
    """
    section_titles = [
        "1. 项目概述",
        "2. 需求分析",
        "3. 系统设计",
        "4. 实现方案",
        "5. 测试计划",
    ]

    for i in range(section_count):
        await asyncio.sleep(delay)
        content = f"## {section_titles[i]}\n\n这是{section_titles[i]}的内容。这部分内容将详细描述相关信息。"

        yield {
            "content": content,
            "metadata": {
                "section_id": f"section_{i+1}",
                "section_title": section_titles[i],
                "section_type": "markdown",
                "section_index": i + 1,
                "total_sections": section_count,
                "timestamp": datetime.now().isoformat(),
            },
        }


@router.get("/test")
async def test_stream(
    delay: float = Query(0.5, description="每条消息的延迟（秒）"),
    count: int = Query(10, description="消息总数"),
):
    """
    测试简单的流式响应
    """
    generator = mock_generator(delay=delay, count=count)
    return StreamingResponse(
        create_stream_response(generator), media_type="text/event-stream"
    )


@router.get("/document")
async def test_document_stream(
    document_id: Optional[str] = Query(None, description="文档ID，不提供则自动生成"),
    template_id: Optional[str] = Query(None, description="模板ID"),
    delay: float = Query(0.8, description="每个节点的延迟（秒）"),
    section_count: int = Query(5, description="节点总数"),
):
    """
    测试文档流式生成响应
    """
    # 如果没有提供文档ID，生成一个
    if not document_id:
        document_id = str(uuid.uuid4())

    generator = mock_document_generator(delay=delay, section_count=section_count)
    return StreamingResponse(
        create_document_stream(generator, document_id, template_id),
        media_type="text/event-stream",
    )

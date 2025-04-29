import asyncio
import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException
from fastapi.responses import StreamingResponse

# 复用OpenManus的配置、日志和LLM系统
from app.config import Config
from app.llm import LLM
from app.logger import setup_logger
from modules.doc_server.agents.document_writer.agent import DocumentWriterAgent

# 引入API模型
from modules.doc_server.api.models.document import (
    DocumentRequest,
    DocumentResponse,
    DocumentType,
    IntentType,
)

# 导入文档服务组件
from modules.doc_server.services.document.processor import DocumentProcessor
from modules.doc_server.services.rag.client import RAGClient
from modules.doc_server.utils.stream_utils import create_document_stream

# 设置路由
router = APIRouter(prefix="/documents", tags=["documents"])
logger = setup_logger("doc_server.documents")
config = Config()

# 初始化服务
document_processor = DocumentProcessor(config.get("doc_server.document", {}))
rag_client = RAGClient(config.get("doc_server.rag", {}))


@router.post("/", response_model=DocumentResponse)
async def create_document(request: DocumentRequest):
    """
    创建新文档
    """
    try:
        # 生成唯一ID
        document_id = str(uuid.uuid4())
        timestamp = datetime.now().isoformat()

        # 日志记录
        logger.info(f"开始创建文档: {document_id}, 类型: {request.document_type}")

        # 获取模板
        template_id = request.template_id
        if not template_id:
            # 如果未指定模板，根据文档类型选择默认模板
            if request.document_type:
                template_id = f"{request.document_type.value}_default"
            else:
                # 需要根据用户查询识别意图和文档类型
                # 这里暂时使用默认模板
                template_id = "general_default"

        # 加载模板
        try:
            template = await document_processor.load_template(template_id)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail=f"模板不存在: {template_id}")

        # 简单处理：生成文档标题和内容
        # 实际实现中需要调用Agent和工具进行复杂处理
        title = f"文档 - {timestamp}"
        content = f"这是根据模板 {template_id} 生成的文档内容。"

        # 返回结果
        return DocumentResponse(
            document_id=document_id,
            title=title,
            content=content,
            template_used=template_id,
            created_at=timestamp,
            chunks=[],  # 暂时为空
        )

    except Exception as e:
        logger.error(f"创建文档失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"创建文档失败: {str(e)}")


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(document_id: str):
    """
    获取文档详情
    """
    # 实际实现需要从数据库获取文档
    # 这里暂时返回模拟数据
    try:
        # 模拟从存储中获取文档
        if not document_id:
            raise HTTPException(status_code=404, detail="文档不存在")

        return DocumentResponse(
            document_id=document_id,
            title=f"文档 - {document_id}",
            content="这是文档内容",
            template_used="default",
            created_at=datetime.now().isoformat(),
            chunks=[],
        )
    except Exception as e:
        logger.error(f"获取文档失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取文档失败: {str(e)}")


@router.post("/generate/stream")
async def stream_generate_document(
    document_type: Optional[str] = None,
    template_id: Optional[str] = None,
    user_query: str = Body(..., embed=True, description="用户请求描述"),
    reference_documents: Optional[List[str]] = Body(
        None, embed=True, description="参考文档ID列表"
    ),
):
    """
    流式处理文档相关请求，包括生成、审查、编辑和解读

    首先检测用户意图，然后根据不同意图类型分发到相应的处理流程
    """
    try:
        # 生成文档ID
        document_id = str(uuid.uuid4())
        logger.info(
            f"收到用户请求: {document_id}, 查询: {user_query}, 类型: {document_type}, 模板: {template_id}"
        )

        # 首先进行意图检测
        from modules.doc_server.tools.intent_detector.tool import IntentDetectorTool

        intent_detector = IntentDetectorTool()
        intent_result = await intent_detector.execute(user_query)

        logger.info(
            f"意图检测结果: {intent_result.intent}, 置信度: {intent_result.confidence}"
        )

        # 根据意图类型分发处理
        if intent_result.intent == IntentType.CREATE.value:
            # 文档生成流程
            return await handle_document_generation(
                document_id, document_type, template_id, user_query, reference_documents
            )
        elif intent_result.intent == IntentType.REVIEW.value:
            # 文档审查流程
            return await handle_document_review(
                document_id, document_type, template_id, user_query, reference_documents
            )
        elif intent_result.intent == IntentType.EDIT.value:
            # 文档编辑流程
            return await handle_document_edit(
                document_id, document_type, template_id, user_query, reference_documents
            )
        elif intent_result.intent == IntentType.ANALYZE.value:
            # 文档解读流程
            return await handle_document_interpretation(
                document_id, document_type, template_id, user_query, reference_documents
            )
        else:
            # 未识别意图，返回提示并默认使用文档生成流程
            logger.warning(
                f"未能明确识别用户意图: {intent_result.intent}，默认使用文档生成流程"
            )
            return await handle_unclear_intent(
                document_id,
                document_type,
                template_id,
                user_query,
                reference_documents,
                intent_result,
            )

    except Exception as e:
        logger.error(f"处理用户请求失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"处理用户请求失败: {str(e)}")


async def handle_document_generation(
    document_id: str,
    document_type: Optional[str],
    template_id: Optional[str],
    user_query: str,
    reference_documents: Optional[List[str]],
):
    """处理文档生成意图"""
    # 初始化文档编写Agent
    doc_agent = DocumentWriterAgent(
        document_id=document_id,
        template_id=template_id,
        document_type=document_type,
        user_query=user_query,
        reference_documents=reference_documents or [],
    )

    # 创建异步生成器
    async def generate():
        try:
            async for result in doc_agent.run_stream():
                yield result
        except Exception as e:
            logger.error(f"流式生成文档失败: {str(e)}")
            yield {
                "content": f"生成文档时出错: {str(e)}",
                "metadata": {"error": str(e), "section_type": "error"},
            }

    # 返回流式响应
    return StreamingResponse(
        create_document_stream(generate(), document_id, template_id),
        media_type="text/event-stream",
    )


async def handle_document_review(
    document_id: str,
    document_type: Optional[str],
    template_id: Optional[str],
    user_query: str,
    reference_documents: Optional[List[str]],
):
    """处理文档审查意图"""
    from app.llm import LLM

    llm = LLM()

    async def generate():
        try:
            # 1. 首先发送开始审查的消息
            yield {
                "content": "开始进行文档审查...",
                "metadata": {
                    "section_id": "review_start",
                    "section_title": "文档审查开始",
                    "section_type": "info",
                    "section_index": 1,
                    "total_sections": 4,
                },
            }

            # 2. 分析需要审查的文档类型和要求
            system_prompt = f"""你是一位资深的文档审查专家，擅长审查各类专业文档并提供改进建议。
            请根据用户描述的需求，分析需要审查的文档类型和主要关注点。

            用户查询: {user_query}
            """

            messages = [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": f"请分析我需要审查的文档类型和主要关注点: {user_query}",
                },
            ]

            analysis_content = await llm.ask(messages, stream=False)

            yield {
                "content": analysis_content,
                "metadata": {
                    "section_id": "review_analysis",
                    "section_title": "审查需求分析",
                    "section_type": "analysis",
                    "section_index": 2,
                    "total_sections": 4,
                },
            }

            # 3. 生成审查要点清单
            checklist_prompt = f"""基于对用户需求的分析，请生成一份文档审查要点清单，包括:
            1. 文档结构与组织方面的检查点
            2. 内容完整性与准确性方面的检查点
            3. 语言表达与风格方面的检查点
            4. 专业性与技术准确性方面的检查点
            5. 格式与排版方面的检查点

            用户查询: {user_query}
            参考文档数量: {len(reference_documents) if reference_documents else 0}
            """

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": checklist_prompt},
            ]

            checklist_content = await llm.ask(messages, stream=False)

            yield {
                "content": checklist_content,
                "metadata": {
                    "section_id": "review_checklist",
                    "section_title": "审查要点清单",
                    "section_type": "checklist",
                    "section_index": 3,
                    "total_sections": 4,
                },
            }

            # 4. 生成审查流程指导
            guidance_prompt = f"""基于之前生成的审查要点清单，请提供一份详细的审查流程指导，帮助用户按照系统的步骤进行文档审查。
            包括:
            1. 如何使用审查要点清单
            2. 审查的优先级和顺序建议
            3. 常见问题的处理方法
            4. 审查完成后的质量评估方法

            用户查询: {user_query}
            """

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": guidance_prompt},
            ]

            guidance_content = await llm.ask(messages, stream=False)

            yield {
                "content": guidance_content,
                "metadata": {
                    "section_id": "review_guidance",
                    "section_title": "审查流程指导",
                    "section_type": "guidance",
                    "section_index": 4,
                    "total_sections": 4,
                },
            }

        except Exception as e:
            logger.error(f"文档审查处理失败: {str(e)}")
            yield {
                "content": f"文档审查过程中出错: {str(e)}",
                "metadata": {"error": str(e), "section_type": "error"},
            }

    return StreamingResponse(
        create_document_stream(generate(), document_id, template_id),
        media_type="text/event-stream",
    )


async def handle_document_edit(
    document_id: str,
    document_type: Optional[str],
    template_id: Optional[str],
    user_query: str,
    reference_documents: Optional[List[str]],
):
    """处理文档编辑意图"""
    from app.llm import LLM

    llm = LLM()

    async def generate():
        try:
            # 1. 发送开始编辑的消息
            yield {
                "content": "开始文档编辑分析...",
                "metadata": {
                    "section_id": "edit_start",
                    "section_title": "文档编辑开始",
                    "section_type": "info",
                    "section_index": 1,
                    "total_sections": 4,
                },
            }

            # 2. 分析编辑需求
            system_prompt = f"""你是一位专业的文档编辑顾问，擅长帮助用户编辑和改进各类文档。
            请分析用户的编辑需求，理解他们希望如何修改或改进文档。

            用户查询: {user_query}
            """

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"请分析我的文档编辑需求: {user_query}"},
            ]

            analysis_content = await llm.ask(messages, stream=False)

            yield {
                "content": analysis_content,
                "metadata": {
                    "section_id": "edit_analysis",
                    "section_title": "编辑需求分析",
                    "section_type": "analysis",
                    "section_index": 2,
                    "total_sections": 4,
                },
            }

            # 3. 生成编辑建议
            suggestions_prompt = f"""基于对用户编辑需求的分析，请提供具体的编辑建议，包括:
            1. 内容组织与结构调整建议
            2. 语言表达与风格优化建议
            3. 内容充实与删减建议
            4. 专业性与准确性提升建议
            5. 可读性与受众适应性建议

            用户查询: {user_query}
            """

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": suggestions_prompt},
            ]

            suggestions_content = await llm.ask(messages, stream=False)

            yield {
                "content": suggestions_content,
                "metadata": {
                    "section_id": "edit_suggestions",
                    "section_title": "编辑建议",
                    "section_type": "suggestions",
                    "section_index": 3,
                    "total_sections": 4,
                },
            }

            # 4. 提供编辑实施计划
            plan_prompt = f"""基于之前的编辑建议，请提供一份实用的编辑实施计划，帮助用户系统地完成文档编辑工作。包括:
            1. 编辑工作的优先级排序
            2. 分步骤的编辑流程
            3. 编辑过程中的注意事项
            4. 编辑完成后的自查清单

            用户查询: {user_query}
            """

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": plan_prompt},
            ]

            plan_content = await llm.ask(messages, stream=False)

            yield {
                "content": plan_content,
                "metadata": {
                    "section_id": "edit_plan",
                    "section_title": "编辑实施计划",
                    "section_type": "plan",
                    "section_index": 4,
                    "total_sections": 4,
                },
            }

        except Exception as e:
            logger.error(f"文档编辑处理失败: {str(e)}")
            yield {
                "content": f"文档编辑过程中出错: {str(e)}",
                "metadata": {"error": str(e), "section_type": "error"},
            }

    return StreamingResponse(
        create_document_stream(generate(), document_id, template_id),
        media_type="text/event-stream",
    )


async def handle_document_interpretation(
    document_id: str,
    document_type: Optional[str],
    template_id: Optional[str],
    user_query: str,
    reference_documents: Optional[List[str]],
):
    """处理文档解读意图"""
    from app.llm import LLM

    llm = LLM()

    async def generate():
        try:
            # 1. 发送开始解读的消息
            yield {
                "content": "开始进行文档解读...",
                "metadata": {
                    "section_id": "interpret_start",
                    "section_title": "文档解读开始",
                    "section_type": "info",
                    "section_index": 1,
                    "total_sections": 5,
                },
            }

            # 2. 分析解读需求
            system_prompt = f"""你是一位专业的文档解读专家，擅长帮助用户理解复杂的专业文档内容。
            请分析用户的解读需求，理解他们希望从文档中了解什么关键信息。

            用户查询: {user_query}
            参考文档数量: {len(reference_documents) if reference_documents else 0}
            """

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"请分析我的文档解读需求: {user_query}"},
            ]

            analysis_content = await llm.ask(messages, stream=False)

            yield {
                "content": analysis_content,
                "metadata": {
                    "section_id": "interpret_analysis",
                    "section_title": "解读需求分析",
                    "section_type": "analysis",
                    "section_index": 2,
                    "total_sections": 5,
                },
            }

            # 3. 文档结构概览
            structure_prompt = f"""基于用户的解读需求，请提供一份文档结构概览，帮助用户了解文档的整体框架和组织方式。包括:
            1. 文档的主要章节和层次结构
            2. 各部分的内容概述
            3. 关键信息的分布位置
            4. 阅读导航建议

            用户查询: {user_query}
            """

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": structure_prompt},
            ]

            structure_content = await llm.ask(messages, stream=False)

            yield {
                "content": structure_content,
                "metadata": {
                    "section_id": "interpret_structure",
                    "section_title": "文档结构概览",
                    "section_type": "structure",
                    "section_index": 3,
                    "total_sections": 5,
                },
            }

            # 4. 核心内容解读
            content_prompt = f"""基于用户的解读需求，请提供文档核心内容的深度解读，包括:
            1. 关键概念和术语的解释
            2. 主要论点和发现的分析
            3. 数据和事实的解读
            4. 隐含信息的揭示
            5. 专业背景知识的补充

            用户查询: {user_query}
            """

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": content_prompt},
            ]

            content_interpretation = await llm.ask(messages, stream=False)

            yield {
                "content": content_interpretation,
                "metadata": {
                    "section_id": "interpret_content",
                    "section_title": "核心内容解读",
                    "section_type": "interpretation",
                    "section_index": 4,
                    "total_sections": 5,
                },
            }

            # 5. 提供阅读指南和建议
            guidance_prompt = f"""基于之前的解读，请提供一份实用的阅读指南和建议，帮助用户更有效地理解和应用文档内容。包括:
            1. 重点关注建议
            2. 阅读顺序建议
            3. 理解难点解析
            4. 实际应用建议
            5. 延伸阅读推荐

            用户查询: {user_query}
            """

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": guidance_prompt},
            ]

            guidance_content = await llm.ask(messages, stream=False)

            yield {
                "content": guidance_content,
                "metadata": {
                    "section_id": "interpret_guidance",
                    "section_title": "阅读指南和建议",
                    "section_type": "guidance",
                    "section_index": 5,
                    "total_sections": 5,
                },
            }

        except Exception as e:
            logger.error(f"文档解读处理失败: {str(e)}")
            yield {
                "content": f"文档解读过程中出错: {str(e)}",
                "metadata": {"error": str(e), "section_type": "error"},
            }

    return StreamingResponse(
        create_document_stream(generate(), document_id, template_id),
        media_type="text/event-stream",
    )


async def handle_unclear_intent(
    document_id: str,
    document_type: Optional[str],
    template_id: Optional[str],
    user_query: str,
    reference_documents: Optional[List[str]],
    intent_result: Any,
):
    """处理意图不明确的情况"""
    from app.llm import LLM

    llm = LLM()

    async def generate():
        try:
            # 发送意图不明确的提示
            yield {
                "content": f"我无法明确确定您的意图。检测到的意图类型是 '{intent_result.intent}'，置信度为 {intent_result.confidence}。",
                "metadata": {
                    "section_id": "unclear_intent",
                    "section_title": "意图不明确",
                    "section_type": "warning",
                    "section_index": 1,
                    "total_sections": 3,
                },
            }

            # 分析用户可能的意图
            system_prompt = """你是一位专业的文档助手，你的任务是分析用户的查询，并推测他们最可能的意图。
            请考虑以下几种可能的意图类型:
            - 创建/生成新文档
            - 审查/评价现有文档
            - 编辑/修改文档内容
            - 解读/理解文档内容
            """

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"请分析我可能的意图: {user_query}"},
            ]

            intent_analysis = await llm.ask(messages, stream=False)

            yield {
                "content": intent_analysis,
                "metadata": {
                    "section_id": "intent_analysis",
                    "section_title": "意图分析",
                    "section_type": "analysis",
                    "section_index": 2,
                    "total_sections": 3,
                },
            }

            # 提供功能选项建议
            options_content = """基于您的需求，我可以提供以下几种服务：

1. **创建文档**：根据您的要求和参考资料，生成一份完整的结构化文档。
2. **审查文档**：分析现有文档的质量，提供改进建议和审查清单。
3. **编辑文档**：提供具体的编辑建议和实施计划，帮助改进文档质量。
4. **解读文档**：帮助您更好地理解文档内容，提供专业解读和阅读指南。

请在下次查询中明确您需要的服务类型，例如"我需要创建一份项目需求文档"或"请帮我审查这份技术报告"。"""

            yield {
                "content": options_content,
                "metadata": {
                    "section_id": "options",
                    "section_title": "可用服务选项",
                    "section_type": "options",
                    "section_index": 3,
                    "total_sections": 3,
                },
            }

        except Exception as e:
            logger.error(f"处理不明确意图失败: {str(e)}")
            yield {
                "content": f"处理您的请求时出错: {str(e)}",
                "metadata": {"error": str(e), "section_type": "error"},
            }

    return StreamingResponse(
        create_document_stream(generate(), document_id, template_id),
        media_type="text/event-stream",
    )


@router.post("/stream")
async def stream_document(request: DocumentRequest):
    """
    流式生成文档（旧版接口，保留兼容性）
    """

    async def generate():
        """生成器函数，用于流式返回文档内容"""
        try:
            # 实际实现中应该调用Agent和工具进行复杂处理
            # 并通过SSE流式返回生成过程
            # 这里使用简单示例
            for i in range(5):
                await asyncio.sleep(1)  # 模拟处理时间
                data = {
                    "type": "chunk",
                    "content": f"生成的文档内容部分 {i+1}",
                    "progress": (i + 1) * 20,
                }
                yield f"data: {json.dumps(data)}\n\n"

            # 最后返回完整内容
            data = {
                "type": "complete",
                "document_id": str(uuid.uuid4()),
                "title": "流式生成的文档",
                "content": "完整的文档内容",
                "progress": 100,
            }
            yield f"data: {json.dumps(data)}\n\n"

        except Exception as e:
            logger.error(f"流式生成文档失败: {str(e)}")
            error_data = {"type": "error", "error": str(e)}
            yield f"data: {json.dumps(error_data)}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.post("/review/{document_id}")
async def review_document(document_id: str, background_tasks: BackgroundTasks):
    """
    审阅生成的文档内容，检查连贯性和完整性
    """
    try:
        logger.info(f"开始审阅文档: {document_id}")

        # 初始化文档编写Agent
        doc_agent = DocumentWriterAgent(
            document_id=document_id,
            template_id=None,  # 审阅不需要模板
            document_type=None,
            user_query="请审阅此文档",
            reference_documents=[],
        )

        # 执行文档审阅
        review_result = await doc_agent.review_document()

        if not review_result.get("success", False):
            raise HTTPException(
                status_code=500,
                detail=f"审阅文档失败: {review_result.get('error', '未知错误')}",
            )

        return {
            "document_id": document_id,
            "review": review_result.get("review", ""),
            "success": True,
        }

    except Exception as e:
        logger.error(f"审阅文档失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"审阅文档失败: {str(e)}")

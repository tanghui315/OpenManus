"""
文档编写Agent
基于OpenManus的ReActAgent，专门用于生成文档内容
"""

import asyncio
import json
from datetime import datetime
from typing import Any, AsyncGenerator, Dict, List, Optional

from pydantic import ConfigDict, Field

# 复用OpenManus的基础设施
from app.agent.react import ReActAgent
from app.config import Config
from app.llm import LLM
from app.logger import setup_logger
from app.schema import AgentState, Memory

# 导入文档服务相关组件
from modules.doc_server.services.rag.client import RAGClient
from modules.doc_server.services.template.manager import TemplateManager
from modules.doc_server.tools.chunk_manager.model import ChunkOperation
from modules.doc_server.tools.chunk_manager.tool import ChunkManagerTool

logger = setup_logger("doc_server.agents.document_writer")


class DocumentWriterAgent(ReActAgent):
    """
    文档编写Agent，负责生成文档内容

    基于ReAct架构，通过思考和行动来生成文档
    支持流式生成，适用于各种文档类型和模板
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    # 基本信息
    name: str = "DocumentWriterAgent"
    description: str = "专注于生成高质量结构化文档的智能体"

    # 文档相关字段
    document_id: str = Field(..., description="文档ID")
    template_id: Optional[str] = Field(None, description="模板ID")
    document_type: Optional[str] = Field(None, description="文档类型")
    user_query: str = Field(..., description="用户请求描述")
    reference_documents: List[str] = Field(
        default_factory=list, description="参考文档ID列表"
    )

    # 服务和工具
    rag_client: Optional[RAGClient] = Field(None, description="RAG检索客户端")
    template_manager: Optional[TemplateManager] = Field(None, description="模板管理器")
    chunk_manager: Optional[ChunkManagerTool] = Field(
        None, description="文档块管理工具"
    )

    # 生成控制
    current_section_index: int = Field(0, description="当前处理的节点索引")
    total_sections: int = Field(0, description="文档总节点数")
    generated_sections: Dict[str, Any] = Field(
        default_factory=dict, description="已生成的节点"
    )

    # 提示词相关
    system_prompt_template: str = Field(
        """你是一名专业的文档编写专家，擅长根据用户需求和参考资料生成高质量的结构化文档。
        你需要遵循指定的模板格式，确保文档内容完整、准确、专业，同时满足用户的具体要求。

        当前任务：根据用户查询和提供的参考资料，生成一份{document_type}类型的文档。

        文档ID: {document_id}
        模板ID: {template_id}

        你将按照模板定义的结构，逐节生成内容。对于每个节点：
        1. 分析节点要求和RAG关键词
        2. 检索相关参考资料
        3. 组织并生成该节点的内容
        4. 确保内容的准确性和相关性

        在生成长文档时，你可以回顾和管理之前生成的内容块。如果需要参考前面的内容，可以使用文档块管理工具查看已生成的内容。

        文档块管理工具提供的能力：
        - 查看已生成的所有内容块
        - 在需要时合并或拆分内容块
        - 调整内容块的顺序
        - 确保文档内容的连贯性和一致性

        请保持专业、客观的语言风格，注重逻辑性和可读性。
        """,
        description="系统提示词模板",
    )

    section_prompt_template: str = Field(
        """现在，请为文档的以下节点生成内容：

        节点ID: {section_id}
        节点标题: {section_title}
        节点类型: {section_type}
        节点描述: {section_description}

        RAG关键词: {rag_keywords}

        参考资料：
        {reference_content}

        用户需求：
        {user_query}

        {context_prompt}

        请生成此节点的内容，确保:
        1. 内容与节点标题和描述相符
        2. 充分利用提供的参考资料
        3. 符合{document_type}类型文档的专业标准
        4. 满足用户需求
        5. 与已生成的内容保持连贯性

        只需要生成该节点的内容，无需重复节点标题。
        """,
        description="节点内容生成提示词模板",
    )

    context_prompt_template: str = Field(
        """已生成内容的上下文（如有）：
        {context_content}

        请确保新生成的内容与上下文保持连贯性，避免重复或冲突。
        """,
        description="上下文提示词模板",
    )

    def __init__(self, **data: Any):
        """初始化文档编写Agent"""
        super().__init__(**data)

        # 设置配置
        config = Config()

        # 初始化服务
        if not self.rag_client:
            self.rag_client = RAGClient(config.get("doc_server.rag", {}))

        if not self.template_manager:
            self.template_manager = TemplateManager()

        # 初始化文档块管理工具
        if not self.chunk_manager:
            self.chunk_manager = ChunkManagerTool()
            self.chunk_manager.initialize()

        # 初始化系统提示词
        if not self.system_prompt:
            self.system_prompt = self.system_prompt_template.format(
                document_id=self.document_id,
                template_id=self.template_id or "未指定",
                document_type=self.document_type or "通用",
            )

        # 初始化agent内存
        self.memory = Memory()
        self.update_memory("system", self.system_prompt)
        self.update_memory("user", self.user_query)

    async def load_template(self) -> Dict[str, Any]:
        """
        加载文档模板

        Returns:
            模板数据结构
        """
        if not self.template_id:
            # 如果没有指定模板ID，尝试根据文档类型选择默认模板
            if self.document_type:
                self.template_id = f"{self.document_type}_default"
            else:
                self.template_id = "general_default"

        try:
            template = await self.template_manager.get_template(self.template_id)
            if not template:
                logger.warning(f"未找到模板: {self.template_id}，使用默认空模板")
                template = {}

            return template
        except Exception as e:
            logger.error(f"加载模板失败: {str(e)}")
            return {}

    async def retrieve_references(self, keywords: List[str]) -> str:
        """
        基于关键词检索参考资料

        Args:
            keywords: 检索关键词列表

        Returns:
            检索到的参考内容文本
        """
        if not keywords or not self.reference_documents:
            return "未找到相关参考资料。"

        try:
            # 构建检索查询
            query = " ".join(keywords)

            # 调用RAG客户端检索内容
            results = await self.rag_client.retrieve(
                query=query, document_ids=self.reference_documents, top_k=3
            )

            # 提取检索结果
            if not results.get("success", False):
                return f"检索过程出现错误: {results.get('error', '未知错误')}"

            items = results.get("results", [])
            if not items:
                return "未找到相关参考资料。"

            # 格式化参考内容
            reference_texts = []
            for i, item in enumerate(items):
                source = item.get("metadata", {}).get("source", "未知来源")
                content = item.get("content", "").strip()
                if content:
                    reference_texts.append(f"参考{i+1} ({source}):\n{content}")

            return "\n\n".join(reference_texts)
        except Exception as e:
            logger.error(f"检索参考资料失败: {str(e)}")
            return f"检索过程出现错误: {str(e)}"

    async def get_context_content(self, current_index: int) -> str:
        """
        获取上下文内容，用于提供给模型参考

        Args:
            current_index: 当前节点索引

        Returns:
            上下文内容文本
        """
        try:
            # 如果是第一个节点，没有上下文
            if current_index == 0:
                return ""

            # 获取文档的所有块
            result = await self.chunk_manager.execute(
                operation=ChunkOperation.REORDER,  # 这里使用REORDER操作只是为了获取所有块
                document_id=self.document_id,
                target_ids=[],  # 空列表表示不做实际重排序
            )

            if not result.success or not result.chunks:
                logger.warning(f"获取文档块失败或没有块: {result.error}")
                return ""

            # 获取之前的块（至多2个）
            context_chunks = []
            chunks_count = len(result.chunks)

            # 寻找之前生成的最多2个块
            context_indices = []
            if current_index - 1 >= 0 and current_index - 1 < chunks_count:
                context_indices.append(current_index - 1)
            if current_index - 2 >= 0 and current_index - 2 < chunks_count:
                context_indices.append(current_index - 2)

            for idx in context_indices:
                if idx < len(result.chunks):
                    chunk = result.chunks[idx]
                    context_chunks.append(
                        f"节点 {idx+1}: {chunk.section_title}\n{chunk.content}"
                    )

            if not context_chunks:
                return ""

            return "\n\n".join(context_chunks)

        except Exception as e:
            logger.error(f"获取上下文内容失败: {str(e)}")
            return ""

    async def process_section(
        self, section: Dict[str, Any]
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        处理单个文档节点

        Args:
            section: 节点数据

        Yields:
            生成的节点内容和元数据
        """
        try:
            # 获取节点信息
            section_id = section.get(
                "section_id", f"section_{self.current_section_index}"
            )
            section_title = section.get("title", f"节点 {self.current_section_index}")
            section_type = section.get("category", "text")
            section_description = section.get("desc", "")

            # 获取RAG关键词
            rag_keywords = section.get("rag_key_words", [])
            if not rag_keywords and section_title:
                # 如果没有提供关键词，使用标题作为关键词
                rag_keywords = [section_title]

            # 检索参考资料
            reference_content = await self.retrieve_references(rag_keywords)

            # 创建基础元数据
            metadata = {
                "section_id": section_id,
                "section_title": section_title,
                "section_type": section_type,
                "section_index": self.current_section_index + 1,
                "total_sections": self.total_sections,
                "timestamp": datetime.now().isoformat(),
            }

            # 先构建初步提示词询问是否需要上下文
            context_decision_prompt = f"""你将为文档的以下节点生成内容：

            节点ID: {section_id}
            节点标题: {section_title}
            节点类型: {section_type}
            节点描述: {section_description}

            RAG关键词: {', '.join(rag_keywords)}

            你需要先判断：是否需要查看先前生成的内容作为上下文参考？
            - 如果当前节点是独立的章节，或与前文关联不大，回答"不需要"
            - 如果当前节点需要与前文保持连贯性或有内在联系，回答"需要"

            只需简单回答"需要"或"不需要"，不要解释理由。
            """

            # 更新Agent内存并询问是否需要上下文
            temp_memory = Memory()
            temp_memory.update("system", context_decision_prompt)

            need_context_response = await self.llm.ask(
                temp_memory.get_messages(), stream=False
            )
            need_context = "需要" in need_context_response.lower()

            # 根据模型判断决定是否获取上下文
            context_prompt = ""
            if need_context and self.current_section_index > 0:
                logger.info(f"模型决定需要获取上下文用于节点: {section_title}")
                context_content = await self.get_context_content(
                    self.current_section_index
                )
                if context_content:
                    context_prompt = self.context_prompt_template.format(
                        context_content=context_content
                    )
            else:
                logger.info(f"模型决定不需要获取上下文用于节点: {section_title}")

            # 构建完整节点提示词
            section_prompt = self.section_prompt_template.format(
                section_id=section_id,
                section_title=section_title,
                section_type=section_type,
                section_description=section_description,
                rag_keywords=", ".join(rag_keywords),
                reference_content=reference_content,
                user_query=self.user_query,
                document_type=self.document_type or "通用",
                context_prompt=context_prompt,
            )

            # 更新Agent内存
            self.update_memory("system", section_prompt)

            # 修改为使用流式调用LLM
            content_parts = []
            async for chunk in self.llm.ask(self.memory.get_messages(), stream=True):
                content_parts.append(chunk)
                # 流式返回部分内容
                yield {"content": chunk, "metadata": metadata, "is_partial": True}

            # 组合完整内容
            content = "".join(content_parts)

            # 记录助手回复
            self.update_memory("assistant", content)

            # 构建完整结果
            final_result = {
                "content": content,
                "metadata": metadata,
                "is_partial": False,
            }

            # 更新已生成节点
            self.generated_sections[section_id] = {
                "content": content,
                "metadata": metadata,
            }

            # 使用ChunkManagerTool将内容保存为文档块
            await self.chunk_manager.execute(
                operation=ChunkOperation.ADD,
                document_id=self.document_id,
                section_title=section_title,
                section_type=section_type,
                content=content,
                position=self.current_section_index,
            )

            yield final_result
        except Exception as e:
            logger.error(f"处理节点失败: {str(e)}")
            yield {
                "content": f"生成内容时出错: {str(e)}",
                "metadata": {
                    "section_id": section.get(
                        "section_id", f"section_{self.current_section_index}"
                    ),
                    "section_title": section.get(
                        "title", f"节点 {self.current_section_index}"
                    ),
                    "section_type": "error",
                    "section_index": self.current_section_index + 1,
                    "total_sections": self.total_sections,
                    "timestamp": datetime.now().isoformat(),
                    "error": str(e),
                },
                "is_partial": False,
            }

    async def generate_document_content(self) -> AsyncGenerator[Dict[str, Any], None]:
        """
        生成完整文档内容的异步生成器

        Yields:
            文档节点内容和元数据
        """
        # 重置状态
        self.current_section_index = 0
        self.generated_sections = {}

        try:
            # 加载模板
            template = await self.load_template()

            # 解析模板获取节点列表
            sections = template.get("sections", [])
            self.total_sections = len(sections)

            if self.total_sections == 0:
                # 如果没有定义节点，创建一个默认节点
                sections = [
                    {
                        "section_id": "default",
                        "title": "文档内容",
                        "category": "text",
                        "desc": "根据用户需求生成完整文档内容",
                    }
                ]
                self.total_sections = 1

            # 逐节处理
            for i, section in enumerate(sections):
                self.current_section_index = i

                # 处理节点并流式输出
                async for result in self.process_section(section):
                    yield result

                # 每个节点生成后添加短暂延迟，避免请求过于密集
                await asyncio.sleep(0.1)

        except Exception as e:
            logger.error(f"生成文档内容失败: {str(e)}")
            yield {
                "content": f"生成文档内容失败: {str(e)}",
                "metadata": {
                    "section_id": "error",
                    "section_title": "错误",
                    "section_type": "error",
                    "section_index": self.current_section_index + 1,
                    "total_sections": self.total_sections,
                    "timestamp": datetime.now().isoformat(),
                    "error": str(e),
                },
            }

    async def think(self) -> bool:
        """
        分析当前状态并决定下一步行动

        Returns:
            是否需要采取行动
        """
        # 在文档生成场景中，总是需要采取行动
        return True

    async def act(self) -> str:
        """
        执行决定的行动

        Returns:
            行动结果描述
        """
        # 对于文档编写Agent，主要行动是生成文档内容
        # 但这里仅返回一个描述，实际生成通过generate_document_content完成
        return f"生成文档内容: {self.document_id}, 模板: {self.template_id}, 完成度: {min(100, int((self.current_section_index / max(1, self.total_sections)) * 100))}%"

    async def run_stream(self) -> AsyncGenerator[Dict[str, Any], None]:
        """
        运行Agent并流式返回生成内容

        这是流式生成接口，替代标准的run方法

        Yields:
            文档节点内容和元数据
        """
        if self.state != AgentState.IDLE:
            error_message = f"无法从状态 {self.state} 启动Agent"
            logger.error(error_message)
            yield {
                "content": error_message,
                "metadata": {"error": error_message, "section_type": "error"},
            }
            return

        async with self.state_context(AgentState.RUNNING):
            async for result in self.generate_document_content():
                yield result

            # 完成所有节点生成后
            self.state = AgentState.FINISHED

    async def review_document(self) -> Dict[str, Any]:
        """
        审阅生成的文档内容，检查连贯性和完整性

        Returns:
            审阅结果
        """
        try:
            # 获取所有文档块
            result = await self.chunk_manager.execute(
                operation=ChunkOperation.REORDER,
                document_id=self.document_id,
                target_ids=[],
            )

            if not result.success:
                logger.error(f"获取文档块失败: {result.error}")
                return {
                    "success": False,
                    "error": f"审阅文档时发生错误: {result.error}",
                }

            if not result.chunks:
                logger.warning("没有找到文档块")
                return {"success": False, "error": "文档为空，无法审阅"}

            # 构建完整文档内容
            full_content = "\n\n".join(
                [
                    f"## {chunk.section_title}\n{chunk.content}"
                    for chunk in result.chunks
                ]
            )

            # 构建审阅提示词
            review_prompt = f"""请审阅以下文档内容，检查连贯性、逻辑性、一致性和完整性：

{full_content}

请提供审阅意见和改进建议。
"""

            messages = [
                {
                    "role": "system",
                    "content": "你是一名文档审阅专家，负责检查文档的质量和连贯性。",
                },
                {"role": "user", "content": review_prompt},
            ]

            # 调用LLM进行审阅
            review_result = await self.llm.ask(messages, stream=False)

            return {
                "success": True,
                "review": review_result,
                "document_id": self.document_id,
            }

        except Exception as e:
            logger.error(f"审阅文档时发生错误: {str(e)}")
            return {"success": False, "error": f"审阅文档时发生错误: {str(e)}"}

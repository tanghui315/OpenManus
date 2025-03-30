from typing import List, Dict, Any, Optional, Tuple

from pydantic import Field

from app.agent.planning import PlanningAgent
from app.schema import Message, ToolChoice
from app.tool import ToolCollection, Terminate, BrowserUseTool
from app.tool.str_replace_editor import StrReplaceEditor
from app.tool.planning import PlanningTool
from app.logger import logger


SYSTEM_PROMPT = """你是一个专业的技术内容创作者，专注于创建高质量的技术文章。

你的任务是基于提供的信息来撰写一篇结构清晰、内容连贯的技术文章。遵循以下原则：

1. 内容必须基于提供的信息，不要编造事实或过度延伸有限的信息
2. 每个章节应与前后章节保持逻辑连贯，避免重复内容
3. 确保技术准确性和专业性，同时保持可读性
4. 适当引用来源信息，给予出处说明

你的文章应该：
- 有清晰的逻辑结构和章节划分
- 各章节内容衔接自然，前后呼应
- 提供有价值的技术见解和分析
- 从整体到细节层层深入，引导读者理解

最终输出应该是一篇可以直接发布的完整技术文章，没有不必要的重复内容。
"""

NEXT_STEP_PROMPT = """基于我们收集的信息，请开始撰写技术文章。

首先分析这些信息，确定：
1. 文章的中心主题和目标受众
2. 合理的章节结构和逻辑框架
3. 每个章节应涵盖的关键信息点

然后根据规划撰写文章，确保各部分内容连贯一致，没有重复。如果收集的信息不足，请直接说明。
"""


class ArticleWriterAgent(PlanningAgent):
    """针对章节结构优化的技术文章撰写Agent"""

    name: str = "article_writer"
    description: str = "基于收集的信息撰写结构化技术文章"

    system_prompt: str = SYSTEM_PROMPT
    next_step_prompt: str = NEXT_STEP_PROMPT

    available_tools: ToolCollection = Field(
        default_factory=lambda: ToolCollection(
            BrowserUseTool(), StrReplaceEditor(), PlanningTool(), Terminate()
        )
    )

    # 使用AUTO，允许大模型自由回答或调用工具
    tool_choices: ToolChoice = ToolChoice.AUTO  # type: ignore
    special_tool_names: List[str] = Field(default_factory=lambda: [Terminate().name])

    max_steps: int = 8  # 动态调整
    collected_info: List[Dict[str, Any]] = Field(default_factory=list)

    # 新增：保存章节结构和内容摘要
    chapter_structure: List[str] = Field(default_factory=list)
    chapter_contents: Dict[int, str] = Field(default_factory=dict)
    content_summaries: Dict[int, str] = Field(default_factory=dict)
    article_title: str = ""
    article_intro: str = ""
    article_conclusion: str = ""
    writing_stage: str = "planning"  # planning, introduction, chapters, conclusion, review

    async def run(self, request: Optional[str] = None) -> str:
        """
        执行文章撰写的主流程

        Args:
            request: 可选的初始请求，例如要撰写的文章主题或包含的信息点

        Returns:
            执行结果的字符串描述，通常是撰写的文章内容
        """
        # 重置状态
        self.chapter_structure = []
        self.chapter_contents = {}
        self.content_summaries = {}
        self.article_title = ""
        self.article_intro = ""
        self.article_conclusion = ""
        self.writing_stage = "planning"

        # 初始化收集的信息
        if not self.collected_info and request:
            # 如果有初始请求，将其作为第一条信息
            self.collected_info.append({
                "source": "initial_request",
                "content": request
            })

        # 添加收集到的信息到记忆中
        self._add_collected_info_to_memory()

        # 检查是否有足够的信息来撰写文章
        if not self.collected_info:
            logger.warning("没有收集到任何信息，无法撰写文章")
            return "没有足够的信息来撰写技术文章。请提供一些相关资料或主题。"

        # 执行Agent主流程
        try:
            result = await super().run()
            # 组装完整文章
            if self.writing_stage == "review":
                complete_article = self._assemble_final_article()
                return complete_article
            return result
        except Exception as e:
            logger.error(f"文章撰写过程中出错: {str(e)}")
            # 如果发生错误，尝试直接回答，不使用计划
            try:
                logger.info("尝试不使用计划直接撰写文章")
                result = await self._generate_article_without_plan()
                return result
            except Exception as fallback_error:
                logger.error(f"备用方案也失败: {str(fallback_error)}")
                return f"撰写文章时出错: {str(e)}"

    def _assemble_final_article(self) -> str:
        """根据已生成的各部分内容，组装完整文章"""
        parts = []

        # 添加标题
        if self.article_title:
            parts.append(f"# {self.article_title}\n")

        # 添加引言
        if self.article_intro:
            parts.append(self.article_intro)

        # 添加主体章节
        sorted_chapters = sorted(self.chapter_contents.items())
        for _, content in sorted_chapters:
            parts.append(content)

        # 添加结论
        if self.article_conclusion:
            parts.append(self.article_conclusion)

        return "\n\n".join(parts)

    async def _analyze_and_plan_article(self) -> Tuple[str, List[str]]:
        """分析收集的信息，确定文章主题和章节结构"""
        planning_prompt = """
基于以上收集的信息，请执行以下任务：

1. 分析所有内容，确定一个明确的中心主题
2. 为文章设计一个引人注目的标题
3. 规划4-6个逻辑连贯的章节结构（提供章节标题和每章要点）
4. 确保章节结构能完整覆盖关键信息，同时避免内容重复

请用以下格式回复：
标题：[文章标题]

章节结构：
1. [第一章标题]
   - [要点1]
   - [要点2]
2. [第二章标题]
   ...
"""
        self.memory.add_message(Message.user_message(planning_prompt))
        plan_response = await self.llm_chain.ainvoke(self.memory.messages, model=self.model)

        # 解析响应提取标题和章节结构
        title, chapters = self._parse_planning_response(plan_response)
        logger.info(f"已确定文章标题: {title}")
        logger.info(f"已规划章节结构: {', '.join(chapters)}")

        return title, chapters

    def _parse_planning_response(self, response: str) -> Tuple[str, List[str]]:
        """从规划响应中提取标题和章节结构"""
        lines = response.strip().split('\n')
        title = ""
        chapters = []

        for line in lines:
            line = line.strip()
            # 提取标题
            if line.startswith("标题：") or line.startswith("标题:"):
                title = line.split("：", 1)[1].strip() if "：" in line else line.split(":", 1)[1].strip()

            # 提取章节标题（通常是数字开头后跟章节名）
            elif line and line[0].isdigit() and "." in line and not line.startswith("- "):
                # 移除序号和点，只保留章节标题
                chapter_title = line.split(".", 1)[1].strip()
                if chapter_title:
                    chapters.append(chapter_title)

        return title, chapters

    async def _generate_article_without_plan(self) -> str:
        """当计划创建失败时，尝试直接生成文章"""
        direct_request = """
由于计划创建过程中断，现在请直接基于所有提供的信息撰写一篇完整的技术文章。文章应：

1. 有明确的标题和引言
2. 包含3-5个主要章节，每个章节有清晰的小标题
3. 章节之间保持逻辑连贯，避免内容重复
4. 以简短有力的结论结尾

请确保内容准确、深入且有见地，同时保持整体连贯性。
"""
        self.memory.add_message(Message.user_message(direct_request))
        response = await self.llm_chain.ainvoke(self.memory.messages, model=self.model)
        return response

    def add_information(self, source: str, content: str, url: Optional[str] = None) -> None:
        """
        添加信息到收集的信息列表中

        Args:
            source: 信息来源的描述
            content: 信息内容
            url: 可选的来源URL
        """
        info = {
            "source": source,
            "content": content
        }

        if url:
            info["url"] = url

        self.collected_info.append(info)
        logger.debug(f"添加信息: 来源={source}, URL={url or '无'}, 内容长度={len(content)}")

    def _add_collected_info_to_memory(self) -> None:
        """将收集到的信息添加到Agent的记忆中"""
        if not self.collected_info:
            logger.warning("没有收集到任何信息，无法添加到记忆中")
            return

        # 格式化信息
        formatted_info = "## 收集到的信息\n\n"

        for i, info in enumerate(self.collected_info, 1):
            formatted_info += f"### 信息 {i}: {info['source']}\n"

            if "url" in info:
                formatted_info += f"来源: {info['url']}\n"

            formatted_info += f"\n{info['content']}\n\n"

        # 添加到记忆中
        self.memory.add_message(Message.user_message(formatted_info))
        logger.debug(f"已将 {len(self.collected_info)} 条信息添加到记忆中")

    async def create_initial_plan(self, request: str) -> None:
        """
        创建初始文章写作计划，使用动态章节规划

        Args:
            request: 初始请求，包含文章主题或要求
        """
        # 首先添加用户请求
        self.memory.add_message(Message.user_message(request))

        # 分析收集的信息并确定章节结构
        self.article_title, self.chapter_structure = await self._analyze_and_plan_article()

        # 根据章节结构创建动态计划步骤
        plan_steps = [
            "分析文章主题和确定标题",
            "撰写引言部分，介绍文章主题和目的",
        ]

        # 为每个章节创建步骤
        for i, chapter in enumerate(self.chapter_structure, 1):
            plan_steps.append(f"撰写第{i}章：{chapter}")

        # 添加结论和审查步骤
        plan_steps.append("撰写总结和结论部分")
        plan_steps.append("审查全文，确保连贯性并消除重复内容")

        # 动态调整最大步骤数
        self.max_steps = len(plan_steps)
        logger.info(f"根据章节规划，设置最大步骤为: {self.max_steps}")

        # 使用PlanningTool创建计划
        plan_id = f"article_plan_{self.name}"
        self.active_plan_id = plan_id

        try:
            # 检查PlanningTool是否可用
            planning_tool = None
            for tool in self.available_tools.tools:
                if tool.name == "planning":
                    planning_tool = tool
                    break

            if not planning_tool:
                logger.warning("PlanningTool不可用，将跳过计划创建步骤")
                self.active_plan_id = None
                return

            # 创建计划
            logger.info(f"开始创建文章写作计划: {plan_id}")
            result = await self.available_tools.execute(
                name="planning",
                tool_input={
                    "command": "create",
                    "plan_id": plan_id,
                    "title": f"《{self.article_title}》文章撰写计划",
                    "description": f"基于收集的信息撰写一篇关于《{self.article_title}》的技术文章",
                    "steps": plan_steps
                }
            )

            # 检查计划是否创建成功
            if not result or "error" in result.lower():
                logger.warning(f"计划创建可能失败: {result}")
                self.active_plan_id = None
            else:
                logger.info(f"文章写作计划创建成功: {plan_id}")

        except Exception as e:
            logger.error(f"创建计划时出错: {str(e)}")
            self.active_plan_id = None

    async def think(self) -> bool:
        """重写think方法，根据当前步骤更新提示和状态"""
        current_step_index = await self._get_current_step_index()
        if current_step_index is not None:
            # 根据当前步骤更新writing_stage
            if current_step_index == 0:
                self.writing_stage = "planning"
                next_prompt = "请分析收集的信息，确定文章主题和标题。"
            elif current_step_index == 1:
                self.writing_stage = "introduction"
                next_prompt = f"""
请为文章《{self.article_title}》撰写引言部分。引言应：
1. 介绍文章主题和背景
2. 说明文章的目的和意义
3. 简要预告文章将要讨论的主要内容
4. 吸引读者继续阅读

引言应控制在300-500字左右，为后续章节做铺垫。
"""
            elif 2 <= current_step_index < 2 + len(self.chapter_structure):
                self.writing_stage = "chapters"
                chapter_index = current_step_index - 2
                chapter_title = self.chapter_structure[chapter_index]

                # 加入前文摘要以增强连贯性
                context = self._get_previous_content_summary(chapter_index)

                next_prompt = f"""
请撰写文章《{self.article_title}》的第{chapter_index + 1}章："{chapter_title}"。

{context}

请确保本章内容：
1. 与前文内容保持连贯，避免重复已经讨论过的内容
2. 深入探讨章节主题，提供有价值的分析和见解
3. 如有必要，引用相关的数据、例子或信息源支持你的观点
4. 使用清晰的小标题或段落划分，使内容易于阅读
"""
            elif current_step_index == 2 + len(self.chapter_structure):
                self.writing_stage = "conclusion"
                next_prompt = f"""
请为文章《{self.article_title}》撰写结论部分。结论应：
1. 总结文章的主要观点和发现
2. 强调文章的价值和意义
3. 可以提出一些思考或未来展望
4. 给读者留下深刻印象

请确保结论与文章主体内容紧密相关，避免引入全新的概念或信息。
"""
            else:
                self.writing_stage = "review"
                next_prompt = f"""
请审查整篇文章《{self.article_title}》，重点检查：
1. 内容的逻辑连贯性
2. 是否存在重复或冗余内容
3. 章节之间的过渡是否自然
4. 技术准确性和专业表达

请提供修改建议，或直接给出优化后的完整文章。
"""

            # 更新提示
            self.next_step_prompt = next_prompt

        # 调用父类方法继续处理
        return await super().think()

    async def act(self) -> str:
        """执行当前步骤并保存生成的内容"""
        # 执行父类方法获取结果
        result = await super().act()

        # 保存生成的内容
        current_step_index = self.current_step_index
        if current_step_index is not None:
            if current_step_index == 0:  # 规划步骤
                # 从结果中提取标题
                if not self.article_title and "标题" in result:
                    lines = result.strip().split('\n')
                    for line in lines:
                        if "标题" in line:
                            self.article_title = line.split(":", 1)[1].strip() if ":" in line else line.split("：", 1)[1].strip()
                            break
            elif current_step_index == 1:  # 引言
                self.article_intro = result
                self.content_summaries[current_step_index] = self._summarize_content(result)
            elif 2 <= current_step_index < 2 + len(self.chapter_structure):  # 章节内容
                chapter_index = current_step_index - 2
                self.chapter_contents[chapter_index] = result
                self.content_summaries[current_step_index] = self._summarize_content(result)
            elif current_step_index == 2 + len(self.chapter_structure):  # 结论
                self.article_conclusion = result
                self.content_summaries[current_step_index] = self._summarize_content(result)

        return result

    def _get_previous_content_summary(self, current_chapter_index: int) -> str:
        """获取前文内容摘要，用于增强章节间的连贯性"""
        context_parts = []

        # 添加引言摘要
        if 1 in self.content_summaries:
            context_parts.append(f"引言摘要：{self.content_summaries[1]}")

        # 添加之前章节的摘要
        for i in range(current_chapter_index):
            step_index = i + 2  # 章节步骤从2开始
            if step_index in self.content_summaries:
                chapter_title = self.chapter_structure[i]
                context_parts.append(f"第{i+1}章《{chapter_title}》摘要：{self.content_summaries[step_index]}")

        if not context_parts:
            return "这是文章的第一个内容章节，请确保与引言部分衔接自然。"

        return "前文内容概要：\n" + "\n\n".join(context_parts) + "\n\n请基于以上内容继续撰写，确保逻辑连贯，避免重复。"

    def _summarize_content(self, content: str, max_length: int = 200) -> str:
        """生成内容摘要"""
        # 实际项目中可以调用LLM生成摘要，这里简化处理
        if len(content) <= max_length:
            return content

        # 简单截取前N个字符
        summary = content[:max_length].strip() + "..."
        return summary

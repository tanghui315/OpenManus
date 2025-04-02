from typing import List, Dict, Any, Optional, Tuple

from pydantic import Field

from app.agent.planning import PlanningAgent
from app.schema import Message, ToolChoice
from app.tool import ToolCollection, Terminate
from app.tool.str_replace_editor import StrReplaceEditor
from app.tool.web_search import WebSearch
from app.tool.planning import PlanningTool
from app.rss_writer.tools.rss_feed import RSSFeedTool
from app.logger import logger


SYSTEM_PROMPT = """你是一个专业的AI技术热点分析师，专注于创建高质量的"AI热点速报"文章。

你的任务是基于提供的多篇文章信息，撰写一篇引人入胜的AI热点速报。遵循以下特定结构：

1. 从提供的文章中选择最有价值、最新颖的一篇作为主标题，确保标题能够吸引读者
2. 开篇概述本期热点速报将要讨论的主要内容和价值
3. 分别详细介绍每篇文章的核心技术要点和创新点
4. 为每个技术点分析提供明确的来源引用
5. 最后做一个全面的技术总结，指出发展趋势或应用前景

你的文章应该：
- 保持技术准确性和专业性
- 各部分逻辑清晰，重点突出
- 风格应当简洁明了，易于技术人员快速获取信息
- 确保为每个技术点明确标注来源

最终输出应该是一篇格式规范、信息丰富的AI热点速报，帮助读者快速了解当前AI领域的重要进展。
"""

NEXT_STEP_PROMPT = """基于收集的多篇文章信息，请开始撰写AI热点速报。

首先分析所有文章，确定：
1. 哪一篇文章最有价值，可以作为本期速报的主标题
2. 如何构建一个引人入胜的标题来吸引读者
3. 各篇文章的核心技术要点和创新点

然后按照AI热点速报的标准格式撰写文章。
"""


class ArticleWriterAgent(PlanningAgent):
    """针对AI热点速报优化的文章撰写Agent"""

    name: str = "article_writer"
    description: str = "基于多篇文章撰写AI热点速报"

    system_prompt: str = SYSTEM_PROMPT
    next_step_prompt: str = NEXT_STEP_PROMPT

    available_tools: ToolCollection = Field(
        default_factory=lambda: ToolCollection(
            WebSearch(), StrReplaceEditor(), PlanningTool(), RSSFeedTool(), Terminate()
        )
    )

    # 使用AUTO，允许大模型自由回答或调用工具
    tool_choices: ToolChoice = ToolChoice.AUTO  # type: ignore
    special_tool_names: List[str] = Field(default_factory=lambda: [Terminate().name])

    max_steps: int = 8  # 动态调整
    collected_info: List[Dict[str, Any]] = Field(default_factory=list)

    # 新增：保存文章结构和内容
    headline_article: Dict[str, Any] = Field(default_factory=dict)
    article_sources: List[Dict[str, Any]] = Field(default_factory=list)
    article_title: str = ""
    article_intro: str = ""
    article_sections: Dict[int, str] = Field(default_factory=dict)  # 各篇文章分析
    article_conclusion: str = ""
    writing_stage: str = "planning"  # planning, headline, introduction, sections, conclusion, review

    async def run(self, request: Optional[str] = None) -> str:
        """
        执行文章撰写的主流程

        Args:
            request: 可选的初始请求，例如要撰写的文章主题或包含的信息点

        Returns:
            执行结果的字符串描述，通常是撰写的文章内容
        """
        # 重置状态
        self.headline_article = {}
        self.article_sources = []
        self.article_sections = {}
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

        # 检查是否有足够的信息来撰写文章
        if not self.collected_info:
            logger.warning("没有收集到任何信息，无法撰写文章")
            return "没有足够的信息来撰写AI热点速报。请提供一些相关文章。"

        # 提取文章来源信息
        self._extract_article_sources()

        # 执行Agent主流程
        try:
            # 添加收集到的信息到记忆中 - 移到这里避免重复添加
            # 只在调用super().run之前添加一次
            self._add_collected_info_to_memory()

            # 确保传递request参数给父类方法
            result = await super().run(request)

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

    def _extract_article_sources(self):
        """从收集的信息中提取文章来源信息"""
        for info in self.collected_info:
            if "url" in info:
                source = {
                    "title": info.get("source", "未知标题"),
                    "url": info["url"],
                }
                self.article_sources.append(source)
                logger.debug(f"提取文章来源: {source['title']} - {source['url']}")

    def _assemble_final_article(self) -> str:
        """根据已生成的各部分内容，组装完整热点速报"""
        parts = []

        # 添加标题
        if self.article_title:
            parts.append(f"# {self.article_title}\n")

        # 添加引言/概述
        if self.article_intro:
            parts.append(self.article_intro)

        # 添加各篇文章分析
        sorted_sections = sorted(self.article_sections.items())
        for _, content in sorted_sections:
            parts.append(content)

        # 添加来源列表
        if self.article_sources:
            parts.append("## 文章来源")
            sources_list = []
            for i, source in enumerate(self.article_sources, 1):
                sources_list.append(f"{i}. [{source['title']}]({source['url']})")
            parts.append("\n".join(sources_list))

        # 添加结论
        if self.article_conclusion:
            parts.append(self.article_conclusion)

        return "\n\n".join(parts)

    async def _select_headline_and_plan(self) -> Tuple[str, List[Dict]]:
        """从收集的文章中选择最有价值的作为标题，并规划文章结构"""
        planning_prompt = """
基于以上收集的所有文章信息，请执行以下任务：

1. 分析所有文章，选择最有价值、最新颖、最能引起读者兴趣的一篇作为本期AI热点速报的主题
2. 为热点速报设计一个吸引人的标题，可以适当修改原文标题使其更加吸引读者
3. 确定如何分析每篇文章的技术要点，避免内容重复

请用以下格式回复：
主标题：[设计的吸引人标题]
选定文章：[所选文章的标题]
选定理由：[为什么选择这篇文章作为主题]

文章规划：
1. [第一篇文章标题] - [该篇核心技术点]
2. [第二篇文章标题] - [该篇核心技术点]
...
"""
        # 创建临时消息列表避免修改self.memory
        messages = self.memory.messages.copy()
        messages.append(Message.user_message(planning_prompt))

        try:
            # 使用ask而不是ask_tool，因为这里只需要文本响应
            plan_response = await self.llm.ask(
                messages=messages,
                system_msgs=[Message.system_message(self.system_prompt)]
            )

            if not plan_response:
                logger.warning("规划响应为空，使用默认值")
                return "AI热点速报", []

            # 解析响应提取标题和文章规划
            title, article_plan = self._parse_headline_response(plan_response)
            logger.info(f"已确定热点速报标题: {title}")
            logger.info(f"已规划文章分析结构: {len(article_plan)}篇")

            return title, article_plan
        except Exception as e:
            logger.error(f"选择头条和规划结构失败: {str(e)}")
            return "AI热点速报", []  # 返回默认值

    def _parse_headline_response(self, response: str) -> Tuple[str, List[Dict]]:
        """从规划响应中提取标题和文章分析规划"""
        lines = response.strip().split('\n')
        title = ""
        selected_article = ""
        reason = ""
        article_plan = []

        # 解析模式：标题/规划
        mode = "header"

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # 解析标题部分
            if mode == "header":
                if line.startswith("主标题"):
                    title = line.split("：", 1)[1].strip() if "：" in line else line.split(":", 1)[1].strip()
                elif line.startswith("选定文章"):
                    selected_article = line.split("：", 1)[1].strip() if "：" in line else line.split(":", 1)[1].strip()
                elif line.startswith("选定理由"):
                    reason = line.split("：", 1)[1].strip() if "：" in line else line.split(":", 1)[1].strip()
                elif line.startswith("文章规划"):
                    mode = "plan"

            # 解析文章规划部分
            elif mode == "plan" and line[0].isdigit() and "." in line:
                # 尝试提取文章标题和核心技术点
                try:
                    article_info = line.split(".", 1)[1].strip()
                    if "-" in article_info:
                        article_title, tech_point = article_info.split("-", 1)
                        article_plan.append({
                            "title": article_title.strip(),
                            "tech_point": tech_point.strip()
                        })
                    else:
                        article_plan.append({
                            "title": article_info.strip(),
                            "tech_point": ""
                        })
                except Exception as e:
                    logger.warning(f"解析文章规划行失败: {line}, 错误: {str(e)}")

        # 保存选定的头条文章信息
        self.headline_article = {
            "title": selected_article,
            "reason": reason
        }

        return title, article_plan

    async def _generate_article_without_plan(self) -> str:
        """当计划创建失败时，尝试直接生成文章"""
        direct_request = """
由于计划创建过程中断，现在请直接基于所有提供的信息撰写一篇完整的AI热点速报。文章应：

1. 从所有文章中选择最有价值的一个作为主标题，确保标题吸引人
2. 开头概述本期速报将讨论的内容
3. 分别分析每篇文章的核心技术要点
4. 为每个技术点明确标注来源
5. 以技术总结和前景展望结尾

请确保内容准确、专业且有见地，同时格式符合AI热点速报的标准。
"""
        self.memory.add_message(Message.user_message(direct_request))
        response = await self.llm.ask(
            messages=self.memory.messages,
            system_msgs=[Message.system_message(self.system_prompt)]
        )
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
        formatted_info = "## 收集到的文章信息\n\n"

        for i, info in enumerate(self.collected_info, 1):
            formatted_info += f"### 文章 {i}: {info['source']}\n"

            if "url" in info:
                formatted_info += f"来源: {info['url']}\n"

            formatted_info += f"\n{info['content']}\n\n"

        # 添加到记忆中
        self.memory.add_message(Message.user_message(formatted_info))
        logger.debug(f"已将 {len(self.collected_info)} 篇文章信息添加到记忆中")

    async def create_initial_plan(self, request: str) -> None:
        """
        创建初始文章写作计划，针对AI热点速报格式

        Args:
            request: 初始请求，包含文章主题或要求
        """
        logger.info(f"创建AI热点速报初始计划，请求: {request[:50]}...")

        # 此时memory中应该已经包含了收集的文章信息
        # 首先添加用户请求到内存 - 使用单个消息避免重复
        self.memory.add_message(Message.user_message(request))

        try:
            # 分析文章并选择标题、规划结构
            self.article_title, article_plan = await self._select_headline_and_plan()

            # 根据文章规划创建动态计划步骤
            plan_steps = [
                "选择最有价值的文章作为头条并设计标题",
                "撰写热点速报开篇概述",
            ]

            # 为每篇文章创建分析步骤
            for i, article in enumerate(article_plan, 1):
                plan_steps.append(f"分析第{i}篇文章: {article['title']}")

            # 添加结论步骤
            plan_steps.append("撰写技术总结和前景展望")
            plan_steps.append("审查全文，确保格式规范和内容准确")

            # 动态调整最大步骤数
            self.max_steps = len(plan_steps)
            logger.info(f"根据文章数量，设置最大步骤为: {self.max_steps}")

            # 设置计划ID
            plan_id = self.active_plan_id or f"article_plan_{self.name}"
            self.active_plan_id = plan_id

            # 使用PlanningAgent原生方式创建计划
            # 构建创建计划的消息
            plan_message = f"""
我需要创建一个AI热点速报撰写计划，标题为《{self.article_title}》。
这是一个步骤明确的计划，包含以下{len(plan_steps)}个步骤:

{chr(10).join([f"{i+1}. {step}" for i, step in enumerate(plan_steps)])}

请帮我创建这个计划，plan_id为: {plan_id}
"""
            # 添加计划创建请求到记忆中
            self.memory.add_message(Message.user_message(plan_message))

            # 使用父类方法的方式，让LLM决定如何调用planning工具
            response = await self.llm.ask_tool(
                messages=self.memory.messages,
                system_msgs=[Message.system_message(self.system_prompt)],
                tools=self.available_tools.to_params(),
                tool_choice=ToolChoice.AUTO,
            )

            if not response or not response.tool_calls:
                # 如果LLM没有调用工具，手动创建计划
                logger.warning("LLM没有创建计划，手动创建")
                result = await self.available_tools.execute(
                    name="planning",
                    tool_input={
                        "command": "create",
                        "plan_id": plan_id,
                        "title": f"《{self.article_title}》AI热点速报撰写计划",
                        "description": f"基于收集的文章信息撰写一篇AI热点速报",
                        "steps": plan_steps
                    }
                )
                logger.info(f"手动创建计划结果: {result}")
            else:
                # 将LLM响应添加到记忆
                assistant_msg = Message.from_tool_calls(
                    content=response.content,
                    tool_calls=response.tool_calls
                )
                self.memory.add_message(assistant_msg)

                # 执行工具调用
                executed = False
                for tool_call in response.tool_calls:
                    if tool_call.function.name == "planning":
                        result = await self.execute_tool(tool_call)
                        tool_msg = Message.tool_message(
                            content=result,
                            tool_call_id=tool_call.id,
                            name=tool_call.function.name,
                        )
                        self.memory.add_message(tool_msg)
                        executed = True
                        logger.info(f"通过LLM创建计划成功: {plan_id}")
                        break

                if not executed:
                    # 如果LLM没有调用planning工具，手动创建
                    result = await self.available_tools.execute(
                        name="planning",
                        tool_input={
                            "command": "create",
                            "plan_id": plan_id,
                            "title": f"《{self.article_title}》AI热点速报撰写计划",
                            "description": f"基于收集的文章信息撰写一篇AI热点速报",
                            "steps": plan_steps
                        }
                    )
                    logger.info(f"LLM未调用planning工具，手动创建计划: {result}")

        except Exception as e:
            logger.error(f"创建计划过程中出错: {str(e)}")
            self.active_plan_id = None

    async def think(self) -> bool:
        """重写think方法，根据当前步骤更新提示和状态"""
        # 获取当前步骤索引前记录日志
        logger.info(f"开始think()方法，当前writing_stage={self.writing_stage}，查询当前步骤索引...")

        current_step_index = await self._get_current_step_index()
        logger.info(f"获取到当前步骤索引: {current_step_index}")

        # 获取计划总步数，用于检查进度
        plan_steps_count = 0
        if self.active_plan_id:
            plan_str = await self.get_plan()
            logger.debug(f"获取到计划内容: {plan_str}")

            # 修改计划步骤识别方式，PlanningTool返回的格式通常是"- [ ] 步骤描述"
            steps_lines = [line for line in plan_str.split('\n')
                          if line.strip().startswith(('- [ ]', '- [→]', '- [✓]'))]
            plan_steps_count = len(steps_lines)

            # 如果上面的方式没有找到步骤，尝试另一种格式
            if plan_steps_count == 0:
                # 尝试查找Steps:和Notes:之间的行数
                steps_part = False
                steps_lines = []
                for line in plan_str.split('\n'):
                    line = line.strip()
                    if line == "Steps:":
                        steps_part = True
                        continue
                    elif line == "Notes:" or line.startswith("Created at:"):
                        steps_part = False
                    elif steps_part and line and not line.startswith("Plan"):
                        steps_lines.append(line)
                plan_steps_count = len(steps_lines)

            # 如果仍然找不到步骤，使用我们设置的max_steps
            if plan_steps_count == 0:
                plan_steps_count = self.max_steps
                logger.warning(f"无法从计划中识别步骤，使用预设的max_steps: {self.max_steps}")

            logger.info(f"计划总步数: {plan_steps_count}, 当前步骤: {current_step_index}")

            # 保存计划步骤总数到实例变量，确保act方法可以访问
            self.plan_steps_count = plan_steps_count
        else:
            # 如果没有激活的计划，使用max_steps
            self.plan_steps_count = self.max_steps
            logger.warning(f"没有激活的计划，使用预设的max_steps: {self.max_steps}")

        # 更新current_step_index到实例变量，确保act方法可以访问
        self.current_step_index = current_step_index

        if current_step_index is not None:
            # 检测是否卡在同一步骤，添加防止重复的处理
            if hasattr(self, '_last_step_index') and self._last_step_index == current_step_index:
                if hasattr(self, '_same_step_count'):
                    self._same_step_count += 1
                else:
                    self._same_step_count = 1

                logger.warning(f"连续{self._same_step_count}次停留在步骤{current_step_index}")

                # 如果连续3次卡在同一步骤，尝试强制推进
                if self._same_step_count >= 3:
                    logger.warning(f"检测到连续{self._same_step_count}次停留在步骤{current_step_index}，尝试强制推进")
                    try:
                        # 手动标记当前步骤为完成
                        await self.available_tools.execute(
                            name="planning",
                            tool_input={
                                "command": "mark_step",
                                "plan_id": self.active_plan_id,
                                "step_index": current_step_index,
                                "step_status": "completed",
                            },
                        )
                        # 重新获取当前步骤
                        current_step_index = await self._get_current_step_index()
                        self.current_step_index = current_step_index
                        logger.info(f"强制推进后，新的步骤索引: {current_step_index}")
                        # 重置计数器
                        self._same_step_count = 0

                        # 如果还是相同步骤，抛出异常强制进入fallback模式
                        if current_step_index == self._last_step_index:
                            raise ValueError(f"无法推进步骤，当前步骤{current_step_index}卡住")
                    except Exception as e:
                        logger.error(f"强制推进步骤失败: {str(e)}")
                        # 如果强制推进失败，直接进入写作阶段，跳过剩余步骤
                        self.writing_stage = "review"
                        return False

            # 记录当前步骤索引，用于下次检测是否卡住
            self._last_step_index = current_step_index

            # 根据当前步骤更新writing_stage
            if current_step_index == 0:
                self.writing_stage = "headline"
                next_prompt = "请分析所有文章，选择最有价值的一篇作为头条，并设计一个吸引人的标题。"
            elif current_step_index == 1:
                self.writing_stage = "introduction"
                next_prompt = f"""
请为AI热点速报《{self.article_title}》撰写开篇概述，字数控制在300-500字左右。概述应：
1. 简要介绍本期速报的主题和价值
2. 概括将要分析的几篇文章的核心技术亮点
3. 说明这些技术进展的重要性
4. 吸引读者继续阅读后续内容

请确保内容简明扼要，突出信息价值，避免重复之前生成的内容。
"""
            elif 2 <= current_step_index < self.plan_steps_count - 2:
                self.writing_stage = "sections"
                article_index = current_step_index - 2

                # 获取对应的文章信息(如果有)
                article_info = None
                if article_index < len(self.collected_info):
                    article_info = self.collected_info[article_index]

                article_title = article_info["source"] if article_info else f"第{article_index+1}篇文章"
                article_url = article_info.get("url", "未知来源") if article_info else "未知来源"

                # 确保不要重复之前分析过的文章
                if article_index in self.article_sections:
                    logger.warning(f"第{article_index+1}篇文章已经分析过，将跳过")
                    # 手动标记当前步骤为完成并推进
                    await self.available_tools.execute(
                        name="planning",
                        tool_input={
                            "command": "mark_step",
                            "plan_id": self.active_plan_id,
                            "step_index": current_step_index,
                            "step_status": "completed",
                        },
                    )
                    # 重新获取当前步骤
                    current_step_index = await self._get_current_step_index()
                    self.current_step_index = current_step_index
                    logger.info(f"跳过已分析文章，新的步骤索引: {current_step_index}")
                    # 递归调用think方法处理新步骤
                    return await self.think()

                next_prompt = f"""
请分析《{self.article_title}》中的第{article_index + 1}篇文章: {article_title} (来源: {article_url})

请对这篇文章进行深入分析，内容应包括：
1. 文章介绍的技术创新点或核心发现
2. 该技术的工作原理或关键方法
3. 潜在的应用场景或影响
4. 与其他技术的比较优势（如适用）

格式要求：
- 使用"## [文章标题]"作为该部分的标题
- 在文末标注来源: [文章标题](URL链接)
- 确保分析简洁明了，重点突出
- 控制在500字内，保持内容精炼
"""
            elif current_step_index == self.plan_steps_count - 2:
                self.writing_stage = "conclusion"
                next_prompt = f"""
请为AI热点速报《{self.article_title}》撰写技术总结和前景展望。总结应：
1. 归纳本期所有文章分析的核心技术趋势
2. 探讨这些技术的未来发展方向
3. 分析可能的产业影响或应用前景
4. 提供对读者有价值的见解或建议

请确保总结与前面分析的内容保持一致，突出整体技术发展脉络。
"""
            else:
                self.writing_stage = "review"
                next_prompt = f"""
请审查整篇AI热点速报《{self.article_title}》，重点检查：
1. 标题是否足够吸引人
2. 开篇概述是否简明扼要
3. 各文章分析是否重点突出
4. 来源引用是否明确
5. 结论部分是否有价值和见解

请直接给出优化后的完整热点速报。确保格式规范，内容专业准确。
"""

            # 更新提示
            self.next_step_prompt = next_prompt
            logger.info(f"已设置next_step_prompt，当前writing_stage={self.writing_stage}")
        else:
            logger.warning("无法获取当前步骤索引，可能是计划未创建或已完成")
            # 如果无法获取步骤索引，但self.writing_stage不是review，设置为review
            if self.writing_stage != "review":
                self.writing_stage = "review"
                self.next_step_prompt = f"""
请整合已有内容，生成一篇完整的AI热点速报《{self.article_title or "AI热点速报"}》。
确保包含标题、开篇概述、各文章分析、来源引用和技术总结。
"""
                logger.info("无法获取步骤索引，设置为review阶段")

        # 调用父类方法继续处理
        return await super().think()

    async def act(self) -> str:
        """执行当前步骤并保存生成的内容"""
        # 执行前记录当前步骤
        logger.info(f"开始act()方法，执行步骤{self.current_step_index}，writing_stage={self.writing_stage}")

        # 执行父类方法获取结果
        result = await super().act()
        logger.info(f"步骤{self.current_step_index}执行完毕，结果长度: {len(result)}")

        # 保存生成的内容
        current_step_index = self.current_step_index
        if current_step_index is not None:
            if current_step_index == 0:  # 标题选择
                if not self.article_title:
                    # 尝试从结果中提取标题
                    lines = result.strip().split('\n')
                    for line in lines:
                        if "标题" in line or "题目" in line:
                            parts = line.split(":", 1) if ":" in line else line.split("：", 1)
                            if len(parts) > 1:
                                self.article_title = parts[1].strip()
                                logger.info(f"从结果中提取到标题: {self.article_title}")
                                break

                    # 如果无法从结果中提取标题，使用默认标题
                    if not self.article_title:
                        # 尝试使用result的第一行作为标题
                        if result and "\n" in result:
                            self.article_title = result.split("\n")[0].strip()
                            if self.article_title.startswith("#"):
                                self.article_title = self.article_title[1:].strip()
                            logger.info(f"使用第一行作为标题: {self.article_title}")
                        else:
                            self.article_title = "AI热点速报"
                            logger.warning(f"无法提取标题，使用默认标题: {self.article_title}")

            elif current_step_index == 1:  # 开篇概述
                self.article_intro = result
                logger.info(f"已保存文章开篇概述，长度: {len(self.article_intro)}")

            elif 2 <= current_step_index < self.plan_steps_count - 2:  # 文章分析
                article_index = current_step_index - 2
                if article_index not in self.article_sections:  # 避免重复
                    self.article_sections[article_index] = result
                    logger.info(f"已保存第{article_index+1}篇文章分析，长度: {len(result)}")
                else:
                    logger.warning(f"第{article_index+1}篇文章分析已存在，跳过保存")

            elif current_step_index == self.plan_steps_count - 2:  # 技术总结
                self.article_conclusion = result
                logger.info(f"已保存技术总结，长度: {len(self.article_conclusion)}")

            # 确保当前步骤在执行完后被标记为完成
            try:
                await self.available_tools.execute(
                    name="planning",
                    tool_input={
                        "command": "mark_step",
                        "plan_id": self.active_plan_id,
                        "step_index": current_step_index,
                        "step_status": "completed",
                    },
                )
                logger.info(f"已将步骤{current_step_index}标记为已完成")
            except Exception as e:
                logger.error(f"标记步骤{current_step_index}为已完成失败: {str(e)}")

        # 如果是review阶段，组装最终文章
        if self.writing_stage == "review":
            # 无论步骤索引如何，都尝试组装文章
            complete_article = self._assemble_final_article()
            logger.info(f"已组装完整文章，长度: {len(complete_article)}")

            # 如果组装后的文章很短，可能出现了问题，直接返回result
            if len(complete_article) < 200 and len(result) > 200:
                logger.warning(f"组装文章过短({len(complete_article)}字符)，使用模型直接生成的结果({len(result)}字符)")
                return result
            return complete_article

        return result

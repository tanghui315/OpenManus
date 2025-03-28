from typing import List, Dict, Any, Optional

from pydantic import Field

from app.agent.planning import PlanningAgent
from app.schema import Message, ToolChoice
from app.tool import ToolCollection, Terminate, BrowserUseTool
from app.tool.str_replace_editor import StrReplaceEditor


SYSTEM_PROMPT = """你是一个专业的技术内容创作者，专注于创建高质量的技术文章。

你的任务是基于提供的信息来撰写一篇完整的技术文章。遵循以下步骤：

1. 分析收集到的信息，确定一个引人注目且有教育意义的主题
2. 创建清晰的文章结构，包括引言、主体部分和结论
3. 撰写详细内容，确保技术准确性和深度
4. 在必要的地方添加示例代码、图表描述或实践建议

如果提供的信息不足以创建高质量的文章，请明确说明，不要编造内容或过度延伸有限的信息。

你的文章应该：
- 有清晰的逻辑结构
- 提供有价值的技术见解
- 使用专业但易于理解的语言
- 引用和整合所有相关的信息源

最终输出应该是一篇可以直接发布的完整技术文章。
"""

NEXT_STEP_PROMPT = """基于我们收集的信息，请开始撰写技术文章。

首先规划文章结构，包括:
1. 文章主题和标题
2. 主要章节划分
3. 每个章节需要涵盖的关键点

然后按照规划撰写完整文章内容。如果收集的信息不足以创建高质量的文章，请直接说明。
"""


class ArticleWriterAgent(PlanningAgent):
    """撰写技术文章的Agent"""

    name: str = "article_writer"
    description: str = "基于收集的信息撰写技术文章"

    system_prompt: str = SYSTEM_PROMPT
    next_step_prompt: str = NEXT_STEP_PROMPT

    available_tools: ToolCollection = Field(
        default_factory=lambda: ToolCollection(
            BrowserUseTool(), StrReplaceEditor(), Terminate()
        )
    )

    # 使用AUTO，允许大模型自由回答或调用工具
    tool_choices: ToolChoice = ToolChoice.AUTO  # type: ignore
    special_tool_names: List[str] = Field(default_factory=lambda: [Terminate().name])

    max_steps: int = 10  # 撰写文章可能需要更多步骤
    collected_info: List[Dict[str, Any]] = Field(default_factory=list)

    async def run(self, request: Optional[str] = None) -> str:
        """
        执行文章撰写的主流程

        Args:
            request: 可选的初始请求，例如要撰写的文章主题或包含的信息点

        Returns:
            执行结果的字符串描述，通常是撰写的文章内容
        """
        # 初始化收集的信息
        if not self.collected_info and request:
            # 如果有初始请求，将其作为第一条信息
            self.collected_info.append({
                "source": "initial_request",
                "content": request
            })

        # 添加收集到的信息到记忆中
        self._add_collected_info_to_memory()

        # 执行Agent主流程
        return await super().run()

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

    def _add_collected_info_to_memory(self) -> None:
        """将收集到的信息添加到Agent的记忆中"""
        if not self.collected_info:
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

    async def create_initial_plan(self, request: str) -> None:
        """
        创建初始文章写作计划

        Args:
            request: 初始请求，包含文章主题或要求
        """
        # 首先添加用户请求
        self.memory.add_message(Message.user_message(request))

        # 创建初始写作计划
        plan_steps = [
            "分析收集的信息，确定文章主题和范围",
            "定义文章结构，包括主要章节",
            "撰写引言部分，介绍文章主题和目的",
            "撰写主体部分的各个章节",
            "撰写结论和总结",
            "审查和优化文章内容"
        ]

        # 使用PlanningTool创建计划
        plan_id = f"article_plan_{self.name}"
        self.active_plan_id = plan_id

        # 创建计划
        await self.available_tools.execute(
            name="planning",
            tool_input={
                "command": "create",
                "plan_id": plan_id,
                "title": "技术文章撰写计划",
                "description": f"基于提供的信息撰写一篇关于{request[:50]}...的技术文章",
                "steps": plan_steps
            }
        )

        # 更新下一步提示
        self.next_step_prompt = (
            f"基于以下收集到的信息，请开始撰写技术文章，首先定义文章主题和结构。\n\n"
            f"如果收集的信息不足以创建高质量的文章，请直接说明，我们可以收集更多信息。"
        )

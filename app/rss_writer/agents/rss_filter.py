from typing import List, Dict, Any, Optional

from pydantic import Field

from app.agent.toolcall import ToolCallAgent
from app.schema import Message, ToolChoice
from app.tool import ToolCollection, Terminate, BrowserUseTool
from app.rss_writer.tools.rss_feed import RSSFeedTool


SYSTEM_PROMPT = """你是一个内容评估专家。你需要评估RSS条目的价值，并决定哪些值得进一步阅读。

判断标准：
1. 技术相关性 - 是否包含有用的技术信息
2. 新颖性 - 是否包含新的观点或信息
3. 深度 - 是否不只是表面的新闻

只有同时满足这些标准的文章才应该被选中。选择的文章应该能帮助技术人员学习新知识或获取有价值的见解。

你的工作流程：
1. 分析RSS Feed中的所有条目
2. 评估每个条目的价值
3. 选择最有价值的文章（最多5篇）
4. 如果没有满足标准的文章，请明确说明没有找到有价值的文章

输出应该包含你选择的文章列表，以及为什么这些文章有价值的简短解释。
"""

NEXT_STEP_PROMPT = """请评估这些RSS条目，并选择最有价值的文章（最多5篇）进行深入阅读。
如果没有满足标准的文章，请明确说明没有找到有价值的文章。

你需要输出以下内容：
1. 你选择的文章列表（包括标题和链接）
2. 为什么这些文章有价值的简短解释
3. 明确说明下一步操作：是访问这些文章获取更多信息，还是因为没有价值文章而结束
"""


class RSSFilterAgent(ToolCallAgent):
    """评估RSS文章价值的Agent"""

    name: str = "rss_filter"
    description: str = "评估RSS文章价值并决定是否深入阅读"

    system_prompt: str = SYSTEM_PROMPT
    next_step_prompt: str = NEXT_STEP_PROMPT

    available_tools: ToolCollection = Field(
        default_factory=lambda: ToolCollection(
            RSSFeedTool(),  Terminate()
        )
    )

    # 使用AUTO，允许大模型自由回答或调用工具
    tool_choices: ToolChoice = ToolChoice.AUTO  # type: ignore
    special_tool_names: List[str] = Field(default_factory=lambda: [Terminate().name])

    max_steps: int = 5  # RSS筛选通常步骤较少
    selected_articles: List[Dict[str, Any]] = Field(default_factory=list)

    async def run(self, request: Optional[str] = None) -> str:
        """
        执行RSS内容筛选的主流程

        Args:
            request: 可选的初始请求，例如RSS feed的URL

        Returns:
            执行结果的字符串描述
        """
        # 清空已选文章列表
        self.selected_articles = []

        # 执行Agent主流程
        result = await super().run(request)

        # 解析结果中的选定文章
        self._parse_selected_articles()

        return result

    def _parse_selected_articles(self) -> None:
        """从最后的助手消息中解析选定的文章"""
        # 寻找最后一条助手消息
        for msg in reversed(self.memory.messages):
            if msg.role == "assistant" and msg.content:
                if "没有找到有价值的文章" in msg.content:
                    self.selected_articles = []
                    return

                # 使用正则表达式查找Markdown链接 [Title](URL)
                # \[([^\]]+)\] 匹配方括号内的标题文字 (捕获组1)
                # \((https?://\S+)\) 匹配圆括号内的URL (捕获组2)
                import re
                matches = re.findall(r'\[([^\]]+)\]\((https?://\S+)\)', msg.content)

                self.selected_articles = [] # 清空之前的错误解析（如果运行多次）
                for title, url in matches:
                     # 检查是否是Reddit链接（可选，增加精确度）
                     # if "reddit.com" in url: # 可以取消注释这行来只选择reddit链接
                         self.selected_articles.append({
                             "title": title.strip(), # 去除可能的首尾空格
                             "url": url
                         })

                # 解析完成后直接返回，不需要后续的旧逻辑
                return

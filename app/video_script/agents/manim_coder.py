"""
Manim代码生成Agent模块

负责为视频脚本中的关键概念生成Manim动画代码
"""

from typing import List, Dict, Any, Optional

from pydantic import Field

from app.agent.base import BaseAgent
from app.schema import Message, ToolChoice
from app.tool import ToolCollection, Terminate, WebSearch, StrReplaceEditor
from app.logger import logger
from app.video_script.agents.script_writer import WebExtractTool


SYSTEM_PROMPT = """你是一位Manim动画编程专家，精通使用Manim库创建数学和技术概念的可视化动画。

你的任务是根据技术教学视频脚本中的概念，生成精确、可视化效果良好的Manim代码。生成的代码应当：

1. 使用最新的Manim社区版(manim-community)语法
2. 清晰可视化给定的概念，增强观众理解
3. 代码结构良好，包含必要的注释
4. 能够独立运行，无需额外依赖
5. 遵循Manim的最佳实践

动画设计应考虑：
- 视觉清晰度：元素大小、颜色和布局合理
- 动画流畅度：使用适当的过渡和时间设置
- 教学效果：动画应强化概念理解，而非仅作装饰
- 复杂度平衡：动画要足够有趣但不过度复杂

请确保生成的代码在语法上正确，并提供详细注释说明每个部分的功能和用途。
"""


class ManimCoderAgent(BaseAgent):
    """Manim动画代码生成Agent

    负责为技术教学视频的关键概念生成Manim动画代码
    """

    name: str = "manim_coder"
    description: str = "生成Manim动画代码"

    system_prompt: str = SYSTEM_PROMPT

    available_tools: ToolCollection = Field(
        default_factory=lambda: ToolCollection(
            WebSearch(), WebExtractTool(), StrReplaceEditor(), Terminate()
        )
    )

    # 使用AUTO，允许大模型自由回答或调用工具
    tool_choices: ToolChoice = ToolChoice.AUTO

    max_interactions: int = 3  # 限制Agent的最大交互次数
    collected_info: List[Dict[str, Any]] = Field(default_factory=list)

    async def run(self, request: str) -> str:
        """
        执行Manim代码生成的主流程

        Args:
            request: 包含要可视化的概念和上下文的请求

        Returns:
            生成的Manim代码
        """
        try:
            # 重置状态
            self.memory.clear()
            self.collected_info = []

            # 创建初始提示
            logger.info(f"开始为请求生成Manim代码: {request[:50]}...")
            self.memory.add_message(Message.system_message(self.system_prompt))
            self.memory.add_message(Message.user_message(request))

            # 执行信息收集和代码生成
            interaction_count = 0
            has_answer = False
            final_response = ""

            while interaction_count < self.max_interactions:
                interaction_count += 1
                logger.debug(f"Manim代码生成交互 {interaction_count}/{self.max_interactions}")

                # 思考下一步行动
                response = await self.llm.ask_tool(
                    messages=self.memory.messages,
                    tools=self.available_tools.to_params(),
                    tool_choice=self.tool_choices,
                )

                # 如果有工具调用，执行工具调用
                if response.tool_calls:
                    # 添加工具调用到内存
                    assistant_msg = Message.from_tool_calls(
                        content=response.content,
                        tool_calls=response.tool_calls
                    )
                    self.memory.add_message(assistant_msg)

                    # 执行工具调用
                    for tool_call in response.tool_calls:
                        # 检查是否调用了终止工具
                        if tool_call.function.name == "terminate":
                            has_answer = True
                            tool_result = await self.execute_tool(tool_call)
                            args = self._parse_args(tool_call)
                            final_response = args.get("output", "")

                            # 添加工具结果到内存
                            tool_msg = Message.tool_message(
                                content=tool_result,
                                tool_call_id=tool_call.id,
                                name=tool_call.function.name,
                            )
                            self.memory.add_message(tool_msg)
                            break
                        else:
                            # 执行其他工具
                            tool_result = await self.execute_tool(tool_call)

                            # 如果是搜索工具，收集信息
                            if tool_call.function.name == "web_search":
                                args = self._parse_args(tool_call)
                                query = args.get("search_term", "")
                                if query:
                                    self.collected_info.append({
                                        "query": query,
                                        "result": tool_result
                                    })

                            # 添加工具结果到内存
                            tool_msg = Message.tool_message(
                                content=tool_result,
                                tool_call_id=tool_call.id,
                                name=tool_call.function.name,
                            )
                            self.memory.add_message(tool_msg)

                    # 如果找到了答案，跳出循环
                    if has_answer:
                        break
                else:
                    # 如果没有工具调用，直接使用回复作为最终结果
                    self.memory.add_message(Message.assistant_message(response.content))
                    final_response = response.content
                    break

            # 如果到达最大交互次数但没有明确答案，使用最后一次响应
            if not has_answer and not final_response:
                # 发送最后一次请求，要求生成最终代码
                final_request = "请基于已收集的信息，生成最终的Manim动画代码。确保代码完整且可运行。"
                self.memory.add_message(Message.user_message(final_request))

                response = await self.llm.ask(
                    messages=self.memory.messages,
                    system_msgs=[Message.system_message(self.system_prompt)]
                )

                final_response = response

            # 清理代码结果，确保代码格式正确
            cleaned_response = self._clean_code_response(final_response)

            logger.info("Manim代码生成完成")
            return cleaned_response

        except Exception as e:
            logger.error(f"Manim代码生成过程中出错: {str(e)}")
            return f"Manim代码生成失败: {str(e)}"

    def _parse_args(self, tool_call) -> Dict[str, Any]:
        """从工具调用中解析参数"""
        import json
        try:
            if tool_call.function.arguments:
                return json.loads(tool_call.function.arguments)
        except:
            pass
        return {}

    def _clean_code_response(self, response: str) -> str:
        """清理代码响应，提取和格式化Python代码块"""
        # 如果响应已经是纯Python代码，直接返回
        if response.strip().startswith("from manim import") or response.strip().startswith("import manim"):
            return response

        # 提取代码块
        code_blocks = []
        in_code_block = False
        current_block = []

        for line in response.split('\n'):
            if line.strip().startswith("```python") or line.strip() == "```python":
                in_code_block = True
                current_block = []
            elif line.strip() == "```" and in_code_block:
                in_code_block = False
                if current_block:
                    code_blocks.append('\n'.join(current_block))
                current_block = []
            elif in_code_block:
                current_block.append(line)

        # 如果代码块未正确关闭
        if in_code_block and current_block:
            code_blocks.append('\n'.join(current_block))

        # 使用第一个找到的有效代码块
        for code in code_blocks:
            if "import manim" in code or "from manim import" in code:
                return code

        # 如果没有找到有效的代码块，尝试从文本中提取代码
        if not code_blocks:
            # 查找可能的Python代码起始位置
            lines = response.split('\n')
            start_idx = -1
            for i, line in enumerate(lines):
                if "import manim" in line or "from manim import" in line:
                    start_idx = i
                    break

            if start_idx != -1:
                # 从导入语句开始收集代码行
                return '\n'.join(lines[start_idx:])

        # 如果找不到有效的Manim代码，使用第一个代码块或原始响应
        return code_blocks[0] if code_blocks else response

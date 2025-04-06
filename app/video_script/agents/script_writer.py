"""
脚本撰写Agent模块

负责根据关键字生成结构化的技术视频脚本
"""

from typing import List, Dict, Any, Optional

from pydantic import Field

from app.agent.base import BaseAgent
from app.schema import Message, ToolChoice
from app.tool import ToolCollection, Terminate, WebSearch, StrReplaceEditor
from app.logger import logger


SYSTEM_PROMPT = """你是一位专业的技术教学视频脚本撰写专家，擅长将复杂的技术概念转化为清晰、有条理的视频讲解脚本。

你的任务是基于给定的技术关键字，撰写一份结构完善、内容准确的技术教学视频脚本。脚本应当：

1. 结构清晰，包含引言、背景知识、核心概念解释、工作原理、实际应用和总结等部分
2. 语言自然流畅，适合口头表达和旁白录制
3. 保持技术准确性和专业性，同时照顾目标受众的知识水平
4. 通过"【可视化: 描述】内容【/可视化】"格式标记适合用动画展示的概念或公式
5. 为视频提供3-5个吸引人的标题建议

你可以使用搜索工具获取最新、准确的技术信息，确保脚本内容反映当前技术发展状况。

最终输出应当是一份可以直接用于视频制作的完整脚本，包含标题建议、章节结构和详细内容。
"""


class ScriptWriterAgent(BaseAgent):
    """技术视频脚本撰写Agent

    负责根据关键字生成结构化的技术视频脚本，包括内容规划、脚本撰写和标题建议
    """

    name: str = "script_writer"
    description: str = "根据技术关键字生成视频脚本"

    system_prompt: str = SYSTEM_PROMPT

    available_tools: ToolCollection = Field(
        default_factory=lambda: ToolCollection(
            WebSearch(), StrReplaceEditor(), Terminate()
        )
    )

    # 使用AUTO，允许大模型自由回答或调用工具
    tool_choices: ToolChoice = ToolChoice.AUTO

    max_interactions: int = 5  # 限制Agent的最大交互次数
    collected_info: List[Dict[str, Any]] = Field(default_factory=list)

    async def run(self, request: str) -> str:
        """
        执行脚本撰写的主流程

        Args:
            request: 包含技术关键字和目标受众的请求

        Returns:
            生成的技术视频脚本
        """
        try:
            # 重置状态
            self.memory.clear()
            self.collected_info = []

            # 创建初始提示
            logger.info(f"开始为请求撰写脚本: {request[:50]}...")
            self.memory.add_message(Message.system_message(self.system_prompt))
            self.memory.add_message(Message.user_message(request))

            # 执行信息收集和脚本生成
            interaction_count = 0
            has_answer = False
            final_response = ""

            while interaction_count < self.max_interactions:
                interaction_count += 1
                logger.debug(f"脚本生成交互 {interaction_count}/{self.max_interactions}")

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
                # 发送最后一次请求，要求生成最终答案
                final_request = "请基于已收集的信息，生成最终的视频脚本。包括标题建议和标记需要可视化的概念。"
                self.memory.add_message(Message.user_message(final_request))

                response = await self.llm.ask(
                    messages=self.memory.messages,
                    system_msgs=[Message.system_message(self.system_prompt)]
                )

                final_response = response

            logger.info("脚本生成完成")
            return final_response

        except Exception as e:
            logger.error(f"脚本生成过程中出错: {str(e)}")
            return f"脚本生成失败: {str(e)}"

    def _parse_args(self, tool_call) -> Dict[str, Any]:
        """从工具调用中解析参数"""
        import json
        try:
            if tool_call.function.arguments:
                return json.loads(tool_call.function.arguments)
        except:
            pass
        return {}

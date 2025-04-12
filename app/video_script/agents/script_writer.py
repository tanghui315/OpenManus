"""
脚本撰写Agent模块

负责根据关键字生成结构化的技术视频脚本
"""

from typing import List, Dict, Any, Optional
import time

from pydantic import Field

from app.agent.planning import PlanningAgent
from app.schema import Message, ToolChoice
from app.tool import ToolCollection, Terminate, WebSearch, StrReplaceEditor
from app.tool.planning import PlanningTool
from app.logger import logger
from app.video_script.tools import WebExtractTool

SYSTEM_PROMPT = """你是一位专业的技术教学视频脚本撰写专家，擅长将复杂的技术概念转化为清晰、有条理的视频讲解脚本。

你的任务是基于给定的技术关键字，撰写一份结构完善、内容准确的技术教学视频脚本。脚本应当：

1. 结构清晰，包含引言、背景知识、核心概念解释、工作原理、实际应用和总结等部分
2. 语言自然流畅，适合口头表达和旁白录制
3. 保持技术准确性和专业性，同时照顾目标受众的知识水平
4. 通过"【可视化: 描述】内容【/可视化】"格式标记适合用动画展示的概念或公式
5. 为视频提供3-5个吸引人的标题建议

你应该先搜索相关信息，然后提取页面内容进行分析，确保脚本内容全面准确并反映当前技术发展状况。

最终输出应当是一份可以直接用于视频制作的完整脚本，包含标题建议、章节结构和详细内容。
"""

NEXT_STEP_PROMPT = """
请按照当前计划的下一步行动。如果你需要信息，可以搜索或提取网页内容。
确保按照技术视频脚本的结构清晰地组织内容，并标记需要可视化的部分。
"""


class ScriptWriterAgent(PlanningAgent):
    """技术视频脚本撰写Agent

    负责根据关键字生成结构化的技术视频脚本，包括内容规划、脚本撰写和标题建议
    """

    name: str = "script_writer"
    description: str = "根据技术关键字生成视频脚本"

    system_prompt: str = SYSTEM_PROMPT
    next_step_prompt: str = NEXT_STEP_PROMPT

    available_tools: ToolCollection = Field(
        default_factory=lambda: ToolCollection(
            WebSearch(), WebExtractTool(), StrReplaceEditor(), PlanningTool(), Terminate()
        )
    )

    # 使用AUTO，允许大模型自由回答或调用工具
    tool_choices: ToolChoice = ToolChoice.AUTO

    max_steps: int = 30  # 从15增加到30，确保有足够步骤完成所有计划
    collected_info: List[Dict[str, Any]] = Field(default_factory=list)
    extracted_contents: List[Dict[str, Any]] = Field(default_factory=list)
    suggested_titles: List[str] = Field(default_factory=list)
    final_script: str = ""

    async def run(self, request: Optional[str] = None) -> str:
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
            self.extracted_contents = []
            self.suggested_titles = []
            self.final_script = ""

            # 创建初始提示
            logger.info(f"开始为请求撰写脚本: {request[:50] if request else ''}...")

            # 使用父类方法运行，它会调用create_initial_plan
            result = await super().run(request)
            logger.info(f"大模型最终返回结果(前200字符): {result[:200] if result else '空结果'}...")

            # 检查脚本是否生成
            if not self.final_script and len(self.memory.messages) > 0:
                logger.info("未通过常规方式生成脚本，尝试从记忆中恢复")
                # 尝试从最后的助手消息中获取脚本
                for message in reversed(self.memory.messages):
                    if message.role == "assistant" and len(message.content) > 500:
                        self.final_script = message.content
                        logger.info(f"从记忆中的助手消息恢复到脚本，长度: {len(message.content)}")
                        break

            # 强制保存机制：如果最终结果足够长但final_script为空，则使用result作为最终脚本
            if not self.final_script and result and len(result) > 500:
                self.final_script = result
                logger.info(f"将最终结果强制保存为脚本，长度: {len(result)}")

            # 确保返回有内容的结果
            return self.final_script or result

        except Exception as e:
            logger.error(f"脚本生成过程中出错: {str(e)}")
            return f"脚本生成失败: {str(e)}"

    async def create_initial_plan(self, request: str) -> None:
        """创建初始脚本生成计划"""
        logger.info(f"为技术关键字'{request}'创建脚本生成计划")

        # 解析请求
        keyword = request
        audience_level = "beginner"  # 默认目标受众

        # 如果请求包含受众级别信息，提取它
        if "intermediate" in request.lower() or "中级" in request:
            audience_level = "intermediate"
        elif "advanced" in request.lower() or "高级" in request:
            audience_level = "advanced"

        # 创建计划步骤
        plan_steps = [
            "搜索相关技术信息",
            "从搜索结果中提取和分析详细内容",
            "规划脚本结构和核心内容点",
            "起草脚本引言部分",
            "编写背景知识部分",
            "详细解释核心概念",
            "描述技术工作原理",
            "举例说明实际应用场景",
            "撰写总结部分",
            "标记需要可视化的概念和公式",
            "生成3-5个吸引人的标题建议",
            "整理完整脚本并进行最终优化"
        ]

        # 设置计划ID
        plan_id = f"script_plan_{self.name}_{int(time.time())}"
        self.active_plan_id = plan_id

        # 创建请求消息
        plan_message = f"""
我需要创建一个技术视频脚本撰写计划，主题为"{keyword}"，目标受众为{audience_level}级别。
请帮我创建以下步骤的计划:

{chr(10).join([f"{i+1}. {step}" for i, step in enumerate(plan_steps)])}

plan_id为: {plan_id}
"""
        # 添加到记忆
        self.memory.add_message(Message.user_message(plan_message))

        # 使用planning工具创建计划
        try:
            result = await self.available_tools.execute(
                name="planning",
                tool_input={
                    "command": "create",
                    "plan_id": plan_id,
                    "title": f"《{keyword}》技术视频脚本撰写计划 ({audience_level}级别)",
                    "description": f"基于关键字'{keyword}'撰写一份面向{audience_level}级别受众的技术视频脚本",
                    "steps": plan_steps
                }
            )
            logger.info(f"成功创建脚本撰写计划: {result}")
        except Exception as e:
            logger.error(f"创建计划失败: {str(e)}")

    async def act(self) -> str:
        """执行当前步骤，处理结果，并检查计划是否完成"""
        # 得到当前消息，用于后续提取模型输出
        last_message_index = len(self.memory.messages) - 1 if self.memory.messages else -1

        # 使用父类方法执行步骤
        result = await super().act()

        # 尝试从记忆中提取最新的助手消息，这是大模型的实际输出
        model_output = ""
        if last_message_index >= 0 and len(self.memory.messages) > last_message_index + 1:
            # 找到新增的助手消息
            for i in range(last_message_index + 1, len(self.memory.messages)):
                if self.memory.messages[i].role == "assistant":
                    content = self.memory.messages[i].content
                    if content and isinstance(content, str):
                        # 过滤掉可能的工具调用部分，只保留实际文本
                        if "function_call" not in content.lower() and "tool:" not in content.lower():
                            model_output = content
                            break

        # 记录大模型的实际输出(如果找到)
        if model_output:
            logger.info(f"步骤 {self.current_step} 大模型文本输出(前200字符): {model_output[:200]}...")

        # 记录步骤结果(通常是工具输出)，避免打印过长内容
        if result:
            logger.info(f"步骤 {self.current_step} 执行结果(前200字符): {result[:200]}...")

        # 检查是否有标题建议
        if model_output and ("标题建议" in model_output or "视频标题" in model_output):
            # 提取标题建议
            self._extract_titles(model_output)

        # 放宽脚本保存条件，只要内容足够长，就认为可能是有价值的脚本内容
        if model_output and len(model_output) > 500:
            # 如果新结果更长，则替换之前的脚本
            if len(model_output) > len(self.final_script):
                self.final_script = model_output
                logger.info(f"保存了脚本内容，长度: {len(model_output)} 字符")
        elif result and len(result) > 500 and "planning" not in result.lower() and "execute" not in result.lower():
            # 备选：如果result不是规划日志且内容足够长
            if len(result) > len(self.final_script):
                self.final_script = result
                logger.info(f"从步骤结果中保存了脚本内容，长度: {len(result)} 字符")

        # 检查计划是否完成
        if self.active_plan_id:
            try:
                # 使用 get 命令获取计划详情
                plan_details = await self.available_tools.execute(
                    name="planning",
                    tool_input={
                        "command": "get",
                        "plan_id": self.active_plan_id
                    }
                )

                # 增强的计划完成检测逻辑
                import re
                if isinstance(plan_details, str):
                    # 检查方式1：通过正则表达式匹配进度
                    progress_match = re.search(r"Progress:\s+(\d+)/(\d+)\s+steps", plan_details)
                    if progress_match:
                        completed = int(progress_match.group(1))
                        total = int(progress_match.group(2))

                        # 如果全部步骤都已完成，或完成率超过90%且当前步骤数较多，停止Agent
                        if (completed == total and total > 0) or (completed/total > 0.9 and self.current_step > 10):
                            logger.info(f"检测到计划 '{self.active_plan_id}' 完成率 {completed}/{total}，将停止 Agent。")
                            # 主动调用Terminate工具确保退出
                            await self.available_tools.execute(name="terminate", tool_input={"status": "success"})
                            self.current_step = self.max_steps
                            return result

                    # 检查方式2：简单字符串检查
                    if "步骤已完成" in plan_details or "steps completed" in plan_details:
                        if "100.0%" in plan_details or "整理完整脚本" in plan_details and "completed" in plan_details:
                            logger.info(f"通过字符串匹配检测到计划已完成，将停止Agent。")
                            await self.available_tools.execute(name="terminate", tool_input={"status": "success"})
                            self.current_step = self.max_steps
                            return result

            except Exception as e:
                logger.warning(f"检查计划状态时出错: {str(e)}。安全起见，检查步骤计数。")
                # 添加安全检查：如果当前步骤已经超过预期的80%且已有脚本内容，考虑终止
                if self.current_step > int(self.max_steps * 0.8) and len(self.final_script) > 1000:
                    logger.info(f"已执行{self.current_step}/{self.max_steps}步且已生成足够长的脚本，可能接近完成，将终止Agent。")
                    await self.available_tools.execute(name="terminate", tool_input={"status": "completed"})
                    self.current_step = self.max_steps
                    return result

        return result

    def _extract_titles(self, text: str) -> None:
        """从文本中提取标题建议"""
        lines = text.split('\n')
        title_section = False
        title_lines = []

        for line in lines:
            if ("标题建议" in line or "视频标题" in line) and not title_section:
                title_section = True
                title_lines.append(line)
            elif title_section and (line.strip().startswith("-") or line.strip().startswith("•") or
                                    line.strip().startswith("*") or
                                    any(line.strip().startswith(f"{i}.") for i in range(1, 10))):
                title_lines.append(line)
            elif title_section and line.strip() and not line.strip().startswith("-") and not line.strip().startswith("•"):
                # 如果不是列表项但不是空行，可能已经离开了标题部分
                if not any(line.strip().startswith(f"{i}.") for i in range(1, 10)):
                    title_section = False

        # 提取标题
        for line in title_lines:
            line = line.strip()
            if line and (line.startswith("-") or line.startswith("•") or line.startswith("*") or
                        any(line.startswith(f"{i}.") for i in range(1, 10))):
                # 清理标题文本
                title = line.lstrip("-•* 0123456789.").strip()
                if title and title not in self.suggested_titles:
                    self.suggested_titles.append(title)

        logger.info(f"提取到{len(self.suggested_titles)}个标题建议")

    def _parse_args(self, tool_call) -> Dict[str, Any]:
        """从工具调用中解析参数"""
        import json
        try:
            if tool_call.function.arguments:
                return json.loads(tool_call.function.arguments)
        except:
            pass
        return {}

    def _extract_urls_from_search_results(self, search_results: str) -> List[str]:
        """从搜索结果中提取URL"""
        import re

        # 简单URL提取模式
        url_pattern = r'https?://[^\s"\')]+(?:\.[^\s"\')]+)+[^\s"\').]*'
        urls = re.findall(url_pattern, search_results)

        # 去重
        unique_urls = list(dict.fromkeys(urls))
        return unique_urls

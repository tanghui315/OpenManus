"""
Manim代码生成Agent模块

负责为视频脚本中的关键概念生成Manim动画代码
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

NEXT_STEP_PROMPT = """
请按照当前计划的下一步行动，为脚本中的关键概念生成Manim动画代码。
确保代码使用Manim社区版语法，结构良好且可独立运行。
"""


class ManimCoderAgent(PlanningAgent):
    """Manim动画代码生成Agent

    负责为技术教学视频的关键概念生成Manim动画代码
    """

    name: str = "manim_coder"
    description: str = "生成Manim动画代码"

    system_prompt: str = SYSTEM_PROMPT
    next_step_prompt: str = NEXT_STEP_PROMPT

    available_tools: ToolCollection = Field(
        default_factory=lambda: ToolCollection(
            WebSearch(), WebExtractTool(), StrReplaceEditor(), PlanningTool(), Terminate()
        )
    )

    # 使用AUTO，允许大模型自由回答或调用工具
    tool_choices: ToolChoice = ToolChoice.AUTO

    max_steps: int = 20  # 限制Agent的最大步骤数，从10增加到20
    collected_info: List[Dict[str, Any]] = Field(default_factory=list)
    final_code: str = ""

    async def run(self, request: Optional[str] = None) -> str:
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
            self.final_code = ""

            # 创建初始提示
            logger.info(f"开始为请求生成Manim代码: {request[:50] if request else ''}...")

            # 使用父类方法运行，它会调用create_initial_plan
            result = await super().run(request)

            # 如果没有明确的最终代码，尝试从最后的回复中提取
            if not self.final_code and result:
                cleaned_code = self._clean_code_response(result)
                if cleaned_code:
                    self.final_code = cleaned_code
                    logger.info(f"从最终结果中提取得到Manim代码，长度: {len(cleaned_code)}")

            # 如果仍然没有最终代码，尝试从记忆中提取
            if not self.final_code and len(self.memory.messages) > 0:
                # 从最近的助手消息中寻找代码
                for message in reversed(self.memory.messages):
                    if message.role == "assistant" and ("import manim" in message.content or "from manim import" in message.content):
                        cleaned_code = self._clean_code_response(message.content)
                        if cleaned_code:
                            self.final_code = cleaned_code
                            logger.info(f"从记忆中的消息提取得到Manim代码，长度: {len(cleaned_code)}")
                            break

            # 确保返回清理后的代码
            return self.final_code or result

        except Exception as e:
            logger.error(f"Manim代码生成过程中出错: {str(e)}")
            return f"Manim代码生成失败: {str(e)}"

    async def create_initial_plan(self, request: str) -> None:
        """创建初始Manim代码生成计划"""
        logger.info(f"为概念'{request[:30]}...'创建Manim代码生成计划")

        # 创建计划步骤
        plan_steps = [
            "分析需要可视化的概念和上下文",
            "搜索Manim相关资料和最佳实践",
            "设计场景结构和动画序列",
            "编写基础场景类和对象初始化",
            "实现主要对象和元素",
            "添加动画转场和效果",
            "增加文本说明和注释",
            "优化视觉效果和代码结构",
            "确保代码完整可运行",
            "添加详细代码注释"
        ]

        # 设置计划ID
        plan_id = f"manim_plan_{self.name}_{int(time.time())}"
        self.active_plan_id = plan_id

        # 创建请求消息
        plan_message = f"""
我需要创建一个Manim动画代码生成计划，用于可视化以下概念:
"{request}"

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
                    "title": f"Manim动画代码生成计划",
                    "description": f"为概念'{request[:50]}...'生成Manim可视化动画代码",
                    "steps": plan_steps
                }
            )
            logger.info(f"成功创建Manim代码生成计划: {result}")
        except Exception as e:
            logger.error(f"创建计划失败: {str(e)}")

    async def act(self) -> str:
        """执行当前步骤并处理结果"""
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

        # 记录大模型的实际输出(如果找到)，只记录前100字符
        if model_output:
            logger.info(f"步骤 {self.current_step} 大模型文本输出: {model_output[:100]}..." + (f"[共{len(model_output)}字符]" if len(model_output) > 100 else ""))

            # 检查结果是否包含代码
            if "import manim" in model_output or "from manim import" in model_output:
                cleaned_code = self._clean_code_response(model_output)
                if cleaned_code:
                    self.final_code = cleaned_code
                    logger.info(f"从模型输出中保存了Manim代码，长度: {len(cleaned_code)} 字符")

        # 记录步骤结果(通常是工具输出)，避免打印过长内容
        if result:
            # 检查是否为网页提取结果
            if "web_extract" in str(self.tool_calls) if self.tool_calls else False:
                logger.info(f"步骤 {self.current_step} web_extract工具执行完成，结果长度: {len(result)} 字符")
            elif len(result) > 200:
                # 对于其他长结果，仅打印前200字符
                logger.info(f"步骤 {self.current_step} 执行结果: {result[:200]}... [共{len(result)}字符]")
            else:
                logger.info(f"步骤 {self.current_step} 执行结果: {result}")

            # 也检查结果中的代码
            if "import manim" in result or "from manim import" in result:
                cleaned_code = self._clean_code_response(result)
                if cleaned_code:
                    self.final_code = cleaned_code
                    logger.info(f"从执行结果中保存了Manim代码，长度: {len(cleaned_code)} 字符")

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

                        # 如果全部步骤都已完成，或完成率超过90%且当前步骤数较多，停止 Agent
                        if (completed == total and total > 0) or (completed/total > 0.9 and self.current_step > 10):
                            logger.info(f"检测到计划 '{self.active_plan_id}' 完成率 {completed}/{total}，将停止 Agent。")
                            # 主动调用Terminate工具确保退出
                            await self.available_tools.execute(name="terminate", tool_input={"status": "success"})
                            self.current_step = self.max_steps
                            return result

                    # 检查方式2：简单字符串检查
                    if "步骤已完成" in plan_details or "steps completed" in plan_details:
                        if "100.0%" in plan_details or "10/10" in plan_details:
                            logger.info(f"通过字符串匹配检测到计划已完成，将停止Agent。")
                            await self.available_tools.execute(name="terminate", tool_input={"status": "success"})
                            self.current_step = self.max_steps
                            return result

            except Exception as e:
                logger.warning(f"检查计划状态时出错: {str(e)}。安全起见，检查步骤计数。")
                # 添加安全检查：如果当前步骤已经超过预期的80%且已有代码生成，考虑终止
                if self.current_step > int(self.max_steps * 0.8) and self.final_code:
                    logger.info(f"已执行{self.current_step}/{self.max_steps}步且已生成代码，可能接近完成，将终止Agent。")
                    await self.available_tools.execute(name="terminate", tool_input={"status": "completed"})
                    self.current_step = self.max_steps
                    return result

        return result

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

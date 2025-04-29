"""
用户交互工具
负责与用户交互并获取反馈，复用OpenManus的ask_human工具
"""

from typing import Any, Dict, List, Optional, Union

from app.logger import setup_logger
from app.tool.ask_human import AskHuman
from modules.doc_server.tools.base import DocServerTool

logger = setup_logger("doc_server.tools.ask_human")


class AskHumanTool(DocServerTool):
    """用户交互工具，用于向用户询问并获取反馈"""

    def initialize(self, **kwargs) -> None:
        """
        初始化工具

        Args:
            kwargs: 初始化参数
        """
        super().initialize(**kwargs)

        # 初始化OpenManus的AskHuman工具
        self.ask_human = AskHuman()

        logger.info("用户交互工具初始化完成")

    async def execute(
        self,
        inquire: str,
        options: Optional[List[str]] = None,
        timeout: Optional[int] = None,
        default_response: Optional[str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        执行用户交互

        Args:
            inquire: 向用户询问的问题
            options: 可选的选项列表
            timeout: 超时时间（秒）
            default_response: 超时时的默认回答
            kwargs: 其他参数

        Returns:
            用户反馈结果
        """
        try:
            # 构建完整问题
            full_inquire = inquire

            # 如果有选项，添加到问题中
            if options:
                options_text = "\n".join(
                    [f"{i+1}. {option}" for i, option in enumerate(options)]
                )
                full_inquire = (
                    f"{inquire}\n\n选项:\n{options_text}\n\n请输入选项编号或直接回复:"
                )

            # 调用OpenManus的AskHuman工具
            response = await self.ask_human.execute(inquire=full_inquire)

            # 处理超时情况
            if not response and default_response:
                logger.info(f"用户未在规定时间内回复，使用默认回答: {default_response}")
                response = default_response

            # 处理选项
            selected_option = None
            if options and response and response.isdigit():
                try:
                    option_index = int(response) - 1
                    if 0 <= option_index < len(options):
                        selected_option = options[option_index]
                except ValueError:
                    pass

            # 构建结果
            result = {
                "response": response,
                "inquire": inquire,
                "timestamp": None,  # 这里可以添加时间戳
            }

            # 如果选择了有效选项，添加到结果中
            if selected_option:
                result["selected_option"] = selected_option
                result["option_index"] = int(response) - 1

            logger.info(f"用户对问题 '{inquire}' 的回答: {response}")
            return result

        except Exception as e:
            error_msg = f"执行用户交互时发生错误: {str(e)}"
            logger.error(error_msg)
            if default_response:
                logger.info(f"使用默认回答: {default_response}")
                return {
                    "response": default_response,
                    "inquire": inquire,
                    "is_default": True,
                    "error": error_msg,
                }
            else:
                return {"response": None, "inquire": inquire, "error": error_msg}

from typing import List, Dict, Any, Optional
import json
import asyncio
import traceback  # 新增导入

from app.agent.browser import BrowserAgent
from app.rss_writer.agents.rss_filter import RSSFilterAgent
from app.rss_writer.agents.article_writer import ArticleWriterAgent
from app.schema import Message
from app.logger import logger


class RSSArticleWorkflow:
    """协调RSS阅读和文章撰写的工作流"""

    def __init__(self):
        """初始化工作流组件"""
        self.rss_filter = RSSFilterAgent()
        self.browser = BrowserAgent()
        self.article_writer = ArticleWriterAgent()

    async def run(self, rss_url: str) -> str:
        """
        执行完整的RSS文章撰写工作流

        Args:
            rss_url: RSS Feed的URL

        Returns:
            工作流执行结果，成功时为生成的文章，失败时为错误信息
        """
        try:
            logger.info(f"开始处理RSS源: {rss_url}")

            # 1. 获取并筛选RSS Feed中的文章
            logger.info("步骤1: 开始获取并筛选RSS feed中的文章")
            filter_result = await self.rss_filter.run(f"获取并评估这个RSS源中的文章: {rss_url}")
            logger.info(f"RSS筛选结果: {filter_result[:200]}..." if len(filter_result) > 200 else filter_result)

            # 检查筛选结果
            logger.debug(f"筛选后选定的文章数量: {len(self.rss_filter.selected_articles)}")
            for i, article in enumerate(self.rss_filter.selected_articles):
                logger.debug(f"选定文章 #{i}: 标题='{article.get('title', '未知标题')}', URL={article.get('url', '无URL')}")

            # 检查是否找到了有价值的文章
            if "没有找到有价值的文章" in filter_result or not self.rss_filter.selected_articles:
                logger.info("没有找到有价值的文章，工作流结束")
                return "没有找到可以撰写的有价值内容。"

            # 2. 收集选定文章的详细内容
            logger.info("步骤2: 开始收集选定文章的详细内容")
            collected_info = await self._collect_article_content()

            if not collected_info:
                logger.info("无法收集文章内容，工作流结束")
                return "无法获取选定文章的详细内容，无法继续撰写文章。"

            # 3. 撰写技术文章
            logger.info("步骤3: 开始撰写技术文章")
            write_request = "基于收集到的信息，撰写一篇详细的技术文章，包括引言、主体部分和结论。"
            article = await self.article_writer.run(write_request)
            logger.info(f"文章撰写完成，长度: {len(article)} 字符")

            return article

        except Exception as e:
            # 增加更详细的错误日志
            error_details = traceback.format_exc()
            logger.error(f"工作流执行出错: {str(e)}")
            logger.error(f"详细错误堆栈: {error_details}")
            return f"工作流执行失败: {str(e)}\n\n详细错误: {error_details[:500]}..."

    async def _collect_article_content(self) -> bool:
        """
        收集选定文章的详细内容

        Returns:
            是否成功收集到有效信息
        """
        # 确保有选定的文章
        if not self.rss_filter.selected_articles:
            logger.warning("没有选定的文章，无法收集内容")
            return False

        success_count = 0

        # 依次访问每篇选定的文章
        for i, article in enumerate(self.rss_filter.selected_articles):
            title = article.get("title", "未知标题")
            url = article.get("url", "")

            if not url:
                logger.warning(f"文章 #{i} 没有URL，跳过")
                continue

            logger.info(f"访问文章 #{i}: {title} - {url}")

            try:
                # 使用浏览器访问文章并提取内容
                browser_prompt = f"访问这个URL: {url}，并提取关键的技术信息、见解和重要细节。"
                await self.browser.run(browser_prompt)

                # 收集最后的浏览器结果
                extracted_content = self._get_last_assistant_message(self.browser.memory.messages)

                # 记录提取结果
                content_preview = extracted_content[:100] + "..." if extracted_content and len(extracted_content) > 100 else extracted_content
                logger.debug(f"文章 #{i} 提取内容: {content_preview}")

                if extracted_content:
                    # 将提取的内容添加到文章撰写Agent的收集信息中
                    self.article_writer.add_information(
                        source=title,
                        content=extracted_content,
                        url=url
                    )
                    success_count += 1
                    logger.info(f"成功收集文章 #{i} '{title}' 的内容")
                else:
                    logger.warning(f"未能从文章 #{i} '{title}' 提取有效内容")
            except Exception as e:
                logger.error(f"访问文章 #{i} '{title}' 时出错: {str(e)}")
                # 继续处理下一篇文章

        # 汇总收集结果
        logger.info(f"总共选定 {len(self.rss_filter.selected_articles)} 篇文章，成功收集 {success_count} 篇")

        # 至少成功收集了一篇文章的内容
        return success_count > 0

    @staticmethod
    def _get_last_assistant_message(messages: List[Message]) -> str:
        """
        从消息列表中获取最后一条助手消息的内容

        Args:
            messages: 消息列表

        Returns:
            最后一条助手消息的内容，如果没有则返回空字符串
        """
        for msg in reversed(messages):
            if msg.role == "assistant" and msg.content:
                logger.debug(f"找到最后一条assistant消息: 长度={len(msg.content)}")
                return msg.content

        logger.warning("未找到任何assistant消息")
        return ""

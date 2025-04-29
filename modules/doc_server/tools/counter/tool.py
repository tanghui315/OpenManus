"""
计数工具
用于计算文档、章节、字数等统计信息
"""

import re
from typing import Any, Dict, List, Optional, Tuple

from app.logger import setup_logger
from modules.doc_server.database.document import DocumentStorage
from modules.doc_server.tools.base import DocServerTool
from modules.doc_server.tools.counter.model import CountResult, CountStats

logger = setup_logger("doc_server.tools.counter")


class CounterTool(DocServerTool):
    """计数工具，用于统计文档字数、段落数等信息"""

    def initialize(self, **kwargs) -> None:
        """
        初始化工具

        Args:
            kwargs: 初始化参数
        """
        super().initialize(**kwargs)

        # 初始化文档存储
        self.storage = DocumentStorage()

        # 配置每分钟平均阅读字数（中文）
        self.words_per_minute = kwargs.get("words_per_minute", 300)

        # 中文单词分割正则表达式
        self.word_regex = re.compile(r"[\u4e00-\u9fff]|[a-zA-Z]+")

        # 中文句子分割正则表达式
        self.sentence_regex = re.compile(r"[^!?。；！？.;]+[!?。；！？.;]?")

        # 段落分割正则表达式
        self.paragraph_regex = re.compile(r"\n\s*\n")

        logger.info("计数工具初始化完成")

    async def execute(
        self,
        text: Optional[str] = None,
        document_id: Optional[str] = None,
        count_type: str = "words",
        include_spaces: bool = False,
        include_punctuation: bool = True,
        **kwargs,
    ) -> CountResult:
        """
        执行计数统计

        Args:
            text: 要计算的文本内容
            document_id: 文档ID
            count_type: 计数类型
            include_spaces: 是否包含空格
            include_punctuation: 是否包含标点符号
            kwargs: 其他参数

        Returns:
            计数结果
        """
        if not text and not document_id:
            return CountResult(
                success=False, count_type=count_type, error="必须提供文本内容或文档ID"
            )

        try:
            # 确定计数来源
            source = "text" if text else "document"
            content = text

            # 如果是文档ID，获取文档内容
            if document_id:
                document = await self.storage.get_document(document_id)
                if not document:
                    return CountResult(
                        success=False,
                        count_type=count_type,
                        document_id=document_id,
                        error=f"文档不存在: {document_id}",
                    )

                # 获取文档内容
                content = document.get("content", "")

                # 获取文档块
                chunks = document.get("chunks", [])

                # 如果没有主文档内容但有文档块，合并块内容
                if not content and chunks:
                    content = "\n\n".join(
                        [chunk.get("content", "") for chunk in chunks]
                    )

                # 准备章节统计
                section_stats = {}
                if chunks:
                    for chunk in chunks:
                        section_title = chunk.get("section_title", "未命名章节")
                        section_content = chunk.get("content", "")
                        word_count = self._count_words(section_content)
                        section_stats[section_title] = word_count

            # 如果仍然没有内容，返回错误
            if not content:
                return CountResult(
                    success=False,
                    count_type=count_type,
                    document_id=document_id,
                    error="文档内容为空",
                )

            # 执行计数
            stats = self._calculate_stats(content, include_spaces, include_punctuation)

            # 根据计数类型确定主计数结果
            count = 0
            if count_type == "words":
                count = stats.words
            elif count_type == "chars":
                count = stats.chars if include_spaces else stats.chars_no_spaces
            elif count_type == "paragraphs":
                count = stats.paragraphs
            elif count_type == "sections":
                count = stats.sections
            elif count_type == "sentences":
                count = stats.sentences
            else:
                count = stats.words  # 默认为单词计数

            # 创建预览（最多前100个字符）
            preview = content[:100] + ("..." if len(content) > 100 else "")

            # 返回结果
            result = CountResult(
                success=True,
                count_type=count_type,
                count=count,
                stats=stats,
                source=source,
                text_preview=preview,
            )

            # 添加文档特有字段
            if document_id:
                result.document_id = document_id
                result.section_stats = (
                    section_stats if "section_stats" in locals() else None
                )

            return result

        except Exception as e:
            error_msg = f"执行计数统计时发生错误: {str(e)}"
            logger.error(error_msg)
            return CountResult(success=False, count_type=count_type, error=error_msg)

    def _calculate_stats(
        self, text: str, include_spaces: bool = False, include_punctuation: bool = True
    ) -> CountStats:
        """
        计算统计数据

        Args:
            text: 要计算的文本
            include_spaces: 是否包含空格
            include_punctuation: 是否包含标点符号

        Returns:
            统计结果
        """
        if not text:
            return CountStats()

        # 计算字符数
        chars = len(text)

        # 计算不包含空格的字符数
        chars_no_spaces = len(text.replace(" ", "").replace("\t", "").replace("\n", ""))

        # 计算单词数
        words = self._count_words(text, include_punctuation)

        # 计算段落数
        paragraphs = (
            len(self.paragraph_regex.split(text.strip())) if text.strip() else 0
        )

        # 估计章节数（根据标题标记判断）
        sections = self._count_sections(text)

        # 计算句子数
        sentences = len(self.sentence_regex.findall(text))

        # 计算阅读时间（分钟）
        reading_time = words / self.words_per_minute if self.words_per_minute > 0 else 0

        return CountStats(
            words=words,
            chars=chars,
            chars_no_spaces=chars_no_spaces,
            paragraphs=paragraphs,
            sections=sections,
            sentences=sentences,
            reading_time=reading_time,
        )

    def _count_words(self, text: str, include_punctuation: bool = True) -> int:
        """
        计算单词数

        Args:
            text: 要计算的文本
            include_punctuation: 是否包含标点符号

        Returns:
            单词数
        """
        if not text:
            return 0

        # 如果不包含标点，先去除标点
        if not include_punctuation:
            text = re.sub(r"[^\w\s\u4e00-\u9fff]", "", text)

        # 中文计算方式：汉字和西文单词都算作一个词
        words = self.word_regex.findall(text)
        return len(words)

    def _count_sections(self, text: str) -> int:
        """
        估计章节数

        Args:
            text: 要计算的文本

        Returns:
            章节数
        """
        if not text:
            return 0

        # 使用标题标记来估计章节数
        # 匹配常见的标题格式，如 "第一章"、"# 标题"、"1. 标题" 等
        section_patterns = [
            r"第[一二三四五六七八九十\d]+章",  # 第X章
            r"#+\s+\S+",  # Markdown 标题
            r"\d+[.、]\s+\S+",  # 数字标题
        ]

        sections = 0
        for pattern in section_patterns:
            sections += len(re.findall(pattern, text))

        # 如果没检测到章节，则返回1（视为单章节）
        return max(1, sections)

"""
网页内容提取工具

此模块提供了从网页中提取主要文本内容的功能，可以过滤掉广告、
导航栏等无关内容，只保留文章主体。
"""
import os
import re
import logging
from typing import Dict, Optional, Tuple, List, Any
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from app.logger import logger


class WebContentExtractor:
    """
    网页内容提取器
    用于从网页中提取主要文本内容，过滤掉广告、导航栏等无关内容
    """

    def __init__(self, use_proxy: bool = True):
        """
        初始化网页内容提取器

        Args:
            use_proxy: 是否使用环境变量中设置的代理
        """
        self.use_proxy = use_proxy
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'
        }

    def _get_proxies(self) -> Dict[str, str]:
        """获取环境变量中设置的代理配置"""
        if not self.use_proxy:
            return {}

        proxies = {}
        if 'HTTP_PROXY' in os.environ:
            proxies['http'] = os.environ['HTTP_PROXY']
        if 'HTTPS_PROXY' in os.environ:
            proxies['https'] = os.environ['HTTPS_PROXY']

        return proxies

    def extract_content(self, url: str, timeout: int = 30) -> Tuple[str, Dict[str, Any]]:
        """
        从网页中提取主要文本内容

        Args:
            url: 网页URL
            timeout: 请求超时时间(秒)

        Returns:
            提取的文本内容和元数据的元组

        Raises:
            ValueError: URL格式不正确
            requests.RequestException: 请求失败
        """
        logger.info(f"开始提取网页内容: {url}")

        # 验证URL格式
        parsed_url = urlparse(url)
        if not all([parsed_url.scheme, parsed_url.netloc]):
            raise ValueError(f"无效的URL: {url}")

        # 获取代理设置
        proxies = self._get_proxies()
        proxy_info = list(proxies.values())[0] if proxies else "未使用代理"
        logger.debug(f"使用代理: {proxy_info}")

        try:
            # 获取网页内容
            logger.debug(f"发送HTTP请求: {url}")
            response = requests.get(
                url,
                headers=self.headers,
                proxies=proxies if proxies else None,
                timeout=timeout
            )
            response.raise_for_status()

            # 获取网页元数据
            metadata = {
                'url': url,
                'status_code': response.status_code,
                'content_type': response.headers.get('Content-Type', ''),
                'encoding': response.encoding,
            }

            # 解析HTML
            logger.debug("解析HTML内容")
            soup = BeautifulSoup(response.text, 'html.parser')

            # 提取标题
            title = self._extract_title(soup)
            metadata['title'] = title

            # 提取主要内容
            main_content, content_source = self._extract_main_content(soup)
            metadata['content_source'] = content_source

            logger.info(f"成功提取网页内容，标题: {title}，内容长度: {len(main_content)} 字符")
            return main_content, metadata

        except requests.RequestException as e:
            logger.error(f"请求失败: {str(e)}")
            raise

    def _extract_title(self, soup: BeautifulSoup) -> str:
        """从页面中提取标题"""
        # 尝试获取title标签内容
        if soup.title:
            return soup.title.string.strip()

        # 尝试获取h1标签内容
        h1 = soup.find('h1')
        if h1:
            return h1.get_text(strip=True)

        # 回退使用URL作为标题
        return "未找到标题"

    def _extract_main_content(self, soup: BeautifulSoup) -> Tuple[str, str]:
        """
        提取页面的主要内容

        Args:
            soup: BeautifulSoup对象

        Returns:
            提取的文本内容和来源(例如'main', 'article', 'body')的元组
        """
        # 首先尝试查找main标签
        main_content = soup.find('main')
        if main_content:
            return self._clean_content(main_content), 'main'

        # 尝试article标签
        article = soup.find('article')
        if article:
            return self._clean_content(article), 'article'

        # 尝试带有常见内容类名的div
        content_div = soup.find('div', class_=re.compile(r'content|article|post|main', re.I))
        if content_div:
            return self._clean_content(content_div), 'div.content'

        # 回退到body
        if soup.body:
            return self._clean_content(soup.body), 'body'

        return "未能提取到有效内容", 'none'

    def _clean_content(self, element: BeautifulSoup) -> str:
        """
        清理内容元素，移除无关元素和格式化文本

        Args:
            element: BeautifulSoup元素

        Returns:
            清理后的文本内容
        """
        # 创建一个元素的副本，避免修改原始元素
        content = element.__copy__()

        # 移除可能干扰的标签
        noise_selectors = [
            'script', 'style', 'nav', 'footer', 'header', 'aside', 'iframe',
            '[class*="ad"]', '[class*="banner"]', '[id*="ad"]', '[id*="banner"]',
            'form', '.comments', '#comments', '.sidebar', '.menu', '.navigation',
            '.share', '.social', '.related', '.recommended'
        ]

        # 获取所有需要移除的元素
        for selector in noise_selectors:
            try:
                for tag in content.select(selector):
                    tag.extract()
            except Exception:
                # 忽略无效选择器
                pass

        # 获取清理后的文本
        text = content.get_text(separator='\n', strip=True)

        # 清理文本（移除多余空白等）
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        cleaned_text = '\n'.join(lines)

        # 限制内容长度
        max_length = 50000
        if len(cleaned_text) > max_length:
            cleaned_text = cleaned_text[:max_length] + "... [内容过长，已截断]"

        return cleaned_text

    def format_content_summary(self, content: str, metadata: Dict[str, Any]) -> str:
        """
        格式化内容摘要，用于Agent使用

        Args:
            content: 提取的内容
            metadata: 元数据

        Returns:
            格式化的内容摘要
        """
        title = metadata.get('title', '未知标题')
        url = metadata.get('url', '未知来源')

        content_summary = (
            f"## 文章内容摘要\n\n"
            f"**标题**: {title}\n"
            f"**来源**: {url}\n\n"
            f"### 提取的主要内容\n\n{content}"
        )

        return content_summary

"""
网页内容提取工具模块

提供网页内容提取功能，支持从URL缓存读取内容
"""

import os
import hashlib
import json
from typing import Dict, Any, Tuple, Optional
from datetime import datetime
import logging

from app.tool.web_extract import WebContentExtractor
from app.logger import logger

class WebExtractTool:
    """网页内容提取工具，支持本地缓存"""

    name: str = "web_extract"
    description: str = "从URL中提取主要文本内容，过滤广告等干扰内容，支持本地缓存"
    parameters: dict = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "要提取内容的网页URL"
            },
            "timeout": {
                "type": "integer",
                "description": "请求超时时间(秒)，默认为30",
                "default": 30
            },
            "use_cache": {
                "type": "boolean",
                "description": "是否使用缓存，默认为True",
                "default": True
            }
        },
        "required": ["url"]
    }

    def __init__(self, cache_dir: str = None):
        """初始化网页内容提取工具

        Args:
            cache_dir: 缓存目录路径，默认为 ./outputs/cache/web_extract
        """
        self.extractor = WebContentExtractor()

        # 设置缓存目录
        self.cache_dir = cache_dir or os.path.join("outputs", "cache", "web_extract")
        self._ensure_cache_dir()

        logger.info(f"WebExtractTool初始化完成，缓存目录: {self.cache_dir}")

    def _ensure_cache_dir(self) -> None:
        """确保缓存目录存在"""
        if not os.path.exists(self.cache_dir):
            os.makedirs(self.cache_dir, exist_ok=True)
            logger.info(f"创建网页内容缓存目录: {self.cache_dir}")

    def _get_url_hash(self, url: str) -> str:
        """根据URL生成唯一的哈希值作为文件名

        Args:
            url: 网页URL

        Returns:
            URL的哈希值
        """
        # 使用md5哈希算法生成URL的哈希值
        url_hash = hashlib.md5(url.encode('utf-8')).hexdigest()
        return url_hash

    def _get_cache_path(self, url: str) -> str:
        """获取URL对应的缓存文件路径

        Args:
            url: 网页URL

        Returns:
            缓存文件的完整路径
        """
        url_hash = self._get_url_hash(url)
        return os.path.join(self.cache_dir, f"{url_hash}.json")

    def _check_cache(self, url: str) -> Optional[Dict[str, Any]]:
        """检查URL是否有缓存，有则返回缓存内容

        Args:
            url: 网页URL

        Returns:
            缓存的内容字典，如果没有缓存则返回None
        """
        cache_path = self._get_cache_path(url)

        if not os.path.exists(cache_path):
            return None

        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
                logger.info(f"从缓存加载URL内容: {url[:50]}...")
                return cache_data
        except Exception as e:
            logger.warning(f"读取缓存失败: {str(e)}，将重新提取内容")
            return None

    def _save_to_cache(self, url: str, content: str, metadata: Dict[str, Any]) -> None:
        """将提取的内容保存到缓存

        Args:
            url: 网页URL
            content: 提取的文本内容
            metadata: 元数据字典
        """
        cache_path = self._get_cache_path(url)

        try:
            cache_data = {
                "url": url,
                "content": content,
                "metadata": metadata,
                "cached_at": datetime.now().isoformat()
            }

            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=2)

            logger.info(f"已将URL内容缓存到: {cache_path}")
        except Exception as e:
            logger.warning(f"保存缓存失败: {str(e)}")

    async def execute(self, url: str, timeout: int = 30, use_cache: bool = True) -> str:
        """执行网页内容提取，支持缓存

        Args:
            url: 要提取内容的网页URL
            timeout: 请求超时时间(秒)，默认为30
            use_cache: 是否使用缓存，默认为True

        Returns:
            提取的网页内容摘要
        """
        # 确保缓存目录存在
        self._ensure_cache_dir()

        # 检查是否有缓存
        if use_cache:
            cache_data = self._check_cache(url)
            if cache_data:
                cached_time = cache_data.get("cached_at", "未知时间")
                cached_content = cache_data.get("content", "")
                cached_metadata = cache_data.get("metadata", {})

                if cached_content:
                    logger.info(f"使用缓存内容，缓存时间: {cached_time}，内容长度: {len(cached_content)} 字符")
                    return self.extractor.format_content_summary(cached_content, cached_metadata)

        # 没有缓存或不使用缓存，执行提取
        try:
            logger.info(f"从网络提取URL内容: {url[:50]}...")
            content, metadata = self.extractor.extract_content(url, timeout)

            # 记录内容长度而不是内容本身
            logger.info(f"成功提取内容，长度: {len(content)} 字符，标题: {metadata.get('title', '无标题')[:50]}")

            # 保存到缓存
            if use_cache:
                self._save_to_cache(url, content, metadata)

            return self.extractor.format_content_summary(content, metadata)
        except Exception as e:
            error_msg = f"提取内容失败: {str(e)}"
            logger.error(error_msg)
            return error_msg

    # 将对象设为可调用
    async def __call__(self, **kwargs) -> str:
        """使对象可调用，转发到 execute 方法"""
        url = kwargs.get("url")
        timeout = kwargs.get("timeout", 30)
        use_cache = kwargs.get("use_cache", True)

        if not url:
            return "错误: 必须提供URL参数"

        return await self.execute(url=url, timeout=timeout, use_cache=use_cache)

    def to_param(self) -> dict:
        """返回符合 OpenAI API 格式的工具定义"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters
            }
        }

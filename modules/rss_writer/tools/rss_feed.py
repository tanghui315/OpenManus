import json
import aiohttp
import feedparser
from typing import Dict, List, Optional
import os

from app.tool.base import BaseTool, ToolResult


class RSSFeedTool(BaseTool):
    """读取并解析RSS feed的工具"""

    name: str = "rss_feed"
    description: str = "读取并解析RSS feed，返回文章列表"
    parameters: dict = {
        "type": "object",
        "properties": {
            "feed_url": {
                "type": "string",
                "description": "RSS feed的URL地址",
            },
            "max_entries": {
                "type": "integer",
                "description": "返回的最大条目数，默认为10",
            },
        },
        "required": ["feed_url"],
    }

    async def execute(self, feed_url: str, max_entries: int = 20) -> ToolResult:
        """
        读取并解析RSS feed

        Args:
            feed_url: RSS feed的URL地址
            max_entries: 返回的最大条目数，默认为10

        Returns:
            包含解析结果的ToolResult对象
        """
        try:
            # 从环境变量读取代理设置 (例如: export HTTP_PROXY="http://user:pass@host:port")
            proxy_url = os.environ.get("HTTP_PROXY") or os.environ.get("HTTPS_PROXY")

            # 设置请求头，模拟正常浏览器访问
            headers = {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
                "Accept-Encoding": "gzip, deflate, br",
                "Connection": "keep-alive"
            }

            # 特殊处理Reddit的URL
            if "reddit.com" in feed_url:
                # Reddit对请求更加敏感，需要额外headers
                headers["Referer"] = "https://www.reddit.com/"

            #     # 如果是未认证访问，尝试修改URL使用.json而非.rss
            #     if feed_url.endswith(".rss"):
            #         feed_url = feed_url.replace(".rss", ".json")

            # 使用aiohttp异步获取RSS内容
            async with aiohttp.ClientSession() as session:
                # 在 get 请求中加入 proxy 参数和headers
                async with session.get(feed_url, proxy=proxy_url, headers=headers) as response:
                    if response.status != 200:
                        return ToolResult(
                            error=f"获取RSS feed失败: HTTP状态码 {response.status}, URL: {feed_url}"
                        )

                    content = await response.text()

            # 检查是否为JSON格式（Reddit特殊处理）
            if feed_url.endswith(".json"):
                try:
                    json_data = json.loads(content)
                    # 手动构建类似feedparser的结构
                    feed = type('obj', (object,), {
                        'feed': type('obj', (object,), {'title': 'Reddit Feed', 'link': feed_url}),
                        'entries': []
                    })

                    # 从Reddit JSON提取数据
                    posts = json_data.get('data', {}).get('children', [])
                    for post in posts:
                        post_data = post.get('data', {})
                        entry = type('obj', (object,), {
                            'title': post_data.get('title', 'No Title'),
                            'link': f"https://www.reddit.com{post_data.get('permalink', '')}",
                            'summary': post_data.get('selftext', post_data.get('url', '')),
                            'published': post_data.get('created_utc', ''),
                            'id': post_data.get('id', '')
                        })
                        feed.entries.append(entry)
                except json.JSONDecodeError:
                    # 如果JSON解析失败，回退到默认处理
                    feed = feedparser.parse(content)
            else:
                # 使用feedparser解析RSS内容
                feed = feedparser.parse(content)

            if not feed.entries:
                return ToolResult(output="RSS feed中没有找到条目")

            entries = []

            # 提取文章信息
            for entry in feed.entries[:max_entries]:
                entry_data = {
                    "title": entry.title if hasattr(entry, "title") else "无标题",
                    "link": entry.link if hasattr(entry, "link") else "",
                    "summary": entry.summary if hasattr(entry, "summary") else "",
                    "published": entry.published if hasattr(entry, "published") else "",
                    "id": entry.id if hasattr(entry, "id") else ""
                }

                entries.append(entry_data)

            # 将结果格式化为JSON字符串返回
            result = {
                "feed_title": feed.feed.title if hasattr(feed.feed, "title") else "未知Feed",
                "feed_link": feed.feed.link if hasattr(feed.feed, "link") else "",
                "entries": entries
            }

            return ToolResult(output=json.dumps(result, ensure_ascii=False, indent=2))

        except Exception as e:
            # 可以在这里增加更详细的代理错误日志
            if proxy_url and isinstance(e, aiohttp.ClientConnectorError):
                 return ToolResult(error=f"RSS解析错误 (可能与代理 {proxy_url} 相关): {str(e)}")
            return ToolResult(error=f"RSS解析错误: {str(e)}")

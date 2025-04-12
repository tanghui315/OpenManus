"""
WebExtractTool测试脚本

用于测试网页内容提取工具的缓存功能
"""

import asyncio
import argparse
import sys
import os
from datetime import datetime

# 添加项目根目录到路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../')))

from app.video_script.tools import WebExtractTool
from app.logger import logger

async def test_web_extract_tool():
    """测试WebExtractTool的功能，包括缓存机制"""
    # 解析命令行参数
    parser = argparse.ArgumentParser(description="测试WebExtractTool的缓存功能")
    parser.add_argument("url", help="要提取内容的网页URL")
    parser.add_argument("--no-cache", action="store_true", help="不使用缓存")
    parser.add_argument("--clear-cache", action="store_true", help="清除此URL的缓存后重新提取")
    parser.add_argument("--cache-dir", default=None, help="自定义缓存目录")

    args = parser.parse_args()

    # 初始化工具
    extractor = WebExtractTool(cache_dir=args.cache_dir)

    # 记录开始时间
    start_time = datetime.now()

    # 如果需要清除缓存
    if args.clear_cache:
        cache_path = extractor._get_cache_path(args.url)
        if os.path.exists(cache_path):
            os.remove(cache_path)
            print(f"已清除URL缓存: {cache_path}")

    # 提取内容
    use_cache = not args.no_cache
    print(f"开始提取URL内容: {args.url}")
    print(f"是否使用缓存: {'是' if use_cache else '否'}")

    content = await extractor.execute(args.url, use_cache=use_cache)

    # 计算耗时
    elapsed = (datetime.now() - start_time).total_seconds()

    # 输出结果
    print("\n" + "="*50)
    print(f"内容提取完成! 耗时: {elapsed:.2f}秒")
    print("="*50)
    print(f"内容长度: {len(content)} 字符")
    print("="*50)
    print(content[:500] + "..." if len(content) > 500 else content)
    print("="*50)

    # 输出缓存信息
    cache_path = extractor._get_cache_path(args.url)
    if os.path.exists(cache_path):
        cache_size = os.path.getsize(cache_path) / 1024  # KB
        print(f"缓存文件: {cache_path}")
        print(f"缓存大小: {cache_size:.2f} KB")

if __name__ == "__main__":
    asyncio.run(test_web_extract_tool())

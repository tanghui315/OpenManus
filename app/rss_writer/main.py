import asyncio
import argparse
import os
import sys
import json
from typing import Optional, Any

from app.rss_writer.workflow import RSSArticleWorkflow
from app.logger import logger


def print_message_details(msg_obj: Any) -> str:
    """
    打印消息的详细信息

    Args:
        msg_obj: 消息对象（通常是Message实例或dict）

    Returns:
        格式化的消息详情字符串
    """
    try:
        from pydantic import BaseModel

        if isinstance(msg_obj, BaseModel):
            # Pydantic v2 使用 model_dump，v1 使用 dict()
            msg_dict = msg_obj.model_dump() if hasattr(msg_obj, 'model_dump') else msg_obj.dict()
        else:
            msg_dict = msg_obj

        # 确保只打印关键字段，避免过多输出
        filtered_dict = {k: v for k, v in msg_dict.items()
                        if k in ['role', 'content', 'tool_call_id', 'name', 'function']}

        return json.dumps(filtered_dict, ensure_ascii=False, indent=2)
    except Exception as e:
        return f"消息格式化错误: {str(e)}"


async def main(rss_url: str, output_file: Optional[str] = None) -> None:
    """
    主程序入口，执行RSS文章生成工作流

    Args:
        rss_url: RSS Feed的URL
        output_file: 可选的输出文件路径，如果提供则将结果写入文件
    """
    logger.info(f"开始执行RSS文章生成工作流，RSS源: {rss_url}")

    # 设置代理环境变量
    logger.info("设置代理环境变量")
    os.environ['HTTP_PROXY'] = 'http://127.0.0.1:7890'
    os.environ['HTTPS_PROXY'] = 'http://127.0.0.1:7890'
    os.environ['http_proxy'] = 'http://127.0.0.1:7890'
    os.environ['https_proxy'] = 'http://127.0.0.1:7890'

    try:
        # 初始化工作流
        logger.info("初始化RSSArticleWorkflow")
        workflow = RSSArticleWorkflow()

        # 运行工作流
        logger.info(f"开始执行工作流，处理RSS源: {rss_url}")
        result = await workflow.run(rss_url)
        logger.info("工作流执行完成")

        # 处理结果
        if output_file:
            # 写入到文件
            try:
                logger.info(f"正在将结果写入文件: {output_file}")
                with open(output_file, "w", encoding="utf-8") as f:
                    f.write(result)
                logger.info(f"结果已成功写入文件: {output_file}")
            except Exception as e:
                logger.error(f"写入文件失败: {str(e)}")
                print(f"写入文件失败: {str(e)}")
        else:
            # 直接输出到控制台
            logger.info("将结果输出到控制台")
            print("\n" + "="*50 + "\n")
            print(result)
            print("\n" + "="*50 + "\n")

        logger.info("程序执行完成")
        return result
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        logger.error(f"主程序执行出错: {str(e)}")
        logger.error(f"详细错误堆栈: {error_details}")
        print(f"程序执行出错: {str(e)}")
        return f"程序执行失败: {str(e)}"


def run_cli():
    """处理命令行参数并运行程序"""
    parser = argparse.ArgumentParser(description="根据RSS Feed生成技术文章")
    parser.add_argument("rss_url", help="RSS Feed的URL地址")
    parser.add_argument("-o", "--output", help="输出文件的路径")
    parser.add_argument("--debug", action="store_true", help="启用详细调试日志")

    args = parser.parse_args()

    # 设置日志级别
    if args.debug:
        import logging
        logger.setLevel(logging.DEBUG)
        logger.debug("已启用DEBUG日志级别")

    try:
        asyncio.run(main(args.rss_url, args.output))
    except KeyboardInterrupt:
        print("\n程序被用户中断")
        logger.info("程序被用户中断")
        sys.exit(1)
    except Exception as e:
        print(f"程序执行出错: {str(e)}")
        logger.error(f"程序执行出错: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    run_cli()

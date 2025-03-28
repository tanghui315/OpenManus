import asyncio
import argparse
import sys
from typing import Optional

from app.rss_writer.workflow import RSSArticleWorkflow
from app.logger import logger


async def main(rss_url: str, output_file: Optional[str] = None) -> None:
    """
    主程序入口，执行RSS文章生成工作流

    Args:
        rss_url: RSS Feed的URL
        output_file: 可选的输出文件路径，如果提供则将结果写入文件
    """
    logger.info(f"开始执行RSS文章生成工作流，RSS源: {rss_url}")

    # 初始化工作流
    workflow = RSSArticleWorkflow()

    # 运行工作流
    result = await workflow.run(rss_url)

    # 处理结果
    if output_file:
        # 写入到文件
        try:
            with open(output_file, "w", encoding="utf-8") as f:
                f.write(result)
            logger.info(f"结果已写入文件: {output_file}")
        except Exception as e:
            logger.error(f"写入文件失败: {str(e)}")
            print(f"写入文件失败: {str(e)}")
    else:
        # 直接输出到控制台
        print("\n" + "="*50 + "\n")
        print(result)
        print("\n" + "="*50 + "\n")

    logger.info("工作流执行完成")


def run_cli():
    """处理命令行参数并运行程序"""
    parser = argparse.ArgumentParser(description="根据RSS Feed生成技术文章")
    parser.add_argument("rss_url", help="RSS Feed的URL地址")
    parser.add_argument("-o", "--output", help="输出文件的路径")

    args = parser.parse_args()

    try:
        asyncio.run(main(args.rss_url, args.output))
    except KeyboardInterrupt:
        print("\n程序被用户中断")
        sys.exit(1)
    except Exception as e:
        print(f"程序执行出错: {str(e)}")
        logger.error(f"程序执行出错: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    run_cli()

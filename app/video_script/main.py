"""
视频脚本生成器主入口模块

提供命令行接口，用于生成视频脚本和Manim动画代码
"""

import argparse
import asyncio
import json
import os
from pathlib import Path

from app.logger import logger
from app.video_script.workflow import VideoScriptWorkflow


async def main():
    """视频脚本生成器主入口函数"""
    # 解析命令行参数
    parser = argparse.ArgumentParser(description="AI技术视频脚本生成器")
    parser.add_argument("keyword", help="技术关键字，如'区块链'、'支持向量机'等")
    parser.add_argument("--audience", choices=["beginner", "intermediate", "advanced"],
                       default="beginner", help="目标受众水平，默认为beginner")
    parser.add_argument("--output-dir", default="./outputs", help="输出目录，默认为./outputs")
    parser.add_argument("--output-format", choices=["md", "txt", "json"],
                       default="md", help="输出格式，默认为Markdown")

    args = parser.parse_args()

    # 确保输出目录存在
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # 创建输出文件名
    slug = args.keyword.lower().replace(" ", "_").replace("-", "_")
    timestamp = asyncio.get_event_loop().time()
    base_filename = f"{slug}_{args.audience}_{int(timestamp)}"

    try:
        # 初始化工作流并执行脚本生成
        logger.info(f"开始为关键字 '{args.keyword}' 生成视频脚本")
        workflow = VideoScriptWorkflow()
        result = await workflow.generate_script(args.keyword, args.audience)

        # 准备输出
        if args.output_format == "md":
            # Markdown格式输出
            md_content = generate_markdown_output(result)
            output_file = output_dir / f"{base_filename}.md"
            with open(output_file, "w", encoding="utf-8") as f:
                f.write(md_content)

            # 同时创建单独的Manim代码文件
            manim_dir = output_dir / f"{base_filename}_manim_code"
            manim_dir.mkdir(exist_ok=True)

            for i, block in enumerate(result["manim_code_blocks"], 1):
                code_file = manim_dir / f"scene_{i}_{block['description'].replace(' ', '_')[:30]}.py"
                with open(code_file, "w", encoding="utf-8") as f:
                    f.write(block["code"])

            logger.info(f"已生成Markdown脚本: {output_file}")
            logger.info(f"Manim代码保存在: {manim_dir}")

        elif args.output_format == "txt":
            # 纯文本格式输出
            txt_content = generate_text_output(result)
            output_file = output_dir / f"{base_filename}.txt"
            with open(output_file, "w", encoding="utf-8") as f:
                f.write(txt_content)

            logger.info(f"已生成文本脚本: {output_file}")

        elif args.output_format == "json":
            # JSON格式输出
            output_file = output_dir / f"{base_filename}.json"
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)

            logger.info(f"已生成JSON数据: {output_file}")

        logger.info("脚本生成完成!")
        return 0

    except Exception as e:
        logger.error(f"脚本生成失败: {str(e)}")
        return 1


def generate_markdown_output(result: dict) -> str:
    """生成Markdown格式的输出"""
    md_lines = []

    # 添加标题
    if result["suggested_titles"] and len(result["suggested_titles"]) > 0:
        md_lines.append(f"# {result['suggested_titles'][0]}")
    else:
        md_lines.append(f"# 关于{result['keyword']}的技术视频脚本")

    md_lines.append("")

    # 添加元数据
    md_lines.append("## 元数据")
    md_lines.append("")
    md_lines.append(f"- **关键词**: {result['keyword']}")
    md_lines.append(f"- **目标受众**: {result['audience_level']}")

    # 添加标题建议
    if result["suggested_titles"]:
        md_lines.append("")
        md_lines.append("## 建议标题")
        md_lines.append("")
        for i, title in enumerate(result["suggested_titles"], 1):
            md_lines.append(f"{i}. {title}")

    # 添加脚本内容
    md_lines.append("")
    md_lines.append("## 视频脚本")
    md_lines.append("")

    # 使用enhanced_script，它已经包含了嵌入的Manim代码
    if result.get("enhanced_script"):
        md_lines.append(result["enhanced_script"])
    else:
        md_lines.append(result["script"])

    # 添加附录：所有Manim代码
    if result["manim_code_blocks"]:
        md_lines.append("")
        md_lines.append("## 附录：Manim动画代码")
        md_lines.append("")

        for i, block in enumerate(result["manim_code_blocks"], 1):
            md_lines.append(f"### 场景 {i}: {block['description']}")
            md_lines.append("")
            md_lines.append("```python")
            md_lines.append(block["code"])
            md_lines.append("```")
            md_lines.append("")

    return "\n".join(md_lines)


def generate_text_output(result: dict) -> str:
    """生成纯文本格式的输出"""
    txt_lines = []

    # 添加标题
    if result["suggested_titles"] and len(result["suggested_titles"]) > 0:
        txt_lines.append(f"{result['suggested_titles'][0]}")
    else:
        txt_lines.append(f"关于{result['keyword']}的技术视频脚本")

    txt_lines.append("=" * 50)
    txt_lines.append("")

    # 添加元数据
    txt_lines.append("元数据:")
    txt_lines.append(f"关键词: {result['keyword']}")
    txt_lines.append(f"目标受众: {result['audience_level']}")
    txt_lines.append("")

    # 添加标题建议
    if result["suggested_titles"]:
        txt_lines.append("建议标题:")
        for i, title in enumerate(result["suggested_titles"], 1):
            txt_lines.append(f"{i}. {title}")
        txt_lines.append("")

    # 添加脚本内容
    txt_lines.append("视频脚本:")
    txt_lines.append("=" * 50)
    txt_lines.append("")

    # 使用script而非enhanced_script，避免在纯文本中包含代码块
    script = result["script"]

    # 替换Markdown格式的代码块标记
    script = script.replace("```python", "").replace("```", "")
    txt_lines.append(script)

    # 添加附录：所有Manim代码的描述
    if result["manim_code_blocks"]:
        txt_lines.append("")
        txt_lines.append("附录：Manim动画代码 (保存在单独的Python文件中)")
        txt_lines.append("-" * 50)

        for i, block in enumerate(result["manim_code_blocks"], 1):
            txt_lines.append(f"场景 {i}: {block['description']}")

    return "\n".join(txt_lines)


if __name__ == "__main__":
    asyncio.run(main())

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
    parser.add_argument("--debug", action="store_true", help="启用详细debug日志")

    args = parser.parse_args()

    # 记录debug模式启用情况
    if args.debug:
        logger.info("已启用debug模式，将输出详细日志")
        # 注意：无需设置日志级别，项目的logger可能没有setLevel方法

    # 确保输出目录存在，并转换为绝对路径
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"输出目录绝对路径: {output_dir}")

    # 创建输出文件名
    slug = args.keyword.lower().replace(" ", "_").replace("-", "_")
    timestamp = int(asyncio.get_event_loop().time())
    base_filename = f"{slug}_{args.audience}_{timestamp}"

    try:
        # 初始化工作流并执行脚本生成
        logger.info(f"开始为关键字 '{args.keyword}' 生成视频脚本")

        # 设置输出目录 - 使用绝对路径
        workflow = VideoScriptWorkflow()
        workflow.output_dir = str(output_dir)
        logger.info(f"设置工作流输出目录为: {workflow.output_dir}")

        # 记录开始时间
        start_time = asyncio.get_event_loop().time()

        # 生成脚本
        result = await workflow.generate_script(args.keyword, args.audience)

        # 计算总耗时
        elapsed_time = asyncio.get_event_loop().time() - start_time
        logger.info(f"脚本生成完成，总耗时: {elapsed_time:.2f}秒")

        # 检查结果是否有效
        has_script = bool(result.get("script"))
        has_code = bool(result.get("manim_code_blocks"))
        logger.info(f"生成结果状态: 脚本{'存在' if has_script else '缺失'}, Manim代码{'存在' if has_code else '缺失'}")

        if not has_script:
            logger.warning("警告：未能生成有效的脚本内容")

        # 检查Markdown文件是否已生成
        md_file_exists = workflow.output_file and os.path.exists(workflow.output_file)

        if args.output_format == "md":
            if md_file_exists:
                logger.info(f"已在工作流中生成Markdown脚本: {workflow.output_file}")
                output_files = [workflow.output_file]
            else:
                # Markdown文件应该生成但未找到，手动创建
                logger.warning(f"未找到预期的Markdown文件: {workflow.output_file}，将手动创建")
                md_content = generate_markdown_output(result)
                output_file = output_dir / f"{base_filename}.md"
                with open(output_file, "w", encoding="utf-8") as f:
                    f.write(md_content)
                logger.info(f"手动生成Markdown脚本: {output_file}")
                output_files = [output_file]
        else:
            # 生成其他格式的输出
            if args.output_format == "json":
                # JSON格式输出
                output_file = output_dir / f"{base_filename}.json"
                with open(output_file, "w", encoding="utf-8") as f:
                    json.dump(result, f, ensure_ascii=False, indent=2)
                logger.info(f"已生成JSON数据: {output_file}")
            elif args.output_format == "txt":
                # 纯文本格式输出
                txt_content = generate_text_output(result)
                output_file = output_dir / f"{base_filename}.txt"
                with open(output_file, "w", encoding="utf-8") as f:
                    f.write(txt_content)
                logger.info(f"已生成文本脚本: {output_file}")
            output_files = [output_file]

        # 如果有Manim代码，同时创建单独的Manim代码文件
        if has_code:
            manim_dir = output_dir / f"{base_filename}_manim_code"
            manim_dir.mkdir(exist_ok=True)

            for i, block in enumerate(result["manim_code_blocks"], 1):
                # 确保文件名是有效的
                safe_desc = ''.join(c if c.isalnum() or c in '_- ' else '_' for c in block['description'][:30])
                code_file = manim_dir / f"scene_{i}_{safe_desc.replace(' ', '_')}.py"
                with open(code_file, "w", encoding="utf-8") as f:
                    f.write(block["code"])

            logger.info(f"Manim代码保存在: {manim_dir}")

        # 列出outputs目录中的文件，帮助调试
        logger.info(f"输出目录内容列表:")
        for item in output_dir.iterdir():
            logger.info(f"  - {item.name}")

        logger.info(f"脚本生成过程完成! 输出文件: {', '.join(str(f) for f in output_files)}")
        return 0

    except Exception as e:
        logger.error(f"脚本生成过程中发生严重错误: {str(e)}")
        import traceback
        logger.error(f"错误详情: \n{traceback.format_exc()}")
        return 1


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

    # 检查脚本内容是否有效
    script_content = ""
    if result.get("enhanced_script"):
        script_content = result["enhanced_script"]
    elif result.get("script"):
        script_content = result["script"]

    if script_content:
        md_lines.append(script_content)
    else:
        md_lines.append("> **警告**：未生成有效的脚本内容。")

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


if __name__ == "__main__":
    asyncio.run(main())

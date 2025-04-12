"""
视频脚本生成工作流模块

定义视频脚本生成的工作流程，协调各个Agent的工作
"""

from typing import Dict, List, Any, Optional
import asyncio
import os
import time
from pathlib import Path

from app.logger import logger
from app.video_script.agents.script_writer import ScriptWriterAgent
from app.video_script.agents.manim_coder import ManimCoderAgent
from app.schema import Message
from app.llm import LLM

class VideoScriptWorkflow:
    """视频脚本生成工作流

    协调内容规划、脚本撰写和Manim代码生成的整体流程，
    实现串行执行：先标题，再章节结构，然后逐章节撰写，适时生成Manim代码
    """

    def __init__(self):
        """初始化视频脚本生成工作流"""
        # 初始化各个Agent
        self.script_writer = ScriptWriterAgent()
        self.manim_coder = ManimCoderAgent()

        # 创建独立的LLM实例用于辅助功能
        self.llm = LLM()

        # 存储工作流状态和结果
        self.keyword: str = ""
        self.audience_level: str = "beginner"  # 可选值: beginner, intermediate, advanced
        self.suggested_titles: List[str] = []
        self.selected_title: str = ""
        self.chapters: List[Dict[str, Any]] = []
        self.current_content: str = ""
        self.manim_code_blocks: List[Dict[str, Any]] = []

        # 输出文件路径
        self.output_dir: str = "./outputs"
        self.output_file: str = ""
        self.temp_md_file: str = ""

        # 添加计划终止状态跟踪
        self._plan_completed = False

    async def generate_script(self, keyword: str, audience_level: str = "beginner") -> Dict[str, Any]:
        """
        根据关键字生成视频脚本和Manim代码，实现串行工作流

        Args:
            keyword: 技术关键字，如"区块链"、"支持向量机"等
            audience_level: 目标受众水平，可选值: beginner, intermediate, advanced

        Returns:
            包含脚本、Manim代码和建议标题的结果字典
        """
        self.keyword = keyword
        self.audience_level = audience_level

        # 设置输出文件
        self._setup_output_files()

        # 添加计划终止状态跟踪
        self._plan_completed = False

        try:
            logger.info(f"开始为关键字 '{keyword}' (受众: {audience_level}) 生成视频脚本")

            # 步骤1: 生成标题建议
            await self._generate_titles()

            # 更新有意义的初始内容
            initial_content = f"# {self.selected_title}\n\n"
            initial_content += "## 内容生成中...\n\n请稍候，正在为您生成高质量的视频脚本。"
            self._update_markdown_file(initial_content)

            # 步骤2: 生成章节结构
            await self._generate_chapter_structure()

            # 步骤3: 逐章节撰写内容，适时生成Manim代码
            await self._write_chapters_with_visualization()

            # 标记计划已完成
            self._plan_completed = True

            # 步骤4: 整合最终输出
            final_output = self._assemble_final_output()

            # 检查内容完整性
            if not self.current_content or len(self.current_content) < 500:
                logger.warning("最终内容长度不足，尝试恢复基本章节结构")
                self._ensure_minimum_content()

            # 最后更新一次Markdown文件并标记完成
            self._update_markdown_file(self.current_content)
            self._mark_generation_completed()

            logger.info(f"视频脚本生成完成，最终结果包含 {len(self.current_content)} 字符的脚本和 {len(self.manim_code_blocks)} 个代码块")

            return final_output

        except Exception as e:
            logger.error(f"生成视频脚本时出错: {str(e)}")
            import traceback
            logger.error(f"错误详情:\n{traceback.format_exc()}")

            # 出错时也确保有基本内容
            if not self.current_content or len(self.current_content) < 500:
                logger.warning("发生错误，正在生成基本内容以确保输出")
                self._ensure_minimum_content()
                self._update_markdown_file(self.current_content)
                self._mark_generation_completed(error=True)

            # 返回尽可能有用的结果，即使出错
            return {
                "keyword": self.keyword,
                "audience_level": self.audience_level,
                "suggested_titles": self.suggested_titles or [f"理解{keyword}技术", f"{keyword}入门与进阶"],
                "script": self.current_content or f"脚本生成过程中出错: {str(e)}，请重试。",
                "enhanced_script": self.current_content or f"脚本生成过程中出错: {str(e)}，请重试。",
                "manim_code_blocks": self.manim_code_blocks
            }

    def _setup_output_files(self):
        """设置输出文件路径"""
        # 确保输出目录存在
        try:
            # 转换为绝对路径
            output_dir_path = Path(self.output_dir).resolve()
            output_dir_path.mkdir(parents=True, exist_ok=True)

            # 更新为绝对路径字符串
            self.output_dir = str(output_dir_path)

            # 创建输出文件名
            slug = self.keyword.lower().replace(" ", "_").replace("-", "_")
            timestamp = int(time.time())
            base_filename = f"{slug}_{self.audience_level}_{timestamp}"

            self.output_file = os.path.join(self.output_dir, f"{base_filename}.md")
            self.temp_md_file = os.path.join(self.output_dir, f"{base_filename}_temp.md")

            logger.info(f"输出文件设置完成，将生成: {self.output_file}")

            # 测试目录是否可写
            test_file = os.path.join(self.output_dir, ".write_test")
            with open(test_file, "w") as f:
                f.write("测试写入权限")
            if os.path.exists(test_file):
                os.remove(test_file)
                logger.info(f"确认目录 {self.output_dir} 可写")
            else:
                logger.warning(f"无法确认目录 {self.output_dir} 的写入权限")

        except Exception as e:
            logger.error(f"设置输出文件路径时出错: {str(e)}")
            # 使用默认输出目录作为后备
            self.output_dir = os.path.abspath("./outputs")
            Path(self.output_dir).mkdir(parents=True, exist_ok=True)

            slug = self.keyword.lower().replace(" ", "_").replace("-", "_")
            timestamp = int(time.time())
            base_filename = f"{slug}_{self.audience_level}_{timestamp}"

            self.output_file = os.path.join(self.output_dir, f"{base_filename}.md")
            self.temp_md_file = os.path.join(self.output_dir, f"{base_filename}_temp.md")

            logger.warning(f"使用备用输出文件路径: {self.output_file}")

    def _update_markdown_file(self, content: str):
        """更新Markdown文件，展示当前生成的内容"""
        if not self.output_file or not self.temp_md_file:
            logger.error("未设置输出文件路径，无法更新Markdown文件")
            return

        # 检查内容是否有意义
        placeholders = ["生成中...", "请稍候"]
        if any(ph in content for ph in placeholders) and len(content) < 200:
            logger.info(f"检测到占位内容，将添加更多上下文信息: {content[:50]}...")
            # 为占位内容添加更多上下文
            if self.selected_title:
                enhanced_content = f"# {self.selected_title}\n\n"
                enhanced_content += f"## 关于{self.keyword}\n\n"
                enhanced_content += content
                content = enhanced_content

        try:
            # 生成完整的Markdown内容
            md_content = self._generate_markdown_preview(content)

            # 记录临时文件路径
            logger.info(f"尝试写入临时文件: {self.temp_md_file}")

            # 确保目录存在
            output_dir = os.path.dirname(self.temp_md_file)
            if not os.path.exists(output_dir):
                os.makedirs(output_dir, exist_ok=True)
                logger.info(f"创建目录: {output_dir}")

            # 写入临时文件
            with open(self.temp_md_file, "w", encoding="utf-8") as f:
                f.write(md_content)

            # 确认临时文件写入成功
            if not os.path.exists(self.temp_md_file):
                logger.error(f"临时文件写入失败: {self.temp_md_file}")
                return

            logger.info(f"临时文件写入成功，大小: {os.path.getsize(self.temp_md_file)} 字节")

            # 如果写入成功，重命名为正式文件
            if os.path.exists(self.output_file):
                logger.info(f"删除已存在的输出文件: {self.output_file}")
                os.remove(self.output_file)

            os.rename(self.temp_md_file, self.output_file)

            if os.path.exists(self.output_file):
                file_size = os.path.getsize(self.output_file)
                logger.info(f"已更新Markdown文件: {self.output_file}, 大小: {file_size} 字节")
            else:
                logger.error(f"重命名后文件不存在: {self.output_file}")

        except Exception as e:
            logger.error(f"更新Markdown文件时出错: {str(e)}")
            import traceback
            logger.error(f"错误详情:\n{traceback.format_exc()}")

            # 尝试直接写入最终文件
            try:
                logger.info(f"尝试直接写入最终文件: {self.output_file}")
                md_content = self._generate_markdown_preview(content)
                with open(self.output_file, "w", encoding="utf-8") as f:
                    f.write(md_content)
                if os.path.exists(self.output_file):
                    logger.info(f"直接写入最终文件成功: {self.output_file}")
            except Exception as e2:
                logger.error(f"直接写入最终文件失败: {str(e2)}")

    def _generate_markdown_preview(self, content: str) -> str:
        """生成预览的Markdown内容"""
        md_lines = []

        # 添加标题
        if self.selected_title:
            md_lines.append(f"# {self.selected_title}")
        else:
            md_lines.append(f"# 关于{self.keyword}的技术视频脚本")

        md_lines.append("")

        # 添加元数据
        md_lines.append("## 元数据")
        md_lines.append("")
        md_lines.append(f"- **关键词**: {self.keyword}")
        md_lines.append(f"- **目标受众**: {self.audience_level}")
        md_lines.append(f"- **生成状态**: 进行中...")
        md_lines.append("")

        # 添加标题建议
        if self.suggested_titles:
            md_lines.append("## 建议标题")
            md_lines.append("")
            for i, title in enumerate(self.suggested_titles, 1):
                md_lines.append(f"{i}. {title}")
            md_lines.append("")

        # 如果已选择标题，标明
        if self.selected_title:
            md_lines.append(f"> **已选择标题**: {self.selected_title}")
            md_lines.append("")

        # 添加章节结构（如果有）
        if self.chapters:
            md_lines.append("## 章节结构")
            md_lines.append("")
            for i, chapter in enumerate(self.chapters, 1):
                md_lines.append(f"{i}. **{chapter['title']}**")
                if chapter.get('description'):
                    md_lines.append(f"   - {chapter['description']}")
            md_lines.append("")

        # 添加当前内容
        md_lines.append("## 视频脚本")
        md_lines.append("")
        md_lines.append(content)

        # 添加已生成的Manim代码块信息
        if self.manim_code_blocks:
            md_lines.append("")
            md_lines.append("## 已生成的可视化代码")
            md_lines.append("")
            for i, block in enumerate(self.manim_code_blocks, 1):
                md_lines.append(f"### 场景 {i}: {block['description']}")
                md_lines.append("")
                md_lines.append("```python")
                md_lines.append(block["code"])
                md_lines.append("```")
                md_lines.append("")

        return "\n".join(md_lines)

    async def _generate_titles(self):
        """生成标题建议并选择一个作为最终标题"""
        logger.info("步骤1: 生成标题建议")

        # 确保重置任何现有的计划ID，避免重复开始
        if hasattr(self.script_writer, 'active_plan_id') and self.script_writer.active_plan_id:
            logger.info(f"检测到已有活动计划 {self.script_writer.active_plan_id}，将重置")
            # 保存已完成的计划ID列表
            if not hasattr(self.script_writer, '_completed_plan_ids'):
                self.script_writer._completed_plan_ids = []
            self.script_writer._completed_plan_ids.append(self.script_writer.active_plan_id)
            # 重置计划ID
            self.script_writer.active_plan_id = None

        # 构建请求
        title_request = f"""
请为技术关键字"{self.keyword}"生成5个不同风格的视频标题建议，考虑目标受众为{self.audience_level}级别。

标题应当：
1. 吸引人且准确描述主题
2. 长度适中（20-60个字符）
3. 风格多样（问题式、陈述式、比喻式等）

请仅输出标题列表，格式如下：
1. 标题一
2. 标题二
（以此类推）

不需要额外解释，只需要提供标题列表。
"""

        # 请求生成标题
        try:
            title_result = await self.script_writer.run(title_request)

            # 提取标题列表
            self.script_writer._extract_titles(title_result)
            self.suggested_titles = self.script_writer.suggested_titles

            # 如果没有提取到标题，使用默认标题
            if not self.suggested_titles:
                self.suggested_titles = [
                    f"深入理解{self.keyword}：原理、技术与应用",
                    f"{self.keyword}技术完全指南",
                    f"{self.keyword}：从入门到精通",
                    f"探索{self.keyword}的奥秘",
                    f"{self.keyword}实战指南：理论与实践"
                ]

            logger.info(f"生成了 {len(self.suggested_titles)} 个标题建议")

            # 选择第一个标题作为最终标题
            if self.suggested_titles:
                self.selected_title = self.suggested_titles[0]
                logger.info(f"选择标题: {self.selected_title}")

            # 更新Markdown文件
            self._update_markdown_file("## 正在生成章节结构...\n\n请稍候...")

        except Exception as e:
            logger.error(f"生成标题时出错: {str(e)}")
            # 设置默认标题
            self.selected_title = f"深入理解{self.keyword}：原理、技术与应用"

    async def _generate_chapter_structure(self):
        """生成章节结构"""
        logger.info("步骤2: 生成章节结构")

        # 构建请求
        chapter_request = f"""
请为主题"{self.keyword}"的技术教学视频设计一个详细的章节结构，标题为："{self.selected_title}"。

目标受众水平: {self.audience_level}

请设计6-8个主要章节，每个章节应包含标题和简短描述。章节结构应遵循技术教学的良好实践：
1. 从基础概念开始
2. 逐步深入到复杂内容
3. 包含理论与实践应用
4. 最后总结与展望

请以列表形式输出章节结构：
1. 章节标题一：简短描述
2. 章节标题二：简短描述
（以此类推）

不需要额外解释，只需提供章节结构列表。
"""

        try:
            chapter_result = await self.script_writer.run(chapter_request)

            # 解析章节结构
            self.chapters = self._parse_chapter_structure(chapter_result)

            logger.info(f"生成了 {len(self.chapters)} 个章节")

            # 更新Markdown文件
            temp_content = "# 章节结构\n\n"
            for i, chapter in enumerate(self.chapters, 1):
                temp_content += f"## {i}. {chapter['title']}\n"
                if chapter.get('description'):
                    temp_content += f"{chapter['description']}\n\n"

            self._update_markdown_file(temp_content + "\n\n## 正在撰写内容...\n\n请稍候...")

        except Exception as e:
            logger.error(f"生成章节结构时出错: {str(e)}")
            # 设置默认章节结构
            self.chapters = [
                {"title": "引言", "description": "介绍主题及其重要性"},
                {"title": "基础概念", "description": "解释基本术语和概念"},
                {"title": "核心技术", "description": "深入探讨核心技术原理"},
                {"title": "应用场景", "description": "探讨实际应用案例"},
                {"title": "未来发展", "description": "讨论技术发展趋势"},
                {"title": "总结", "description": "总结要点并提供进一步学习资源"}
            ]

    def _parse_chapter_structure(self, text: str) -> List[Dict[str, str]]:
        """从文本中解析章节结构"""
        chapters = []
        lines = text.split('\n')

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # 匹配常见的章节格式
            chapter_match = False
            title = ""
            description = ""

            # 检查是否以数字开头
            if any(line.startswith(f"{i}.") or line.startswith(f"{i}、") for i in range(1, 20)):
                parts = line.split('：', 1) if '：' in line else line.split(':', 1)

                if len(parts) >= 2:
                    title_part = parts[0]
                    # 去除章节序号
                    title = title_part.split('.', 1)[-1].split('、', 1)[-1].strip()
                    description = parts[1].strip()
                    chapter_match = True
                else:
                    title = line.split('.', 1)[-1].split('、', 1)[-1].strip()
                    chapter_match = True

            # 处理其他格式
            elif '：' in line or ':' in line:
                parts = line.split('：', 1) if '：' in line else line.split(':', 1)
                if len(parts) >= 2:
                    title = parts[0].strip()
                    description = parts[1].strip()
                    chapter_match = True

            if chapter_match and title:
                chapters.append({
                    "title": title,
                    "description": description
                })

        return chapters

    async def _write_chapters_with_visualization(self):
        """逐章节撰写内容，并在需要时生成Manim可视化代码"""
        logger.info("步骤3: 逐章节撰写内容并生成可视化")

        # 如果没有章节，先确保有章节
        if not self.chapters or len(self.chapters) < 3:
            logger.warning("章节结构不完整，将使用默认章节")
            self.chapters = [
                {"title": "引言", "description": "介绍主题及其重要性"},
                {"title": "基础概念", "description": "解释基本术语和概念"},
                {"title": "核心技术原理", "description": "深入探讨核心技术原理"},
                {"title": "应用场景", "description": "探讨实际应用案例"},
                {"title": "总结", "description": "总结主要观点并展望"}
            ]

        # 初始化当前内容
        if not self.current_content or "# " not in self.current_content:
            self.current_content = f"# {self.selected_title}\n\n"

        # 最大重试次数
        max_retries = 2
        max_failures = len(self.chapters) // 2  # 允许最多一半章节失败
        failures = 0

        # 逐章节撰写
        for i, chapter in enumerate(self.chapters, 1):
            try:
                logger.info(f"撰写第 {i}/{len(self.chapters)} 章: {chapter['title']}")

                # 更新Markdown文件
                self._update_markdown_file(self.current_content + f"\n\n## 正在撰写: {chapter['title']}...\n\n请稍候...")

                # 构建章节请求
                retry_count = 0
                chapter_content = None

                while retry_count <= max_retries and not chapter_content:
                    try:
                        chapter_content = await self._write_chapter(chapter, i)
                        if not chapter_content or len(chapter_content) < 50:
                            logger.warning(f"章节 {chapter['title']} 内容过短或为空，重试...")
                            chapter_content = None
                            retry_count += 1
                    except Exception as e:
                        logger.error(f"撰写章节 {chapter['title']} 时出错: {str(e)}")
                        retry_count += 1
                        # 等待一小段时间后重试
                        await asyncio.sleep(2)

                # 如果重试失败，使用基本内容
                if not chapter_content:
                    logger.warning(f"尝试 {retry_count} 次后仍未能生成章节 {chapter['title']} 内容，使用基本内容")
                    chapter_content = f"{chapter.get('description', '本章节描述未提供')}\n\n本章节内容生成失败，请稍后重试。"
                    failures += 1

                # 添加到当前内容
                self.current_content += f"\n\n## {i}. {chapter['title']}\n\n{chapter_content}"

                # 更新Markdown文件
                self._update_markdown_file(self.current_content)

                # 如果失败太多，跳过剩余章节
                if failures >= max_failures:
                    logger.error(f"已有 {failures} 个章节生成失败，超过阈值，将跳过剩余章节")
                    break

                # 检查是否需要可视化
                visualization_sections = await self._identify_visualization_needs(chapter_content)
                if visualization_sections:
                    logger.info(f"检测到第 {i} 章需要 {len(visualization_sections)} 个可视化部分")

                    # 为每个需要可视化的部分生成Manim代码
                    for section in visualization_sections:
                        try:
                            logger.info(f"为'{section['description'][:30]}...'生成Manim代码")

                            # 生成Manim代码
                            code_block = await self._generate_manim_code(section, chapter['title'])
                            if code_block:
                                self.manim_code_blocks.append(code_block)

                                # 在内容中插入可视化代码引用
                                insertion_point = self.current_content.find(section['content']) + len(section['content'])
                                if insertion_point > 0:
                                    code_reference = f"\n\n```python\n# Manim代码：{section['description']}\n{code_block['code']}\n```\n\n"
                                    self.current_content = self.current_content[:insertion_point] + code_reference + self.current_content[insertion_point:]

                                # 更新Markdown文件
                                self._update_markdown_file(self.current_content)
                        except Exception as e:
                            logger.error(f"生成可视化代码时出错: {str(e)}")
                            # 继续处理下一个部分，不中断流程
            except Exception as e:
                logger.error(f"处理章节 {chapter['title']} 时发生严重错误: {str(e)}")
                import traceback
                logger.error(f"错误详情:\n{traceback.format_exc()}")
                failures += 1

                # 添加错误信息到当前内容
                self.current_content += f"\n\n## {i}. {chapter['title']}\n\n生成此章节时出错: {str(e)}\n\n"
                self._update_markdown_file(self.current_content)

                # 如果失败太多，跳过剩余章节
                if failures >= max_failures:
                    logger.error(f"已有 {failures} 个章节生成失败，超过阈值，将跳过剩余章节")
                    break

        # 无论如何都要添加总结
        try:
            self.current_content += "\n\n## 总结\n\n"
            summary_content = await self._generate_summary()
            self.current_content += summary_content
        except Exception as e:
            logger.error(f"生成总结时出错: {str(e)}")
            self.current_content += f"本视频介绍了关于{self.keyword}的核心概念和应用。希望这些内容对您有所帮助，感谢观看！"

        # 更新最终Markdown文件
        self._update_markdown_file(self.current_content)

    async def _write_chapter(self, chapter: Dict[str, str], chapter_num: int) -> str:
        """撰写单个章节的内容"""
        # 构建请求
        chapter_request = f"""
请撰写"{self.selected_title}"视频脚本的第{chapter_num}章："{chapter['title']}"。

已有内容概要：
{self.current_content[:500] + '...' if len(self.current_content) > 500 else self.current_content}

本章描述：{chapter.get('description', '无附加描述')}

目标受众：{self.audience_level}级别

请注意：
1. 内容应与已有章节保持连贯，避免重复
2. 使用自然口语化表达，适合视频讲解
3. 重要概念或需要可视化的部分请用以下格式标记：【可视化: 描述】内容【/可视化】
4. 适当包含例子和应用场景，增强理解
5. 章节内容应全面但精炼，约500-800字

只需提供章节内容，无需添加章节标题。
"""

        try:
            logger.info(f"开始生成第{chapter_num}章: {chapter['title']}内容")
            chapter_content = await self.script_writer.run(chapter_request)
            content_length = len(chapter_content) if chapter_content else 0
            logger.info(f"第{chapter_num}章生成完成，内容长度: {content_length} 字符")
            return chapter_content
        except Exception as e:
            logger.error(f"撰写章节 {chapter['title']} 时出错: {str(e)}")
            return f"（生成此章节内容时出错，请重试）"

    async def _generate_summary(self) -> str:
        """生成总结部分"""
        summary_request = f"""
请为视频"{self.selected_title}"撰写一个总结部分。

已有内容概述：
{self.current_content[:500] + '...' if len(self.current_content) > 500 else '（内容生成中）'}

总结应当：
1. 回顾视频中的关键概念和要点
2. 提供进一步学习的资源或建议
3. 鼓励观众应用所学知识
4. 简洁有力，长度约300-500字

只需提供总结内容，无需标题。
"""

        try:
            logger.info("开始生成视频总结部分")
            summary_content = await self.script_writer.run(summary_request)
            summary_length = len(summary_content) if summary_content else 0
            logger.info(f"总结部分生成完成，内容长度: {summary_length} 字符")
            return summary_content
        except Exception as e:
            logger.error(f"生成总结时出错: {str(e)}")
            return "本视频介绍了关于该主题的核心概念和应用。希望这些内容对您有所帮助，感谢观看！"

    async def _identify_visualization_needs(self, content: str) -> List[Dict[str, Any]]:
        """识别内容中需要可视化的部分"""
        visualization_sections = []

        # 查找特殊标记的部分：【可视化: 描述】内容【/可视化】
        start_markers = ["【可视化:", "【可视化："]
        end_marker = "【/可视化】"

        # 如果没有找到可视化标记，先尝试关键词匹配
        if not any(marker in content for marker in start_markers):
            # 使用关键词匹配作为快速检查
            visualization_keywords = [
                "计算图", "神经网络", "架构", "流程", "公式", "算法",
                "量化过程", "量化算法", "量化方法", "矩阵", "向量", "比较",
                "权重", "激活", "函数", "模型结构"
            ]

            # 先用简单的关键词匹配检查是否有潜在的可视化需求
            potential_matches = []
            paragraphs = content.split('\n\n')
            for paragraph in paragraphs:
                if any(keyword in paragraph for keyword in visualization_keywords) and len(paragraph) > 30:
                    potential_matches.append(paragraph)

            # 如果发现潜在的可视化段落，使用我们自己的LLM实例进行判断
            if potential_matches:
                try:
                    logger.info(f"检测到 {len(potential_matches)} 个潜在的可视化内容，使用LLM直接判断...")

                    # 构建请求，仅针对潜在段落进行评估
                    potential_content = "\n\n".join(potential_matches[:3])  # 最多评估3段
                    viz_request = f"""
请评估以下技术教学视频脚本内容，确定哪些部分最适合用Manim动画可视化展示。
内容是关于"{self.keyword}"的一个章节片段。

{potential_content}

请选择至多2个最需要可视化的段落或概念，使用以下标准评估：
1. 该概念是否包含抽象或复杂的过程/算法/结构
2. 可视化是否能明显增强观众理解
3. 该概念是否适合用Manim进行动画展示

输出格式：
- 对于每个推荐可视化的部分，提供：
  1. 可视化内容：复制原文中需要可视化的具体段落（精确复制）
  2. 描述：简短描述这部分可视化的目的，应该可视化什么内容

注意：只选择真正需要可视化的内容。如果没有适合可视化的内容，请明确回复"无需可视化"。
"""

                    # 使用我们自己的LLM实例直接调用，不走规划流程
                    messages = [{"role": "user", "content": viz_request}]
                    system_msg = [{"role": "system", "content": "你是一位技术视频内容可视化专家，擅长判断哪些技术内容适合通过动画进行可视化展示。"}]

                    # 使用self.llm而不是self.script_writer.llm
                    result = await self.llm.ask(
                        messages=messages,
                        system_msgs=system_msg
                    )

                    # 只记录结果长度，不记录具体内容
                    logger.info(f"LLM可视化评估结果长度: {len(result)} 字符")

                    # 检查是否建议不需要可视化
                    if "无需可视化" in result or "不需要可视化" in result:
                        logger.info("LLM评估结果：内容不需要可视化")
                        return []

                    # 解析结果并找到原内容中的位置
                    sections = []
                    viz_content = None
                    viz_desc = None

                    for line in result.split('\n'):
                        line = line.strip()
                        if not line:
                            continue

                        # 提取可视化内容
                        if line.startswith("可视化内容：") or line.startswith("可视化内容:"):
                            # 处理之前的section
                            if viz_content and viz_desc:
                                # 在完整内容中查找位置
                                start_pos = content.find(viz_content)
                                if start_pos >= 0:
                                    sections.append({
                                        "content": viz_content,
                                        "description": viz_desc,
                                        "start_pos": start_pos,
                                        "end_pos": start_pos + len(viz_content)
                                    })

                            # 开始新section
                            colon_pos = line.find("：") if "：" in line else line.find(":")
                            viz_content = line[colon_pos+1:].strip()
                            viz_desc = None

                        # 提取描述
                        elif (line.startswith("描述：") or line.startswith("描述:")) and viz_content:
                            colon_pos = line.find("：") if "：" in line else line.find(":")
                            viz_desc = line[colon_pos+1:].strip()

                    # 处理最后一个section
                    if viz_content and viz_desc:
                        start_pos = content.find(viz_content)
                        if start_pos >= 0:
                            sections.append({
                                "content": viz_content,
                                "description": viz_desc,
                                "start_pos": start_pos,
                                "end_pos": start_pos + len(viz_content)
                            })

                    if sections:
                        # 记录识别到的每个部分的长度，而不是内容
                        for i, section in enumerate(sections):
                            logger.info(f"LLM识别的可视化部分 {i+1}: 描述='{section['description'][:30]}...', 内容长度={len(section['content'])} 字符")
                        return sections

                    logger.warning("LLM识别结果解析失败，回退到关键词匹配")

                except Exception as e:
                    logger.error(f"使用LLM判断可视化需求时出错: {str(e)}")
                    logger.warning("由于错误，回退到简单关键词匹配")

            # 如果LLM判断失败或没有发现潜在段落，使用简单的关键词匹配
            for paragraph in paragraphs:
                if any(keyword in paragraph for keyword in visualization_keywords) and len(paragraph) > 30:
                    visualization_sections.append({
                        "description": f"可视化{self.keyword}相关概念",
                        "content": paragraph,
                        "start_pos": content.find(paragraph),
                        "end_pos": content.find(paragraph) + len(paragraph)
                    })

            # 最多返回2个自动识别的部分
            return visualization_sections[:2]

        # 标准的可视化标记提取逻辑
        for start_marker in start_markers:
            start_pos = 0
            while True:
                # 查找开始标记
                start_idx = content.find(start_marker, start_pos)
                if start_idx == -1:
                    break

                # 获取描述（标记与内容之间）
                desc_start = start_idx + len(start_marker)
                desc_end = content.find("】", desc_start)

                if desc_end == -1:
                    # 如果没有找到结束括号，跳过此部分
                    start_pos = desc_start
                    continue

                description = content[desc_start:desc_end].strip()

                # 获取内容
                content_start = desc_end + 1
                content_end = content.find(end_marker, content_start)

                if content_end == -1:
                    # 如果没有找到结束标记，使用下一个开始标记或文本末尾
                    next_start = content.find(start_marker, content_start)
                    content_end = next_start if next_start != -1 else len(content)

                content_text = content[content_start:content_end].strip()

                # 添加到结果列表
                visualization_sections.append({
                    "description": description,
                    "content": content_text,
                    "start_pos": start_idx,
                    "end_pos": content_end + len(end_marker) if content_end + len(end_marker) <= len(content) else len(content)
                })

                # 更新搜索位置
                start_pos = content_end

        return visualization_sections

    async def _generate_manim_code(self, section: Dict[str, Any], chapter_title: str) -> Optional[Dict[str, Any]]:
        """为需要可视化的部分生成Manim代码"""
        manim_request = f"""
请为以下技术教学视频脚本中的概念生成Manim Python动画代码：

章节: {chapter_title}
概念: {section['content']}
描述: {section['description']}
上下文关键字: {self.keyword}

生成的代码应该：
1. 使用最新的Manim社区版(manim-community)语法
2. 能够清晰可视化上述概念
3. 添加必要的注释解释代码作用
4. 代码应当能够独立运行

请确保代码的视觉效果能够增强观众对概念的理解，并遵循良好的Manim编程实践。
"""

        try:
            logger.info(f"为概念'{section['description'][:50]}...'生成Manim代码")
            code_result = await self.manim_coder.run(manim_request)

            # 解析代码结果
            if code_result:
                cleaned_code = self.manim_coder._clean_code_response(code_result)
                if cleaned_code:
                    code_length = len(cleaned_code)
                    import_pos = cleaned_code.find("import")
                    # 只记录代码的开头部分（直到第一个import语句）和总长度
                    header = cleaned_code[:min(100, code_length)] if import_pos == -1 else cleaned_code[:min(import_pos + 50, code_length)]
                    logger.info(f"成功生成Manim代码，开头: {header}..., 总长度: {code_length} 字符")
                    return {
                        "description": section['description'],
                        "content": section['content'],
                        "code": cleaned_code,
                        "position": {"start": section['start_pos'], "end": section['end_pos']}
                    }

            logger.warning(f"无法生成有效的Manim代码")
            return None

        except Exception as e:
            logger.error(f"生成Manim代码时出错: {str(e)}")
            return None

    def _assemble_final_output(self) -> Dict[str, Any]:
        """组装最终输出结果"""
        # 创建带有Manim代码的脚本
        enhanced_script = self.current_content

        return {
            "keyword": self.keyword,
            "audience_level": self.audience_level,
            "suggested_titles": self.suggested_titles,
            "script": self.current_content,
            "enhanced_script": enhanced_script,
            "manim_code_blocks": self.manim_code_blocks
        }

    def _ensure_minimum_content(self):
        """确保内容至少包含基本章节结构和内容"""
        logger.warning("正在构建基本内容以确保输出")

        # 创建基本内容
        basic_content = f"# {self.selected_title}\n\n"

        # 添加元数据
        basic_content += "## 元数据\n\n"
        basic_content += f"- **关键词**: {self.keyword}\n"
        basic_content += f"- **目标受众**: {self.audience_level}\n\n"

        # 添加标题列表
        if self.suggested_titles:
            basic_content += "## 建议标题\n\n"
            for i, title in enumerate(self.suggested_titles, 1):
                basic_content += f"{i}. {title}\n"
            basic_content += "\n"

        # 添加章节结构
        if self.chapters:
            for i, chapter in enumerate(self.chapters, 1):
                basic_content += f"## {i}. {chapter['title']}\n\n"
                basic_content += f"{chapter.get('description', '本章节描述…')}\n\n"
                basic_content += "本章节内容生成中...\n\n"
        else:
            # 如果没有章节，创建默认章节
            default_chapters = [
                {"title": "引言", "description": "介绍主题及其重要性"},
                {"title": "基础概念", "description": "解释基本术语和概念"},
                {"title": "核心技术原理", "description": "详细分析核心技术原理"},
                {"title": "应用场景", "description": "探讨实际应用案例"},
                {"title": "总结", "description": "总结主要观点并展望"}
            ]

            for i, chapter in enumerate(default_chapters, 1):
                basic_content += f"## {i}. {chapter['title']}\n\n"
                basic_content += f"{chapter['description']}\n\n"
                basic_content += "本章节内容待完善...\n\n"

        # 添加总结
        basic_content += "## 总结\n\n"
        basic_content += f"本视频介绍了关于{self.keyword}的核心概念和应用。希望这些内容对您有所帮助，感谢观看！\n\n"

        # 添加注释，标记为恢复生成
        basic_content += "<!-- 注: 此内容为系统自动恢复生成，可能需要进一步完善 -->\n"

        self.current_content = basic_content
        logger.info(f"已生成基本内容，长度: {len(basic_content)} 字符")

    def _mark_generation_completed(self, error: bool = False):
        """标记生成过程完成，创建完成标记文件"""
        try:
            # 创建.completed文件
            status = "error" if error else "completed"
            completion_file = f"{self.output_file}.{status}"
            with open(completion_file, "w", encoding="utf-8") as f:
                f.write(f"Generation {status} at {time.strftime('%Y-%m-%d %H:%M:%S')}")

            logger.info(f"已创建完成标记文件: {completion_file}")

            # 确保脚本文件没有"生成中"或"请稍候"等占位符
            if os.path.exists(self.output_file):
                with open(self.output_file, "r", encoding="utf-8") as f:
                    content = f.read()

                # 检查是否含有占位符内容
                placeholders = ["内容生成中", "请稍候", "生成中...", "正在生成"]
                if any(ph in content for ph in placeholders):
                    logger.warning("检测到输出文件中仍有占位内容，将替换为基本内容")
                    self._ensure_minimum_content()
                    with open(self.output_file, "w", encoding="utf-8") as f:
                        f.write(self._generate_markdown_preview(self.current_content))

        except Exception as e:
            logger.error(f"创建完成标记文件时出错: {str(e)}")

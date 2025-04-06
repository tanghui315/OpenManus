"""
视频脚本生成工作流模块

定义视频脚本生成的工作流程，协调各个Agent的工作
"""

from typing import Dict, List, Any, Optional
import asyncio

from app.logger import logger
from app.video_script.agents.script_writer import ScriptWriterAgent
from app.video_script.agents.manim_coder import ManimCoderAgent

class VideoScriptWorkflow:
    """视频脚本生成工作流

    协调信息收集、内容规划、脚本撰写和Manim代码生成的整体流程
    """

    def __init__(self):
        """初始化视频脚本生成工作流"""
        # 初始化各个Agent
        self.script_writer = ScriptWriterAgent()
        self.manim_coder = ManimCoderAgent()

        # 存储工作流状态和结果
        self.keyword: str = ""
        self.audience_level: str = "beginner"  # 可选值: beginner, intermediate, advanced
        self.script_result: Optional[str] = None
        self.manim_code_blocks: List[Dict[str, Any]] = []
        self.suggested_titles: List[str] = []

    async def generate_script(self, keyword: str, audience_level: str = "beginner") -> Dict[str, Any]:
        """
        根据关键字生成视频脚本和Manim代码

        Args:
            keyword: 技术关键字，如"区块链"、"支持向量机"等
            audience_level: 目标受众水平，可选值: beginner, intermediate, advanced

        Returns:
            包含脚本、Manim代码和建议标题的结果字典
        """
        self.keyword = keyword
        self.audience_level = audience_level

        try:
            logger.info(f"开始为关键字 '{keyword}' (受众: {audience_level}) 生成视频脚本")

            # 步骤1: 生成基础脚本和标题建议
            logger.info("步骤1: 生成脚本和标题建议")
            script_request = self._create_script_request(keyword, audience_level)
            script_result = await self.script_writer.run(script_request)

            # 解析脚本结果，提取脚本内容和标题建议
            self.script_result, self.suggested_titles = self._parse_script_result(script_result)

            # 步骤2: 为脚本中的关键部分生成Manim代码
            logger.info("步骤2: 生成Manim可视化代码")
            if self.script_result:
                # 找出需要可视化的关键部分
                key_sections = self._identify_key_sections(self.script_result)

                # 为每个关键部分生成Manim代码
                for section in key_sections:
                    code_request = self._create_code_request(section, keyword)
                    code_result = await self.manim_coder.run(code_request)

                    # 解析和存储代码结果
                    code_block = self._parse_code_result(code_result, section)
                    if code_block:
                        self.manim_code_blocks.append(code_block)

            # 步骤3: 整合最终输出
            logger.info("步骤3: 整合最终输出")
            final_output = self._assemble_final_output()

            return final_output

        except Exception as e:
            logger.error(f"生成视频脚本时出错: {str(e)}")
            raise

    def _create_script_request(self, keyword: str, audience_level: str) -> str:
        """创建脚本生成请求"""
        audience_desc = {
            "beginner": "入门级，假设观众对主题几乎没有先验知识",
            "intermediate": "中级，假设观众已有基本概念理解",
            "advanced": "高级，假设观众已熟悉基础知识，需要深入的技术细节"
        }.get(audience_level, "入门级，假设观众对主题几乎没有先验知识")

        return f"""
请基于关键字 "{keyword}" 生成一个技术教学视频的脚本。

目标受众: {audience_desc}

请首先进行内容规划，确定脚本的结构和核心内容点。推荐的结构为：
1. 引言：介绍主题及其重要性
2. 背景：简要介绍相关历史或背景知识
3. 核心概念：详细解释主要技术概念
4. 工作原理：解释技术如何工作
5. 应用示例：展示技术的实际应用
6. 总结：回顾要点并提供进一步学习的资源

请给出3-5个吸引人的视频标题建议。

生成的脚本应：
- 语言自然流畅，适合口头表达
- 内容准确且符合最新的技术发展
- 清晰标记出适合用动画展示的数学公式或概念
- 针对{audience_level}级别的受众设计深度和复杂度

请特别标记出需要可视化的关键部分，格式为：
【可视化: 描述】内容【/可视化】
"""

    def _create_code_request(self, section: Dict[str, str], keyword: str) -> str:
        """创建Manim代码生成请求"""
        return f"""
请为以下技术教学视频脚本中的概念生成Manim Python动画代码：

概念: {section['content']}
上下文关键字: {keyword}

生成的代码应该：
1. 使用最新的Manim社区版(manim-community)语法
2. 能够清晰可视化上述概念
3. 添加必要的注释解释代码作用
4. 代码应当能够独立运行

请确保代码的视觉效果能够增强观众对概念的理解，并遵循良好的Manim编程实践。
"""

    def _parse_script_result(self, script_result: str) -> tuple[str, List[str]]:
        """解析脚本生成结果，提取脚本内容和建议标题"""
        # 初始化结果
        script_content = script_result
        titles = []

        # 尝试从结果中提取标题建议
        if "标题建议" in script_result or "视频标题" in script_result:
            lines = script_result.split('\n')
            title_section = False
            title_lines = []

            for line in lines:
                if ("标题建议" in line or "视频标题" in line) and not title_section:
                    title_section = True
                    title_lines.append(line)
                elif title_section and (line.strip().startswith("-") or line.strip().startswith("•") or
                                        line.strip().startswith("*") or
                                        any(line.strip().startswith(f"{i}.") for i in range(1, 10))):
                    title_lines.append(line)
                elif title_section and line.strip() and not line.strip().startswith("-") and not line.strip().startswith("•"):
                    # 如果不是列表项但不是空行，可能已经离开了标题部分
                    if not any(line.strip().startswith(f"{i}.") for i in range(1, 10)):
                        title_section = False

            # 提取标题
            for line in title_lines:
                line = line.strip()
                if line and (line.startswith("-") or line.startswith("•") or line.startswith("*") or
                             any(line.startswith(f"{i}.") for i in range(1, 10))):
                    # 清理标题文本
                    title = line.lstrip("-•* 0123456789.").strip()
                    if title and title not in titles:
                        titles.append(title)

        return script_content, titles

    def _identify_key_sections(self, script: str) -> List[Dict[str, str]]:
        """识别脚本中需要可视化的关键部分"""
        sections = []

        # 查找特殊标记的部分：【可视化: 描述】内容【/可视化】
        start_markers = ["【可视化:", "【可视化："]
        end_marker = "【/可视化】"

        for start_marker in start_markers:
            start_pos = 0
            while True:
                # 查找开始标记
                start_idx = script.find(start_marker, start_pos)
                if start_idx == -1:
                    break

                # 获取描述（标记与内容之间）
                desc_start = start_idx + len(start_marker)
                desc_end = script.find("】", desc_start)

                if desc_end == -1:
                    # 如果没有找到结束括号，跳过此部分
                    start_pos = desc_start
                    continue

                description = script[desc_start:desc_end].strip()

                # 获取内容
                content_start = desc_end + 1
                content_end = script.find(end_marker, content_start)

                if content_end == -1:
                    # 如果没有找到结束标记，使用下一个开始标记或文本末尾
                    next_start = script.find(start_marker, content_start)
                    content_end = next_start if next_start != -1 else len(script)

                content = script[content_start:content_end].strip()

                # 添加到结果列表
                sections.append({
                    "description": description,
                    "content": content,
                    "start_pos": start_idx,
                    "end_pos": content_end + len(end_marker) if content_end + len(end_marker) <= len(script) else len(script)
                })

                # 更新搜索位置
                start_pos = content_end

        return sections

    def _parse_code_result(self, code_result: str, section: Dict[str, str]) -> Optional[Dict[str, Any]]:
        """解析Manim代码生成结果"""
        if not code_result or "```python" not in code_result:
            logger.warning(f"无法从结果中提取Manim代码: {code_result[:100]}...")
            return None

        # 提取Python代码块
        code_blocks = []
        in_code_block = False
        current_block = []

        for line in code_result.split('\n'):
            if line.strip().startswith("```python") or line.strip() == "```python":
                in_code_block = True
                current_block = []
            elif line.strip() == "```" and in_code_block:
                in_code_block = False
                if current_block:
                    code_blocks.append('\n'.join(current_block))
                current_block = []
            elif in_code_block:
                current_block.append(line)

        # 如果代码块未正确关闭
        if in_code_block and current_block:
            code_blocks.append('\n'.join(current_block))

        # 如果没有找到代码块，查找第一个import语句作为起点
        if not code_blocks:
            content_lines = code_result.split('\n')
            start_idx = -1
            for i, line in enumerate(content_lines):
                if "import manim" in line or "from manim import" in line:
                    start_idx = i
                    break

            if start_idx != -1:
                code_blocks.append('\n'.join(content_lines[start_idx:]))

        # 返回第一个有效的代码块
        for code in code_blocks:
            if "import manim" in code or "from manim import" in code:
                return {
                    "description": section["description"],
                    "content": section["content"],
                    "code": code,
                    "position": {"start": section["start_pos"], "end": section["end_pos"]}
                }

        # 如果未找到有效代码块
        if code_blocks:
            return {
                "description": section["description"],
                "content": section["content"],
                "code": code_blocks[0],  # 使用第一个代码块
                "position": {"start": section["start_pos"], "end": section["end_pos"]}
            }

        return None

    def _assemble_final_output(self) -> Dict[str, Any]:
        """组装最终输出结果"""
        # 创建带有Manim代码的脚本
        enhanced_script = self.script_result

        # 将Manim代码块插入到脚本中
        if self.manim_code_blocks and self.script_result:
            # 按位置排序，从后向前插入，避免位置错位
            sorted_blocks = sorted(self.manim_code_blocks, key=lambda x: x["position"]["start"], reverse=True)

            for block in sorted_blocks:
                insertion_text = f"\n\n```python\n# Manim代码：{block['description']}\n{block['code']}\n```\n\n"
                start_pos = block["position"]["end"]

                # 确保位置在范围内
                if 0 <= start_pos <= len(enhanced_script):
                    enhanced_script = enhanced_script[:start_pos] + insertion_text + enhanced_script[start_pos:]

        return {
            "keyword": self.keyword,
            "audience_level": self.audience_level,
            "suggested_titles": self.suggested_titles,
            "script": self.script_result,
            "enhanced_script": enhanced_script,
            "manim_code_blocks": self.manim_code_blocks
        }

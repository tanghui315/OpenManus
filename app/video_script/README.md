# AI 技术视频脚本生成器

这个模块提供了一个自动化工具，用于根据技术关键字生成高质量的技术教学视频脚本和配套的Manim可视化代码。

## 功能特点

- **信息检索与整合**: 自动搜索和整合技术主题的相关信息
- **结构化脚本生成**: 按照教学最佳实践生成结构清晰的视频脚本
- **Manim动画代码**: 自动为关键概念和数学公式生成可视化动画代码
- **多种输出格式**: 支持Markdown、纯文本和JSON格式输出
- **受众定制**: 可根据目标受众调整内容深度和复杂度

## 使用方法

### 命令行使用

```bash
python -m app.video_script.main "区块链" --audience beginner --output-format md
```

参数说明:
- 第一个参数: 技术关键字（必填）
- `--audience`: 目标受众水平，可选值: beginner, intermediate, advanced（默认: beginner）
- `--output-dir`: 输出目录（默认: ./outputs）
- `--output-format`: 输出格式，可选值: md, txt, json（默认: md）

### 代码中使用

```python
from app.video_script import VideoScriptWorkflow

async def generate_script():
    workflow = VideoScriptWorkflow()
    result = await workflow.generate_script("支持向量机", audience_level="intermediate")

    # 输出脚本内容
    print(result["script"])

    # 输出Manim代码
    for i, block in enumerate(result["manim_code_blocks"], 1):
        print(f"--- Manim代码块 {i}: {block['description']} ---")
        print(block["code"])
```

## 输出格式

### Markdown格式 (.md)

包含以下部分:
- 建议标题
- 元数据（关键词、目标受众）
- 完整脚本内容
- 嵌入的Manim代码块
- 附录中的所有Manim代码

### 纯文本格式 (.txt)

包含以下部分:
- 建议标题
- 元数据
- 脚本内容（不含代码块）
- Manim代码块描述（代码保存在单独文件中）

### JSON格式 (.json)

包含所有生成数据的结构化表示，方便程序处理和集成。

## 示例

```bash
# 生成关于区块链的入门级脚本
python -m app.video_script.main "区块链" --audience beginner

# 生成关于神经网络的高级脚本，输出为JSON格式
python -m app.video_script.main "神经网络" --audience advanced --output-format json
```

## 实现细节

该模块由以下主要组件组成:

1. **VideoScriptWorkflow**: 整体工作流协调器
2. **ScriptWriterAgent**: 负责生成视频脚本内容
3. **ManimCoderAgent**: 负责生成Manim动画代码

每个组件都可以单独使用或定制以满足特定需求。

## 依赖

- Manim: 用于编译和渲染生成的可视化代码
- 基础LLM框架和工具链

## 注意事项

- 生成的Manim代码需要安装Manim库才能运行和渲染
- 搜索功能依赖于互联网连接
- 为获得最佳效果，建议使用特定且明确的技术关键字

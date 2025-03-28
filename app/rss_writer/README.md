# RSS 文章生成器

基于RSS源自动生成技术文章的模块。

## 功能

- RSS Feed解析和阅读
- 内容价值评估和筛选
- 文章详情抓取
- 技术文章自动撰写

## 组件

- `RSSFeedTool`: RSS源解析工具
- `RSSFilterAgent`: RSS内容评估和筛选Agent
- `ArticleWriterAgent`: 文章规划和撰写Agent
- `RSSArticleWorkflow`: 工作流协调器

## 使用方法

### 命令行使用

```bash
python -m app.rss_writer.main "https://www.reddit.com/r/LocalLLaMA/.rss" -o article.md
```

参数:
- `rss_url`: RSS源的URL地址（必填）
- `-o, --output`: 输出文件路径（可选）

### 编程使用

```python
import asyncio
from app.rss_writer.workflow import RSSArticleWorkflow

async def generate_article():
    workflow = RSSArticleWorkflow()
    result = await workflow.run("https://www.reddit.com/r/LocalLLaMA/.rss")
    print(result)

asyncio.run(generate_article())
```

## 工作流程

1. 读取指定的RSS Feed源
2. 大模型评估并筛选有价值的文章
3. 访问筛选后文章的详情页面
4. 提取文章中的有价值信息点
5. 大模型规划文章结构，撰写主题和各章节
6. 输出完整的技术文章

如果没有找到有价值的文章，则直接结束流程。

## 依赖

- `feedparser`: RSS解析库
- `aiohttp`: 异步HTTP客户端库
- OpenManus项目的其他组件

## 注意事项

- 请确保RSS源URL可访问且为标准RSS格式
- 生成的文章质量取决于源文章的质量和大模型的能力
- 处理时间会根据RSS源大小和文章数量而变化

# RSS Writer 模块

这个模块提供从RSS源自动生成技术文章的功能。它监控指定的RSS源，筛选有价值的文章，提取关键内容，并自动生成新的技术文章。

## 功能

1. **RSS源抓取与筛选**：从指定RSS源获取最新文章，并基于相关性和价值进行筛选。
2. **内容提取与分析**：访问筛选出的文章链接，提取有价值的技术内容。
3. **文章自动生成**：基于提取的内容，自动撰写结构完整的技术文章。

## 使用方法

### 命令行使用

```bash
python -m app.rss_writer.main "https://www.reddit.com/r/LocalLLaMA/.rss" --output article.md --debug
```

参数:
- 第一个参数: RSS源URL
- `--output` 或 `-o`: 输出文件路径
- `--debug`: 启用详细调试日志

### 代码中使用

```python
import asyncio
from app.rss_writer.workflow import RSSArticleWorkflow

async def main():
    workflow = RSSArticleWorkflow()
    article = await workflow.run("https://www.reddit.com/r/LocalLLaMA/.rss")
    print(article)

asyncio.run(main())
```

## 组件说明

### 主要组件

1. **RSSArticleWorkflow**
   - 协调整个文章生成流程的工作流
   - 负责整合RSS过滤、内容提取和文章撰写等步骤

2. **RSSFilterAgent**
   - 负责处理和分析RSS源
   - 筛选出有价值的技术文章

3. **ArticleWriterAgent**
   - 基于收集的信息撰写完整的技术文章
   - 生成包含引言、主体和结论的结构化文章

4. **WebContentExtractor**
   - 用于从网页中提取主要文本内容
   - 过滤掉广告、导航栏等无关内容
   - 优先从`<main>`标签中提取内容
   - 支持代理设置，解决网络访问限制问题

## 注意事项

- 需要安装requests和BeautifulSoup4库：`pip install requests beautifulsoup4`
- 某些网站可能需要设置代理才能正常访问，可以通过环境变量`HTTP_PROXY`和`HTTPS_PROXY`设置
- 默认使用7890端口的本地代理，如需修改，请编辑`main.py`中的代理设置

## 扩展与自定义

1. 修改RSS源过滤标准:
   - 编辑`app/rss_writer/agents/rss_filter.py`中的系统提示和评估标准

2. 调整文章撰写风格:
   - 编辑`app/rss_writer/agents/article_writer.py`中的系统提示

git fetch upstream

git merge upstream/main

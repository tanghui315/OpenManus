# video_script_generator/agent.py
import os
import json
import hashlib
from datetime import datetime
from typing import List, Optional, Dict, Any
from urllib.parse import urlparse

# Import base agent and necessary tools from the existing framework
from app.agent.toolcall import ToolCallAgent
# Adjust import path based on your project structure if needed
from app.tool import ToolCollection, WebSearch, FileSaver, Terminate
# Correctly import the WebContentExtractor class
from app.tool.web_extract import WebContentExtractor
from app.tool.base import ToolResult, ToolFailure # Import ToolResult/Failure
from app.schema import Message, AgentState
from app.logger import logger
# Import LLM class for explicit initialization
from app.llm import LLM

# Default tools needed for this agent (WebContentExtractor is NOT a tool here)
DEFAULT_TOOLS = ToolCollection(WebSearch(), FileSaver(), Terminate())

class VideoScriptAgent(ToolCallAgent):
    """
    AI Agent for generating technical video scripts with Manim code snippets.
    Follows a plan: Plan -> Titles -> Section Content (Web Search -> Write -> Manim) -> Save -> Terminate.
    """
    name: str = "video_script_generator_agent"
    description: str = "Generates video scripts for technical topics, including web research and Manim code."

    # Use default tools + any others potentially added
    available_tools: ToolCollection = DEFAULT_TOOLS
    # Override system prompt if needed, or rely on ToolCallAgent's default
    # system_prompt: str = "You are a helpful AI assistant..."

    # Internal state - Use Pydantic fields for proper initialization if needed
    output_dir: str = "outputs"
    cache_dir: str = "cache"
    script_file_path: Optional[str] = None
    plan: Optional[List[str]] = None
    script_content: Dict[str, str] = {} # Stores text content per section title
    current_keywords: str = ""
    web_extractor: Optional[WebContentExtractor] = None
    # Add audience_level attribute and set default value
    audience_level: str = "intermediate"

    def __init__(self, **data: Any):
        # 从传入的 data 中提取 audience_level，如果未提供则使用默认值
        # Let Pydantic handle audience_level via super init and the class default
        super().__init__(**data)

        # Explicitly initialize LLM if not already set
        # This guards against default_factory issues or silent failures
        if self.llm is None:
            logger.warning("LLM instance was not set by superclass/data, attempting explicit initialization.")
            try:
                self.llm = LLM() # Try creating default instance
                logger.info("LLM instance explicitly initialized.")
            except Exception as e:
                logger.error(f"CRITICAL: Failed to explicitly initialize LLM: {e}")
                # Re-raise as a runtime error to halt execution if LLM is essential
                raise RuntimeError(f"LLM initialization failed: {e}") from e

        # Now self.output_dir is properly initialized by Pydantic.
        # We can proceed with logic that uses it.
        self._setup_directories()

        # Instantiate the extractor after base class init
        try:
             self.web_extractor = WebContentExtractor()
             logger.info("WebContentExtractor initialized within agent.")
        except Exception as e:
             logger.error(f"Failed to initialize WebContentExtractor: {e}")
             self.web_extractor = None # Ensure it's None if init fails

    def _setup_directories(self):
        """Sets up output and cache directories."""
        script_dir = os.path.dirname(__file__)
        if not script_dir: script_dir = '.'

        # Use output_dir set during initialization
        self.output_dir = os.path.normpath(os.path.join(script_dir, self.output_dir))
        self.cache_dir = os.path.join(self.output_dir, "cache")

        os.makedirs(self.output_dir, exist_ok=True)
        os.makedirs(self.cache_dir, exist_ok=True)
        logger.info(f"Output directory set to: {self.output_dir}")
        logger.info(f"Cache directory set to: {self.cache_dir}")

    def _generate_filename(self, keywords: str) -> str:
        """Generates a unique filename for the script in the output directory."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_keywords = "".join(c if c.isalnum() else "_" for c in keywords)
        filename = f"script_{safe_keywords}_{timestamp}.md"
        return os.path.join(self.output_dir, filename) # Place directly in output_dir

    async def _call_llm(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Helper function to call the LLM for generation tasks."""
        messages = [Message.user_message(prompt)]
        # Use the agent's system_prompt if available and none is provided
        effective_system_prompt = system_prompt or self.system_prompt
        system_msgs = [Message.system_message(effective_system_prompt)] if effective_system_prompt else []

        try:
            # Use the agent's built-in LLM instance
            response = await self.llm.ask(messages=messages, system_msgs=system_msgs)
            return response or ""
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            return f"Error: LLM call failed - {e}"

    async def _save_to_file(self, content: str, append: bool = False) -> bool:
        """Uses standard Python I/O to write or append content."""
        if not self.script_file_path:
            logger.error("Script file path not set, cannot save.")
            return False
        try:
            # Determine mode ('w' for write, 'a' for append)
            mode = "a" if append else "w"
            # Ensure UTF-8 encoding for broader character support
            encoding = "utf-8"

            # Use standard Python file writing
            with open(self.script_file_path, mode, encoding=encoding) as f:
                f.write(content)

            # Log success (optional, less verbose)
            # logger.info(f"Content {'appended to' if append else 'written to'} {self.script_file_path}")
            return True
        except IOError as e: # Catch specific IO errors
            logger.error(f"Error writing to file {self.script_file_path}: {e}")
            return False
        except Exception as e: # Catch any other unexpected errors
            logger.error(f"Unexpected error saving file {self.script_file_path}: {e}")
            return False

    async def _cached_web_search(self, query: str, num_results: int = 10) -> List[Dict]:
        """
        Performs web search using the WebSearch tool, then uses the initialized
        WebContentExtractor to get content for each URL. Caches the final structured results.
        """
        # Ensure WebSearch tool exists
        if "web_search" not in self.available_tools.tool_map:
            logger.error("WebSearch tool is not available.")
            return []
        # Ensure WebContentExtractor was initialized
        if not self.web_extractor:
             logger.error("WebContentExtractor instance is not available (initialization failed?).")
             return []

        # Use combined hash of query and num_results for cache key
        cache_key_str = f"{query}-{num_results}"
        query_hash = hashlib.md5(cache_key_str.encode('utf-8')).hexdigest()
        cache_path = os.path.join(self.cache_dir, f"{query_hash}.json")

        # Check cache
        if os.path.exists(cache_path):
            try:
                with open(cache_path, 'r', encoding='utf-8') as f:
                    logger.info(f"Cache hit for processed search: {query[:50]}...")
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to read cache file {cache_path}: {e}")

        # --- Cache miss ---
        logger.info(f"Cache miss, executing web search & extraction for: {query[:50]}...")
        structured_results = []

        # 1. Perform Web Search to get URLs
        urls = []
        try:
            tool_input = {"query": query, "num_results": num_results}
            search_result = await self.available_tools.execute(name="web_search", tool_input=tool_input)

            if isinstance(search_result, ToolFailure):
                 logger.error(f"WebSearch tool failed: {search_result.error}")
                 urls = []
            elif isinstance(search_result, ToolResult) and isinstance(search_result.output, list):
                 urls = search_result.output
                 logger.info(f"WebSearch returned {len(urls)} URLs (via ToolResult).")
            elif isinstance(search_result, list):
                 urls = search_result
                 logger.info(f"WebSearch returned {len(urls)} URLs (directly as list).")
            else:
                 logger.warning(f"Unexpected WebSearch result format: {type(search_result)}. Output: {getattr(search_result, 'output', 'N/A')}")
                 urls = []
        except Exception as e:
            logger.error(f"Error executing WebSearch tool: {e}")
            urls = [] # Ensure urls is empty on error

        # 2. Extract content for each URL using the initialized extractor instance
        if urls:
            logger.info(f"Extracting content for {len(urls)} URLs...")
            for item in urls:
                url_to_extract = None
                url_source_description = "" # For logging clarity
                if isinstance(item, dict) and 'url' in item:
                    url_value = item['url']
                    if isinstance(url_value, str): url_to_extract = url_value
                    else: logger.warning(f"Extracted URL value is not a string: {type(url_value)} in item {item}")
                    url_source_description = f"dict item key 'url': {item}"
                elif isinstance(item, str):
                    url_to_extract = item
                    url_source_description = f"string item: {item}"
                else:
                    logger.warning(f"Skipping unknown item type in search results: {type(item)}")
                    continue

                if not url_to_extract or not isinstance(url_to_extract, str):
                     logger.warning(f"Could not determine a valid string URL from search item ({url_source_description})")
                     continue

                # --- ADD ZHIHU SKIP LOGIC HERE ---
                try:
                    parsed_uri = urlparse(url_to_extract)
                    if 'zhihu.com' in parsed_uri.netloc:
                        logger.info(f"Skipping content extraction for Zhihu URL: {url_to_extract}")
                        continue # Skip to the next item in the loop
                except Exception as parse_err:
                     logger.warning(f"URL parsing failed for {url_to_extract}: {parse_err}. Attempting extraction anyway.")
                # --- END ZHIHU SKIP LOGIC ---

                # url_to_extract is now more reliably a string AND not a zhihu link
                try:
                    content, metadata = self.web_extractor.extract_content(url_to_extract)
                    structured_results.append({
                        "url": url_to_extract,
                        "title": metadata.get("title", "N/A"),
                        "snippet": content[:2000] + ("..." if len(content) > 2000 else "")
                    })
                except Exception as e:
                    logger.warning(f"WebContentExtractor failed for {url_to_extract}: {e}")
                    structured_results.append({
                        "url": url_to_extract,
                        "title": "Extraction Failed",
                        "snippet": f"Error extracting content: {e}"
                    })

        # 3. Save structured results to cache
        try:
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(structured_results, f, ensure_ascii=False, indent=4)
        except Exception as e:
            logger.error(f"Failed to write cache file {cache_path}: {e}")

        return structured_results

    async def _generate_plan(self):
        """Generates the script plan using LLM, considering the audience level."""
        logger.info(f"Generating plan for keywords: {self.current_keywords}, Level: {self.audience_level}")
        prompt = f"""
        Generate a logical video script plan (list of section titles **in Chinese**) for the technical topic: '{self.current_keywords}', tailored for a **{self.audience_level}** audience.

        Audience Level Guidance:
        - **beginner**: Focus on high-level concepts, analogies, simple definitions, and real-world impact. Avoid deep math or complex code. Use simpler language.
        - **intermediate**: Include core mechanisms, basic principles, relevant comparisons, simple math/code examples where helpful. Assume some technical background.
        - **advanced**: Delve into deeper principles, complex mathematical derivations, algorithm details, nuanced trade-offs, and potentially cutting-edge research aspects. Assume strong technical background.

        Instructions:
        - The plan should follow a logical educational structure (e.g., Intro, Concepts, Examples, Conclusion).
        - **All section titles in the list must be in Chinese (中文).**
        - Mark sections involving math, algorithms, or complex concepts suitable for visualization **at this specific '{self.audience_level}' level** with '(Manim)'. Fewer Manim hints for beginners, potentially more complex ones for advanced.
        - Output ONLY a valid JSON list of strings containing Chinese titles. Example: [\"引言\", \"核心概念一 (Manim)\", \"应用示例\", \"总结\"]
        """
        plan_str = await self._call_llm(prompt)
        try:
            # Attempt to clean the string if it contains markdown code block fences
            cleaned_plan_str = plan_str.strip()
            if cleaned_plan_str.startswith("```json"):
                cleaned_plan_str = cleaned_plan_str[len("```json"):]
            if cleaned_plan_str.startswith("```"): # Handle case where only ``` is present
                cleaned_plan_str = cleaned_plan_str[len("```"):]
            if cleaned_plan_str.endswith("```"):
                cleaned_plan_str = cleaned_plan_str[:-len("```")]

            self.plan = json.loads(cleaned_plan_str.strip()) # Use the cleaned string and strip again
            logger.info(f"Generated Plan: {self.plan}")
        except json.JSONDecodeError:
            logger.error(f"Failed to parse plan JSON after cleaning: {plan_str}") # Log original string on error
            # Fallback plan
            self.plan = [
                f"1. {self.current_keywords} 简介 ({self.audience_level}水平)",
                "2. 核心概念",
                "3. 示例/应用",
                "4. 总结"
            ]
            logger.info(f"Using fallback plan: {self.plan}")

    async def _generate_titles(self):
        """Generates title suggestions using LLM, considering the audience level."""
        logger.info(f"Generating titles for: {self.current_keywords}, Level: {self.audience_level}")
        prompt = f"""
        请根据以下计划为关于 '{self.current_keywords}' 的技术视频生成 3-5 个吸引人的、SEO友好的**中文**视频标题建议。该视频的目标受众是 **{self.audience_level}** 水平。
        计划章节: {self.plan}.
        标题应反映内容的深度和风格。
        请仅输出一个有效的 JSON 字符串列表。例如: ["适合{self.audience_level}的标题 1", "标题 2"]
        """
        titles_str = await self._call_llm(prompt)
        titles = [f"占位符标题 ({self.audience_level}): {self.current_keywords}"] # Fallback in Chinese
        try:
            # --- ADD CLEANING LOGIC HERE ---
            cleaned_titles_str = titles_str.strip()
            if cleaned_titles_str.startswith("```json"):
                cleaned_titles_str = cleaned_titles_str[len("```json"):].strip()
            if cleaned_titles_str.startswith("```"):
                 cleaned_titles_str = cleaned_titles_str[len("```"):].strip()
            if cleaned_titles_str.endswith("```"):
                cleaned_titles_str = cleaned_titles_str[:-len("```")].strip()
            # --- END CLEANING LOGIC ---

            titles_list = json.loads(cleaned_titles_str) # Use cleaned string
            # Ensure titles are strings, handle potential non-string items if necessary
            titles = [str(t) for t in titles_list if t]
            if not titles: # If list becomes empty after cleaning
                raise ValueError("Parsed titles list is empty")
            logger.info(f"Generated Titles: {titles}")
        except (json.JSONDecodeError, ValueError) as e:
             logger.error(f"Failed to parse titles JSON or list empty after cleaning: {e}, response: {titles_str}") # Log original string
             # Keep the Chinese fallback title
             titles = [f"占位符标题 ({self.audience_level}): {self.current_keywords}"]

        title_suggestions = f"## 建议标题 (面向 {self.audience_level}):\n\n" + "\n".join(f"- {title}" for title in titles)
        # Initialize the file with titles
        if not await self._save_to_file(title_suggestions + f"\n\n# 暂定标题: {titles[0]}\n\n", append=False):
             raise IOError("Failed to initialize script file with titles.")

    async def _generate_manim_code(self, section_title: str, section_content: str) -> Optional[str]:
        """Generates Manim code using LLM if needed, potentially considering audience level."""
        needs_manim = "(manim)" in section_title.lower() or any(k in section_content.lower() for k in ["formula", "equation", "visualize", "graph", "plot", "math", "algorithm step", "公式", "方程", "可视化", "图表", "数学", "算法步骤"])
        if not needs_manim:
            return None

        logger.info(f"Attempting to generate Manim code for section: {section_title} (Level: {self.audience_level})")
        prompt = f"""
        Generate Python code using the Manim library to create a visualization for the concept described below related to '{self.current_keywords}'.
        The visualization should be suitable for a **{self.audience_level}** audience (beginner=simple analogy/core idea, intermediate=standard visualization, advanced=more detailed/complex).
        Section Title: {section_title}
        Section Content Context:
        ---
        {section_content[:2000]}...
        ---
        Instructions:
        - Create a complete Manim Scene class.
        - Include necessary imports from `manim`.
        - Adjust complexity based on the '{self.audience_level}' level.
        - Output ONLY the Python code block enclosed in ```python ... ```.
        - If visualization is not feasible or suitable for this level, output only the text "MANIM_SKIP".
        """
        manim_code_block = await self._call_llm(prompt)

        if "MANIM_SKIP" in manim_code_block:
             logger.info(f"LLM indicated Manim code generation should be skipped for this section/level.")
             return None
        elif "```python" in manim_code_block and "class" in manim_code_block and "Scene" in manim_code_block:
            # Extract code from markdown block
            try:
                code = manim_code_block.split("```python")[1].split("```")[0].strip()
                # Basic validation for common Manim imports/classes
                if "from manim import" not in code or "Scene" not in code:
                     logger.warning("Generated Manim code missing standard imports or Scene class.")
                     # Decide if we should return potentially invalid code or None
                     return None # Be stricter: return None if validation fails
                logger.info("Manim code generated successfully.")
                return code
            except IndexError:
                 logger.warning("Could not extract Manim code from LLM response block.")
                 return None
        else:
            logger.warning("LLM output for Manim code doesn't look valid or was skipped.")
            return None

    # Override run instead of think/act for a more self-contained flow
    async def run(self, request: Optional[str] = None) -> str:
        """Overrides the default run method to implement the script generation flow."""
        if not request:
            return "Error: No keywords provided for script generation."
        self.current_keywords = request
        self.state = AgentState.RUNNING
        # Reset internal state from previous runs
        self.plan = None
        self.script_content = {}
        self.script_file_path = None

        logger.info(f"Starting script generation for keywords: {self.current_keywords}, Level: {self.audience_level}")

        try:
            # 1. Setup File Path
            self.script_file_path = self._generate_filename(self.current_keywords)
            logger.info(f"Output script path set to: {self.script_file_path}")

            # 2. Generate Plan
            await self._generate_plan()
            if not self.plan:
                raise ValueError("Failed to generate or fallback to a script plan.")

            # 3. Generate Titles and Initialize File
            await self._generate_titles() # This also saves the initial file content

            # 4. Generate Content for Each Section
            for i, section_title in enumerate(self.plan):
                logger.info(f"\n--- Processing Section {i+1}/{len(self.plan)}: {section_title} ---")

                # a. Web Search & Extract for section context
                search_query = f"{self.current_keywords} {section_title} explanation"
                # Use the updated method that handles both search and extraction
                search_results = await self._cached_web_search(search_query)
                # Use a more detailed summary for the LLM context
                search_summary = "\n".join([f"- Title: {r.get('title', 'N/A')}\n  URL: {r.get('url', '#')}\n  Snippet: {r.get('snippet', 'N/A')}\n" for r in search_results[:5]]) # Top 3 results

                # b. Generate Section Content using LLM (Modified prompt for Chinese)
                previous_summary = "\n".join(f"- {prev_title}: {prev_content[:500].strip()}..." # Slightly more context
                                              for prev_title, prev_content in self.script_content.items())
                content_prompt = f"""
                你正在为一个关于 '{self.current_keywords}' 的技术视频撰写**中文**脚本。目标受众是 **{self.audience_level}** 水平。
                当前章节: '{section_title}'
                先前章节摘要: {previous_summary if previous_summary else '无'}
                本章节相关的网络搜索结果 (提取的片段，仅供参考，请用中文撰写脚本):
                ---
                {search_summary if search_summary else '无可用信息'}
                ---

                任务: 为 '{section_title}' 撰写**中文**旁白脚本，确保内容深度和语言风格适合 **{self.audience_level}** 受众。
                - **beginner**: 使用简单语言、类比，解释核心概念和影响，避免深入技术细节和复杂术语。
                - **intermediate**: 解释核心机制和原理，可包含简化数学或代码示例，假设有一定技术背景。
                - **advanced**: 深入探讨原理、数学推导、算法细节、权衡和前沿研究，使用精确术语。
                - 脚本必须**完全使用中文**，风格口语化适合视频。
                - 与前面章节逻辑连贯，避免不必要的重复。
                - **充分利用**上面提供的网络搜索结果片段中的信息来丰富内容。
                - 旁白中无需引用来源 URL。
                - 请仅输出本章节的**中文**旁白文本。不要包含章节标题本身。
                """
                section_text = await self._call_llm(content_prompt)
                # Basic check if LLM failed
                if section_text.startswith("Error: LLM call failed"):
                     logger.error(f"LLM failed for section '{section_title}', using placeholder.")
                     section_text = f"[生成错误，请稍后重试 {section_title} 的内容]" # Chinese placeholder
                elif not section_text.strip(): # Handle empty response from LLM
                     logger.warning(f"LLM returned empty content for section '{section_title}', using placeholder.")
                     section_text = f"[内容为空 {section_title}]" # Chinese placeholder

                self.script_content[section_title] = section_text.strip() # Store stripped content

                # c. Generate Manim Code (if needed, prompt now includes level)
                manim_code = await self._generate_manim_code(section_title, section_text)

                # d. Append to File
                # Ensure section title is added before the content
                content_to_append = f"## {section_title}\n\n{section_text}\n\n"
                if manim_code:
                    content_to_append += f"### Manim Visualization Code:\n\n```python\n{manim_code}\n```\n\n"

                if not await self._save_to_file(content_to_append, append=True):
                    logger.warning(f"Failed to append content for section '{section_title}' to file.")
                    # Consider if failure here should halt the process

                logger.info(f"--- Finished Section {i+1} --- ")

            # 5. Finalize and Terminate
            final_message = f"脚本生成完成 (面向 {self.audience_level})。最终脚本保存在: {self.script_file_path}" # Add level info
            logger.info(final_message)
            self.state = AgentState.FINISHED
            # # Optionally call Terminate tool if integrated into a larger flow
            # try:
            #      if "terminate" in self.available_tools.tool_map:
            #          await self.available_tools.execute(name="terminate", tool_input={"status": "success"})
            # except Exception as term_e:
            #      logger.warning(f"Failed to execute terminate tool: {term_e}")
            return final_message

        except Exception as e:
            logger.exception(f"An error occurred during script generation: {e}")
            self.state = AgentState.FINISHED
            # # Optionally call Terminate tool on failure
            # try:
            #     if "terminate" in self.available_tools.tool_map:
            #         await self.available_tools.execute(name="terminate", tool_input={"status": "failure"})
            # except Exception as term_e:
            #      logger.warning(f"Failed to execute terminate tool on failure: {term_e}")
            return f"脚本生成过程中发生错误: {e}. 部分结果可能保存在: {self.script_file_path or 'N/A'}" # Chinese error message

        # Note: The `finally` block was removed as state cleanup happens at the start of `run`.

# Example Usage (for testing, can be uncommented and run if needed)
# import logging # Add this import if running standalone
# async def main_example():
#     agent = VideoScriptAgent()
#     # Ensure necessary LLM config (e.g., API key) is set via environment or config file
#     # Load LLM config if needed, e.g., from app.config import config
#     # agent.llm.api_key = config.llm.api_key etc.
#     result = await agent.run("支持向量机 (Support Vector Machine)")
#     print(result)
#
# if __name__ == '__main__':
#     import asyncio
#     # Configure logging if running standalone
#     logging.basicConfig(level=logging.INFO)
#     asyncio.run(main_example())

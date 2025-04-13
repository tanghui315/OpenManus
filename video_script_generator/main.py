import argparse
import os
import asyncio # Import asyncio
# Import the agent
from .agent import VideoScriptAgent # Assuming agent.py is in the same directory

# Make main async
async def main():
    parser = argparse.ArgumentParser(description="AI 技术视频脚本生成器")
    parser.add_argument("keywords", type=str, help="用于生成脚本的技术关键字 (用引号包裹，例如 '支持向量机')")
    parser.add_argument("--output_dir", type=str, default="outputs", help="存放输出脚本和缓存的目录 (相对于脚本位置)")
    # 可以添加更多参数，例如 --target_audience="入门"

    args = parser.parse_args()
    # 设置代理环境变量
    os.environ['HTTP_PROXY'] = 'http://127.0.0.1:7890'
    os.environ['HTTPS_PROXY'] = 'http://127.0.0.1:7890'
    os.environ['http_proxy'] = 'http://127.0.0.1:7890'
    os.environ['https_proxy'] = 'http://127.0.0.1:7890'
    # --- Agent Invocation ---
    print(f"收到关键字: {args.keywords}")
    # Pass the relative output directory path to the agent
    # The agent's __init__ method now handles making the path absolute/correct
    agent = VideoScriptAgent(output_dir=args.output_dir)
    # Call agent.run() instead of agent.generate_script() and await it
    final_message = await agent.run(args.keywords) # Changed method call

    # The run method now returns the final status message
    print(f"\n{final_message}") # Print the message directly

    # Extract path from message if needed for specific actions, but the message is usually sufficient
    # Example logic to extract path (might need adjustment based on exact message format)
    # if "脚本生成完成" in final_message and "保存在:" in final_message:
    #     try:
    #         final_script_path = final_message.split("保存在:")[-1].strip()
    #         abs_script_path = os.path.abspath(final_script_path)
    #         print(f"(文件绝对路径: {abs_script_path})")
    #     except Exception:
    #         pass # Ignore if path extraction fails

    # --- End Agent Invocation ---


if __name__ == "__main__":
    # Run the async main function
    asyncio.run(main())

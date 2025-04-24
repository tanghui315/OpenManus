# video_script_generator/test_zhihu_extract.py
import sys
import os
import asyncio
import logging

# Adjust path to import from the parent directory's app module
# This assumes the script runs from the OpenManus root directory using python -m
# Or adjusts path dynamically
current_dir = os.path.dirname(__file__)
parent_dir = os.path.abspath(os.path.join(current_dir, os.pardir))
sys.path.insert(0, parent_dir)

try:
    from app.tool.web_extract import WebContentExtractor
    from app.logger import logger # Use the existing logger setup
except ImportError as e:
    print(f"Error importing necessary modules: {e}")
    print("Please ensure you run this script from the OpenManus root directory, e.g., using:")
    print("python -m video_script_generator.test_zhihu_extract")
    sys.exit(1)

# Configure logging level if running standalone
logging.basicConfig(level=logging.INFO)

async def test_zhihu():
    # Set proxy env vars for the test, similar to main.py
    # os.environ['HTTP_PROXY'] = 'http://127.0.0.1:7890'
    # os.environ['HTTPS_PROXY'] = 'http://127.0.0.1:7890'
    # os.environ['http_proxy'] = 'http://127.0.0.1:7890'
    # os.environ['https_proxy'] = 'http://127.0.0.1:7890'
    logger.info("Proxy environment variables set for test.")

    extractor = WebContentExtractor()
    # Make sure the URL is correct, corrected the potential typo in the question ID
    target_url = "https://www.zhihu.com/question/6479705811155155"

    logger.info(f"Attempting to extract content from: {target_url}")

    try:
        # Note: extract_content is synchronous, running it directly in the async test function
        # If it were truly blocking, we'd use loop.run_in_executor
        content, metadata = extractor.extract_content(target_url)
        logger.info("Extraction successful!")
        print("\n--- Extracted Data ---")
        print(f"Title: {metadata.get('title', 'N/A')}")
        print(f"Source Type: {metadata.get('content_source', 'N/A')}")
        print(f"Content Length: {len(content)}")
        print("\n--- Content Snippet ---")
        print(content[:1000] + "..." if len(content) > 1000 else content)
        print("\n--------------------")

    except ValueError as e:
        logger.error(f"URL validation error: {e}")
    except Exception as e:
        logger.error(f"Extraction failed: {e}")
        # Print underlying error type if possible
        logger.error(f"Error Type: {type(e)}")

if __name__ == "__main__":
    asyncio.run(test_zhihu())

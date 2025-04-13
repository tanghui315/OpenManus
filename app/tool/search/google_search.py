import os # Import os to read environment variables
from googlesearch import search

from app.tool.search.base import WebSearchEngine


class GoogleSearchEngine(WebSearchEngine):
    def perform_search(self, query, num_results=10, *args, **kwargs):
        """Google search engine."""
        # Determine proxy to use
        # Prefer environment variables, fallback to hardcoded value
        proxy_url = (
            os.environ.get('HTTPS_PROXY')
            or os.environ.get('https_proxy')
            or os.environ.get('HTTP_PROXY')
            or os.environ.get('http_proxy')
            or "http://127.0.0.1:7890" # Hardcoded fallback as requested
        )
        # Ensure it's a valid URL format or None
        if not proxy_url or not proxy_url.startswith(("http://", "https://")):
            proxy_url = None # Set to None if invalid or empty

        # Pass the determined proxy to the search function
        return search(query, num_results=num_results, proxy=proxy_url)

import random
import pandas as pd
from datetime import datetime
from typing import List, Dict, Optional
from crawl4ai import AsyncWebCrawler, CacheMode, BrowserConfig, CrawlerRunConfig
from crawl4ai.extraction_strategy import JsonCssExtractionStrategy

# Configure logging
import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

MAX_RETRIES = 5
CURRENT_DT = datetime.today().strftime('%Y-%m-%d')

class WebBrowseKit:
    def __init__(
            self,
            proxies: Optional[List[str]] = None,
            browser_type: str = "chrome",  # Browser Selection, either "firefox" or "chrome" or "webkit"
            word_count_threshold: int = 200,
            js_code: Optional[str] = None,  # Example: "document.querySelector('button#loadMore')?.click()"
            wait_for: Optional[str] = None,  # Example: "css:.main-loaded"
            schema: Optional[Dict] = None,  # html structure
            max_retries: int = MAX_RETRIES,  # Default maximum retries
    ):
        self.proxies = proxies
        self.browser_type = browser_type
        self.word_count_threshold = word_count_threshold
        self.js_code = js_code
        self.wait_for = wait_for
        self.schema = schema
        self.max_retries = max_retries
        self._initiate_config()
    
    def _initiate_config(self):
        # browser configuration
        self.browser_config = BrowserConfig(
            browser_type=self.browser_type,
            headless=True,
            # proxy=f"http://{random.choice(self.proxies)}" if self.proxies is not None else None,
            verbose=True,
            use_persistent_context=False,
            cookies=None,
            headers=None,
            user_agent="random",
            text_mode=False,
            light_mode=False,
            extra_args=None,
        )  

        # set extraction strategy
        schema = {
            "name": "Articles",
            "baseSelector": "div.article",
            "fields": [
                {"name": "title", "selector": "h2", "type": "text"},
                {"name": "link", "selector": "a", "type": "attribute", "attribute": "href"}
            ]
        }
        extraction = JsonCssExtractionStrategy(schema)

        # crawler configuration
        self.run_config = CrawlerRunConfig(
            extraction_strategy=extraction,
            # Content filtering
            word_count_threshold=200,
            excluded_tags=['form', 'header'],
            exclude_external_links=True,
            # interaction
            js_code="document.querySelector('button#loadMore')?.click()",
            # wait for before extracting content
            wait_for="css:.main-loaded",
            # Content processing
            process_iframes=True,
            remove_overlay_elements=True,
            screenshot=False,
            pdf=False,
            # Cache control
            cache_mode=CacheMode.ENABLED  # Use cache if available
        )

    async def browse_url(self, url: str) -> Dict:
        """Browse a single URL with retries and proxy rotation."""
        retries = 0
        used_proxies = set()

        while retries < self.max_retries:
            try:
                proxy = None
                if self.proxies:
                    available_proxies = list(set(self.proxies) - used_proxies)
                    if not available_proxies:
                        logger.warning("All proxies have been tried and failed.")
                        break
                    # set up proxy
                    proxy_str = random.choice(available_proxies)
                    proxy = f"http://{proxy_str}"
                    used_proxies.add(proxy_str)
                    self.browser_config.proxy = proxy

                async with AsyncWebCrawler(config=self.browser_config) as crawler:
                    result = await crawler.arun(
                        url=url,
                        config=self.run_config
                    )
                    return result

            except Exception as e:
                if self.is_proxy_error(e):
                    retries += 1
                    logger.warning(f"Proxy error with {proxy} on attempt {retries}/{self.max_retries}: {e}")
                else:
                    logger.error(f"Non-proxy error browsing {url}: {e}")
                    return {"url": url, "error": str(e)}

        logger.error(f"Failed to browse {url} after {self.max_retries} retries.")
        return {"url": url, "error": f"Failed after {self.max_retries} retries"}

    # async def browse_urls(self, urls, rotating_proxy=False):
    #     """brose multiple urls
    #     """
    #     browser_config = self.browser_config
    #     results = []
    #     for url in urls:
    #         if rotating_proxy:
    #             browser_config.proxy = f"http://{random.choice(self.proxies)}" if self.proxies is not None else None
    #         try:
    #             async with AsyncWebCrawler(config=browser_config) as crawler:
    #                 result = await crawler.arun(url=url, config=self.run_config)
    #                 results.append(result)
    #         except PlaywrightError as e:
    #             logger.error(f"Error browsing {url} with proxy {browser_config.proxy}: {e}")
    #             results.append({"url": url, "error": str(e)})
    #     return results
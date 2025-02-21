# medium
import re
import time
import json
import random
import requests
import pandas as pd
from bs4 import BeautifulSoup
from typing import List, Optional, Dict

from web_browse_tool import WebBrowseTool

# Configure logging
import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

from database_tool import df_to_sqlite

MAX_RETRIES = 5
MEDIUM_ALTER_URLS = [
    "https://freedium.cfd/",
]
MEMBER_ONLY_MSG = ['member only story', 'Member-only story']
DB_PATH = "/Users/jiezi/Documents/Data/Database"
DB_NAME = "paper_pal.db"
SRCH_TBL_NM = "medium_article_pool"

_useragent_list = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:66.0) Gecko/20100101 Firefox/66.0',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/111.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/111.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/111.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/111.0.0.0 Safari/537.36 Edg/111.0.1661.62',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/111.0'
]


def match_strings_in_text(string_list, long_text):
    """
    Matches a list of strings against a long text, ignoring case and non-alphanumeric characters.
    Args:
        string_list: A list of strings to search for.
        long_text: The long text to search within.
    Returns:
        True / False
    """
    prepared_text = re.sub(r'[^a-zA-Z0-9\s]', '', long_text).lower()
    for string in string_list:
        prepared_string = re.sub(r'[^a-zA-Z0-9\s]', '', string).lower()
        if prepared_string in prepared_text:
            return True
    return False

def extract_medium_metadata(html_text):
    """extract medium metadata from html text"""
    soup = BeautifulSoup(html_text, 'html.parser')
    metadata = {}
    # 1. Title
    title_tag = soup.select_one('meta[name="title"]')
    metadata['title'] = title_tag['content'] if title_tag else None

    # 2. Description
    description_tag = soup.select_one('meta[name="description"]')
    metadata['description'] = description_tag['content'] if description_tag else None

    # 3. Author
    author_name = soup.select_one('meta[name="author"]')
    author_url = soup.find('meta', property='article:author') 
    metadata['author'] = author_name['content'] if author_name else None
    metadata['author_url'] = author_url['content'] if author_url else None

    # 4. URL (og:url)
    article_url_tag = soup.find('meta', property='og:url')
    metadata['article_url'] = article_url_tag['content'] if article_url_tag else None

    # 5. Image URL (og:image)
    image_url_tag = soup.find('meta', property='og:image')
    metadata['image_url'] = image_url_tag['content'] if image_url_tag else None

    # 6. Publication name (twitter:site)
    publication_tag = soup.find('meta', property='twitter:site')
    metadata['publication'] = publication_tag['content'] if publication_tag else None

    # 7. Publication date 
    script_tag = soup.find('script', type='application/ld+json')
    if script_tag:
        script_data = json.loads(script_tag.string)
        metadata['published_at'] = script_data.get('datePublished') if script_data.get('datePublished') else script_data.get('dateModified')
    else:
        metadata['published_at'] = None

    # 8. Get the tags of the article
    metadata['tags'] = []
    tag_script_tag = soup.find('script', id='preact-tags')
    if tag_script_tag:
        tag_script_data = json.loads(tag_script_tag.string)
        for tag_data in tag_script_data['tags']:
            metadata['tags'].append(tag_data['name'])

    # 9. Get the reading time
    reading_time = soup.select_one('meta[name="twitter:data1"]')
    metadata['reading_time'] = reading_time['content'] if reading_time else None
    return metadata

def exact_medium_content(html_text):
    """extract medium content from html text"""
    soup = BeautifulSoup(html_text, 'html.parser')
    article_content = soup.find('article')
    div_content = soup.find('div', class_='main-content')
    content = article_content if article_content is not None else div_content

    if not content:
        logging.warning(f"Could not find the main article content. Medium's structure might have changed.")
        return None
    else:
        markdown_text = ""
        for element in content.find_all(['h1', 'h2', 'h3', 'h4', 'p', 'pre', 'blockquote', 'figure', 'ol', 'ul', 'hr', 'a', 'img'], recursive=True):
            if element.name == 'h1':
                markdown_text += f"# {element.get_text().strip()}\n\n"
            elif element.name == 'h2':
                markdown_text += f"## {element.get_text().strip()}\n\n"
            elif element.name == 'h3':
                markdown_text += f"### {element.get_text().strip()}\n\n"
            elif element.name == 'h4':
                markdown_text += f"#### {element.get_text().strip()}\n\n"
            elif element.name == 'p':
                markdown_text += f"{element.get_text().strip()}\n\n"
            elif element.name == 'pre':
                # Extract code block assuming it's within <pre><code>...</code></pre>
                code_block = element.find('code')
                if code_block:
                    # Replace problematic characters within code blocks (e.g., <, >)
                    code_text = code_block.get_text().strip()
                    code_text = code_text.replace("&lt;", "<").replace("&gt;", ">") 
                    markdown_text += f"`\n{code_text}\n`\n\n"
                else:
                    markdown_text += f"`\n{element.get_text().strip()}\n`\n\n"
            elif element.name == 'blockquote':
                markdown_text += f"> {element.get_text().strip()}\n\n"
            elif element.name == 'figure':
                # Handle images and captions
                img = element.find('img')
                caption = element.find('figcaption')
                if img:
                    img_src = img.get('src')
                    alt_text = img.get('alt', '')
                    markdown_text += f"![{alt_text}]({img_src})\n"
                if caption:
                    markdown_text += f"> {caption.get_text().strip()}\n"
                markdown_text += "\n"
            elif element.name == 'ol':
                items = element.find_all('li')
                for i, item in enumerate(items):
                    markdown_text += f"{i+1}. {item.get_text().strip()}\n"
                markdown_text += "\n"
            elif element.name == 'ul':
                for item in element.find_all('li'):
                    markdown_text += f"* {item.get_text().strip()}\n"
                markdown_text += "\n"
            elif element.name == 'hr':
                markdown_text += "---\n\n"
            elif element.name == 'a':
                href = element.get('href')
                text = element.get_text().strip()
                if href:
                    markdown_text += f"[{text}]({href})"
                else:
                    markdown_text += text
            elif element.name == 'img':
                img_src = element.get('src')
                alt_text = element.get('alt', '')
                if img_src:
                    markdown_text += f"![{alt_text}]({img_src})"

        # Clean up extra whitespace (optional)
        markdown_text = re.sub(r'\n\s*\n', '\n\n', markdown_text)
        return markdown_text

class MediumKit:
    def __init__(
            self, 
            proxy_list: Optional[List[str]] = None, 
            user_agents: Optional[List[str]] = None, 
            timeout: int = 10, 
            max_retries: int = MAX_RETRIES, 
            ssl_verify: bool = True,
            db_path=None,
            db_name=None,
            table_name=None):
        self.user_agents = user_agents if user_agents else _useragent_list
        self.proxies = proxy_list if proxy_list else None
        self.timeout = timeout
        self.max_retries = max_retries
        self.ssl_verify = ssl_verify
        self.session = requests.Session()  # Create a session object
        self.session.headers.update({"User-Agent": random.choice(self.user_agents)})
        self.current_proxy_index = 0
        if self.proxies:
            self.current_proxy = self.proxies[self.current_proxy_index]
            self.session.proxies = {'http': self.current_proxy}
        self.session.verify = self.ssl_verify
        self.db_path = db_path
        self.db_name = db_name
        self.table_name = table_name
    
    def _set_next_proxy(self):
        """Selects the next proxy in order and updates the session. Removes unavailable proxies."""
        if self.proxies:
            self.proxies.remove(self.current_proxy)
            if not self.proxies:
                self.current_proxy = None
                self.session.proxies = {}
                logging.info("No more proxies available. Proceeding without a proxy.")
                return
            self.current_proxy_index = (self.current_proxy_index + 1) % len(self.proxies)
            self.current_proxy = self.proxies[self.current_proxy_index]
            self.session.proxies = {'http': self.current_proxy}
            logging.info(f"Using next proxy: {self.current_proxy}")
        else:
            logging.info("No proxies configured.")

    def _retrieve(self, url: str) -> Optional[str]:
        """Retrieves the content of a Medium article based on URL using the session.
        Args:
            url: The URL of the Medium article.
        Returns:
            List of dictionaries containing metadata and content of the article.
        """
        try:
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
            if response.status_code == 200:
                medium_metadata = extract_medium_metadata(response.content)
                medium_content = exact_medium_content(response.content)
                return {**medium_metadata, **{'article_content': medium_content}}
        except requests.exceptions.RequestException as e:
            logging.error(f"Request failed for {url}: {e}")
            if self.proxies:
                logging.info(f"Removing proxy {self.current_proxy} due to connection failure.")
            return None
            
    async def _browse(self, url):
        """Retrieves the content of a Medium article based on URL using the session.
        Args:
            url: The URL of the Medium article.
        Returns:
            article: ddictionaries containing metadata and content of the article.
        """
        try:
            browser = WebBrowseTool(self.proxies, browser_type="chrome")
            web_content = await browser.browse_url(url=url)
            medium_metadata = extract_medium_metadata(web_content.html)
            medium_content = exact_medium_content(web_content.html)
            return {**medium_metadata, **{'article_content': medium_content}}
        except Exception as e:
            logging.error(f"Error occurred while browsing {url}: {e}")
            return None
    
    def _retrieve_approach(self, url):
        """"try alternative urls to retrieve information"""
        article = self._retrieve(url)
        for alter_url in MEDIUM_ALTER_URLS:
            if article is not None:
                medium_markdown = article.get('article_content', '')
                member_only_flag = match_strings_in_text(MEMBER_ONLY_MSG, article.get('article_content', ''))
                if len(medium_markdown) < 200 and member_only_flag == False:
                    medium_markdown = self._retrieve(alter_url + url)
                else:
                    break
        return article
    
    async def _browse_approach(self, url):
        """"try alternative urls to browse information"""
        article = await self._browse(url)
        for alter_url in MEDIUM_ALTER_URLS:
            if article is not None:
                medium_markdown = article.get('article_content', '')
                member_only_flag = match_strings_in_text(MEMBER_ONLY_MSG, articles.get('article_content', ''))
                if len(medium_markdown) < 200 and member_only_flag == False:
                    medium_markdown = self._browse(alter_url + url)
                else:
                    break
        return article

    async def get_medium_content(self, url: str) -> Optional[str]:
        """Gets Medium content through various means.
        Args:
            url: The URL of the Medium article.
        Returns:
            The Markdown content of the article, or None if retrieval failed.
        """
        error_count = 0
        while error_count < self.max_retries:
            try:
                articles = self._retrieve_approach(url)
                if articles is not None:
                    return articles
                else:
                    logging.warning(f"Failed to retrieve content from {url} (retrieve approach)")
                    error_count += 1
                    self._set_next_proxy() # change to a new proxy
            except Exception as e:
                logging.error(f"Error occurred while connecting to {url}: {e}")
                error_count += 1
                self._set_next_proxy()
            try:
                articles = await self._browse_approach(url)
                if articles is not None:
                    return articles
                else:
                    logging.warning(f"Failed to retrieve content from {url} (browse approach)")
                    error_count += 1
            except Exception as e:
                logging.error(f"Error occurred while browsing {url}: {e}")
                error_count += 1
            time.sleep(5)  # Delay before retrying
        logging.error(f"Max retries exceeded ({self.max_retries}). Connection terminated.")
        return None

    def save_medium_articles(self, articles: List[Dict]):
        """"""
        df = pd.DataFrame(articles)
        # save search results to search pool
        db_name = self.db_path + '/' + self.db_name
        table_name = self.table_name
        df_to_sqlite(df, table_name, db_name, if_exists='append')
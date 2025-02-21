
# reddit_tool.py
# TO-DO: 
# 1. save intermediate results
# 2. add async functions

import praw  # pip install praw https://github.com/praw-dev/praw?tab=readme-ov-file, doc from https://praw.readthedocs.io/en/stable/getting_started/quick_start.html
import pandas as pd
from praw.models import MoreComments
from typing import Dict, List

from database_tool import df_to_sqlite

import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

DB_PATH = "/Users/jiezi/Documents/Data/Database"
DB_NAME = "paper_pal.db"
REDIT_TBL_NM = "reddit_thread_pool"

def dfs_comments(comment, level, all_comments):
    """
    Depth-first traversal to extract comments in Markdown format with indentation.

    Args:
        comment: The current comment being processed.
        level: The depth level of the comment (0 for top-level, 1 for replies, etc.).
        all_comments: A list to store the formatted comments.
    """
    if isinstance(comment, MoreComments):
        return

    try:
        author_name = comment.author.name if comment.author else "[deleted]"
    except AttributeError:
        author_name = "[deleted]"

    indent = "    " * level
    all_comments.append(f"{indent}- [{author_name}]: {comment.body}")

    for reply in comment.replies:
        dfs_comments(reply, level + 1, all_comments)

class RedditKit:
    def __init__(
            self, 
            client_id, 
            client_secret, 
            user_agent, 
            username=None, 
            password=None,
            db_path=DB_PATH,
            db_name=DB_NAME,
            table_name=REDIT_TBL_NM):
        """Initialize the RedditKit object.
        Args:
            client_id (str): The Reddit API client ID.
            client_secret (str): The Reddit API client secret.
            user_agent (str): The user agent string, format like # "firefox:app_name:version (by /u/user_name)" 
            username (str): The Reddit username. (no need for read-only)
            password (str): The Reddit password. (no need for read-only)
        """
        self.db_path = db_path
        self.db_name = db_name
        self.table_name = table_name

        self.reddit = praw.Reddit(
            client_id=client_id,        
            client_secret=client_secret,  
            user_agent=user_agent, 
            username=username,  # no need for read-only
            password=password  # no need for read-only
        )
        
    def retrieve_thread(self, url=None, submission_id=None):
        """Retrieve a post from Reddit.
        Args:
            url (str): The URL of the post.
            submission_id (str): The ID of the post.
        Returns:
            thread: dict of thread information (including id, author, title, text, comments, etc.)
        """
        try:
            if url:
                submission = self.reddit.submission(url=url)
            elif submission_id:
                submission = self.reddit.submission(submission_id=submission_id)

            thread = {
                "id": submission.id, 
                "title": submission.title, 
                "author": submission.author.name if submission.author is not None else None, 
                "url": submission.url,
                "content": submission.selftext,
                "created_utc": submission.created_utc,
                "num_comments": submission.num_comments,
                "score": submission.score,
                "upvote_ratio": submission.upvote_ratio,
                "distinguished": submission.distinguished
                }

            submission.comments.replace_more(limit=None)
            all_comments = []
            for top_level_comment in submission.comments:
                dfs_comments(top_level_comment, 0, all_comments)

            # for comment_str in all_comments:
            #     print(comment_str)
            thread['comment'] = "\n".join(all_comments)
            return thread
        except Exception as e:
            print(e)
            return None
        
    def search_thread(self, query, subreeeits=None, sort="relevance", time_filter="all", with_comments=False):
        """Search from subreddits for threads.
        Args:
            subreeeits: (list of str) The subreddits to search in. (default: "all").
            query: (str) The query string to search for.
            sort: (str) Can be one of: "relevance", "hot", "top", "new", or "comments". (default: "relevance").
            time_filter: (str) Can be one of: "all", "day", "hour", "month", "week", or "year" (default: "all").
            with_comments: (bool) whether extract comments from thread
        
        """
        if subreeeits is None:
            subreeeits = ['all']
        
        search_results = self.reddit.subreddit('+'.join(subreeeits)).search(query=query, sort=sort, time_filter=time_filter)
        threads = []
        for item in search_results:
            thread = {
                "id": item.id, 
                "title": item.title, 
                "author": item.author.name if item.author is not None else None,
                "url": item.url,
                "content": item.selftext,
                "created_utc": item.created_utc,
                "num_comments": item.num_comments,
                "score": item.score,
                "upvote_ratio": item.upvote_ratio,
                "distinguished": item.distinguished
                }
            # add commments if with_comments==True
            if with_comments:
                item.comments.replace_more(limit=None)
                all_comments = []
                for top_level_comment in item.comments:
                    dfs_comments(top_level_comment, 0, all_comments)
                thread['comment'] = "\n".join(all_comments)
            threads.append(thread)
        return threads
    
    def save_reddit_threads(self, threads: List[Dict]):
        df = pd.DataFrame(threads)
        # save search results to search pool
        db_name = self.db_path + '/' + self.db_name
        table_name = self.table_name
        df_to_sqlite(df, table_name, db_name, if_exists='append')
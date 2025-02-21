import requests
import pandas as pd
import concurrent.futures
from typing import Dict, List

import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

from database_tool import df_to_sqlite

DFT_MAX_DEPTH = 5  # default max # of comment depth
DFT_MAX_CONCURRENT = 5  # default max # of concurrent iteration of comment tree
DB_PATH = "/Users/jiezi/Documents/Data/Database"
DB_NAME = "paper_pal.db"
HN_TBL_NM = "hackernews_comment_pool"

class HackerNewsKit:
    def __init__(
            self,
            max_depth=DFT_MAX_DEPTH,
            max_concurrent=DFT_MAX_CONCURRENT,
            db_path=DB_PATH,
            db_name=DB_NAME,
            table_name=HN_TBL_NM):
        self.base_url = "https://hacker-news.firebaseio.com/v0/"
        self.max_depth = max_depth
        self.max_concurrent = max_concurrent
        self.db_path = db_path
        self.db_name = db_name
        self.table_name = table_name

    def get_top_stories(self, limit=10):
        """
        Gets the top stories from Hacker News.
        """
        top_stories_ids = requests.get(self.base_url + "topstories.json").json()
        stories = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_concurrent) as executor:
            future_to_story_id = {executor.submit(self.get_story, story_id): story_id for story_id in top_stories_ids[:limit]}
            for future in concurrent.futures.as_completed(future_to_story_id):
                try:
                    story = future.result()
                    stories.append(story)
                except Exception as exc:
                    print(f"Generated an exception: {exc}")
        return stories

    def get_story(self, story_id):
        """
        Gets the details of a specific story.
        """
        response = requests.get(self.base_url + f"item/{story_id}.json")
        response.raise_for_status()  # Raise an exception for bad status codes
        return response.json()

    def get_comments_recursive(self, item_id, max_depth, current_depth=0, seen_ids=None):
        """
        Recursively retrieves comments for a given item.
        """
        if current_depth >= max_depth:
            return []

        if seen_ids is None:
            seen_ids = set()

        if item_id in seen_ids:
            print(f"Circular reference detected for item ID: {item_id}")
            return []
        seen_ids.add(item_id)

        item = self.get_story(item_id)
        if not item or ('deleted' in item and item['deleted']) or ('dead' in item and item['dead']):
            return []

        comments = []

        if item['type'] == 'comment':
            comment_text = f"POSTID:{item.get('id', 'unknown')}  AUTHOR:{item.get('by', 'unknown')}  REPLYTO_POSTID:{item.get('parent', 'unknown')}  COMMENT:\n {item.get('text', '')}"
            comments.append(comment_text)

        if 'kids' in item:
            for kid_id in item['kids']:
                kid_comments = self.get_comments_recursive(
                    kid_id, max_depth, current_depth + 1, seen_ids
                )
                comments.extend(kid_comments)

        return comments

    def get_comments_concurrent(self, item_ids, max_depth, current_depth=0, seen_ids=None):
        """
        Recursively retrieves comments for given item IDs concurrently.
        """
        if current_depth >= max_depth:
            return []  # Corrected return value

        if seen_ids is None:
            seen_ids = set()

        comments = []

        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_concurrent) as executor:
            future_to_item_id = {
                executor.submit(self.get_story, item_id): item_id
                for item_id in item_ids
                if item_id not in seen_ids
            }
            for future in concurrent.futures.as_completed(future_to_item_id):
                item_id = future_to_item_id[future]
                try:
                    item = future.result()
                    if not item or ('deleted' in item and item['deleted']) or ('dead' in item and item['dead']):
                        continue

                    seen_ids.add(item_id)

                    # Directly append to comments
                    if item['type'] == 'comment':
                        comment_text = f"POSTID:{item.get('id', 'unknown')}  AUTHOR:{item.get('by', 'unknown')}  REPLYTO_POSTID:{item.get('parent', 'unknown')}  COMMENT:\n {item.get('text', '')}"
                        comments.append(comment_text)

                    if 'kids' in item:
                        kid_comments = self.get_comments_concurrent(
                            item['kids'], max_depth, current_depth + 1, seen_ids
                        )
                        comments.extend(kid_comments)

                except Exception as exc:
                    print(f"Item ID {item_id} generated an exception: {exc}")

        return comments

    def get_story_w_comments(self, story_id, retrieve_type='concurrent'):
        """
        Gets the details of a specific story with comments.
        """
        story = self.get_story(story_id)
        if story:
            if retrieve_type == 'recursive':
                story['comments'] = self.get_comments_recursive(story_id, max_depth=self.max_depth)
            elif retrieve_type == 'concurrent':
                story['comments'] = self.get_comments_concurrent(
                    [story_id], max_depth=self.max_depth
                )
            else:
                raise ValueError(f"Invalid retrieve_type: {retrieve_type}")
        else:
            story['comments'] = []
        return story
    
    def save_hn_stories(self, stories: List[Dict]):
        df = pd.DataFrame(stories)
        df['time'] = pd.to_datetime(df['time'], unit='s')  # convert unix timestamp to datetime
        df['time'] = df['time'].dt.strftime('%Y-%m-%d')  # format datetime
        # save search results to search pool
        db_name = self.db_path + '/' + self.db_name
        table_name = self.table_name
        df_to_sqlite(df, table_name, db_name, if_exists='append')
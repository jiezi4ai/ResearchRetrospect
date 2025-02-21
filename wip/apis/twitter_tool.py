# twitter_tool.py
# TO-DO: 
# 1. save intermediate results
# 2. improve async_get_tweets_by_id
# 3. add async functions
# 4. extract user, tweet objects

import time
import datetime
import asyncio
import random
import requests
import pandas as pd
from typing import Dict, List, Optional

import twikit  # pip install twikit https://github.com/d60/twikit
from tweeterpy import TweeterPy  #   pip install tweeterpy https://github.com/iSarabjitDhiman/TweeterPy


# Configure logging
import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

MAX_RETRIES = 5
BACKOFF_FACTOR = 0.5
X_ALTER_URL = "https://xapi.betaco.tech/x-thread-api?url="

class TwitterKit:
    def __init__(
            self, 
            proxy_list, 
            x_login_name: Optional[str]=None,
            x_password: Optional[str]=None,
            x_login_email: Optional[str]=None,
            max_retires: Optional[int] = 5
        ):
        """
            tweeterpy_clients_usage: client / proxy usage information
                proxy: proxy used
                initiate_tm: client first initiated
                last_call_tm: client last called with API usage
                remaining_requests: remaining usage cnt
                next_reset_tm: rate limit next reset time



        """
        self.x_login_name = x_login_name
        self.x_password = x_password
        self.x_login_email = x_login_email
        self.max_retires = max_retires

        self.tweeterpy_clients_usage = [{'proxy': proxy} for proxy in proxy_list]  # save client / proxy usage information
        self.bad_proxies = set()
        self.current_proxy = None

    def _load_tweeterpy_client(self):
        """"load tweeterpy client"""
        flag = 0
        self.tweeterpy_clients = None
        self.current_proxy = None

        for idx, client_uage in enumerate(self.tweeterpy_clients_usage):
            if (client_uage.get('is_bad_proxy', False) == True 
                or (client_uage.get('remaining_requests', 20) <= 0 and client_uage.get('next_reset_tm') > int(time.time()))):
                continue
            else:
                try:
                    self.tweeterpy_clients= TweeterPy(
                        proxies={'http': client_uage.get('proxy')}, 
                        log_level="INFO"
                    )
                    test_uid = self.tweeterpy_clients.get_user_id('elonmask')  # test if client works
                    client_uage['initiate_tm'] = int(time.time())
                    self.current_proxy = client_uage['proxy']
                    flag = 1
                    break
                except Exception as e:
                    logging.warning(f"Failed to create TweeterPy client with proxy {client_uage['proxy']}: {e}")
                    client_uage['is_bad_proxy'] = True
        if flag == 0:
            logging.error(f"Exhausted all proxies and still could not establish TweeterPy client.")


    def get_userid(self, username):
        """Get user ID based on user name (screen name like 'elonmusk')."""
        try:
            return self.tweeterpy_clients.get_user_id(username)
        except Exception as e:
            self._load_tweeterpy_client()
        return None


    def get_userdata(self, username):
        """get user profile based on user name (screen name like 'elonmusk')
        Args:
            username (str): user name (screen name like 'elonmusk')
        """
        try:
            return self.tweeterpy_clients.get_user_data(username)
        except Exception as e:
            self._load_tweeterpy_client()
        return None


    def get_tweet_by_id(self, tweet_id):
        """Retrieves a tweet, first trying TweeterPy and then falling back to a direct API request.
        Args:
            username (str): user name (screen name like 'elonmusk')
            tweet_id (str): status id of tweet url
        Returns:
            tweet_dct (dict): information including tweet, user, and api usage
        Usage:
            id = tweet_dct.get('rest_id')  # tweet_id
            usage_data = tweet_dct.get('api_rate_limit')  # for api rate limit information
            tweet_info= tweet_dct.get('data', {}).get('tweetResult', {}).get('result', {})
            tweet_user_data = tweet_info.get('core', {}).get('user_results', {}).get('result', {})  # for user info
            tweet_data = tweet_info.get('legacy')  # for tweet info
        """
        try:
            tweet = self.tweeterpy_clients.get_tweet(tweet_id)
            api_limit = tweet.get('api_rate_limit', {})

            # update client usage info
            idx = [x['proxy'] for x in self.tweeterpy_clients].loc(self.current_proxy)
            self.tweeterpy_clients[idx]['last_call_tm'] = int(time.time())
            self.tweeterpy_clients[idx]['remaining_requests'] = api_limit.get('remaining_requests_count')
            self.tweeterpy_clients[idx]['next_reset_tm'] = int((datetime.datetime.now() + api_limit.get('reset_after_datetime_object').timestamp()))

            return tweet
        
        except Exception as e:
            self._load_tweeterpy_client()
        return None


    def get_tweets_by_user(self, username, total=20):
        """get user tweets based on user name (screen name like 'elonmusk')
        Args:
            username (str): user name (screen name like 'elonmusk')
        """
        try:
            user_tweets = self.tweeterpy_clients.get_user_tweets(username, total=total)
            api_limit = user_tweets.get('api_rate_limit', {})

            # update client usage info
            idx = [x['proxy'] for x in self.tweeterpy_clients].loc(self.current_proxy)
            self.tweeterpy_clients[idx]['last_call_tm'] = int(time.time())
            self.tweeterpy_clients[idx]['remaining_requests'] = api_limit.get('remaining_requests_count')
            self.tweeterpy_clients[idx]['next_reset_tm'] = int((datetime.datetime.now() + api_limit.get('reset_after_datetime_object').timestamp()))

            return user_tweets
        
        except Exception as e:
            self._load_tweeterpy_client()
        return None


    # second approach by utilizing twikit package, which requires x_username, x_password, x_email
    async def _load_twikit_client(self):
        """"twikit require twitter account name, email and password"""
        if self.x_login_name and self.x_password and self.x_login_email:
            try:
                self.twikit_client = twikit.Client('en-US')
                await self.twikit_client.login(
                        auth_info_1=self.x_login_name ,
                        auth_info_2=self.x_login_email,
                        password=self.x_password
                    )
            except Exception as e:
                logging.error(f"Failed to initiate twkit! Please double check your x_login_name / x_login_email / x_password.")
                self.twikit_client = None


    async def twikit_get_tweet_by_ids(tweet_id: Optional[List[str]]):
        """Retrieve multiple tweets by IDs."""
        return asyncget_tweets_by_ids(ids: list[str]
        


    # yet another approach to get tweet by user naem and tweet id (not recommended)
    def scrape_tweet_by_id(self, username, tweet_id):
        """scrape tweet using alternative urls
        Args:
            username (str): user name (screen name like 'elonmusk')
            tweet_id (str): status id of tweet url
        Returns:
            tweet_dcts (list of dict): 
                  a simplified version of tweet dicts, including only author, text, tweet_id, timestamp, media, links.
                  include multiple tweet under same user.
                  sample refere to 'https://xapi.betaco.tech/x-thread-api?url=https://x.com/ulriklykke/status/1879549567278203364'
        """
        def _scrape_tweet_by_id_inner(proxy, username, tweet_id):
           try:
                session = self._get_session(proxy)
                link = f"{X_ALTER_URL}https://x.com/{username}/status/{tweet_id}"
                custom_headers = {"User-Agent": random.choice(self.user_agents)}
                response = session.get(
                    url=link,
                    headers=custom_headers,
                    timeout=self.timeout,
                    verify=self.ssl_verify
                )
                response.raise_for_status()  # Raise an exception for bad status codes (4xx or 5xx)
                return response.json()
           except requests.exceptions.RequestException as e:
                logging.error(f"Direct API request failed using proxy {proxy}: {e}")
                raise  # Re-raise to trigger retry in _make_request   
        return self._make_request(_scrape_tweet_by_id_inner, username, tweet_id) 
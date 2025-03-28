# twitter_tool.py
# TO-DO: 
# 1. save intermediate results
# 2. add async functions
# 3. extract user, tweet objects

# TODO: Twikit could easily causing account ban

import time
import datetime
import random
import requests
from typing import Dict, List, Optional, Set, Literal

import twikit  # pip install twikit https://github.com/d60/twikit
from tweeterpy import TweeterPy  #   pip install tweeterpy https://github.com/iSarabjitDhiman/TweeterPy

# Configure logging
import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

MAX_RETRIES = 5
BACKOFF_FACTOR = 0.5
RESET_TIME_INTERVAL = 900  # rate limit reset time interval in seconds
RATE_LIMIT = 50  # number of rate limit (# of calls)
OVERALL_RATE_LIMIT = 600  # overall rate limit of a day
X_ALTER_URL = "https://xapi.betaco.tech/x-thread-api?url="



# for data alignment purpose
def align_tweeterpy_acct_data(tweeterpy_acct_data):
    """process acct information from TweeterPy"""
    acct_info = tweeterpy_acct_data.get('legacy')
    
    # generate new keys
    acct_info['_client'] = 'tweeterpy_client'
    acct_info['id'] = tweeterpy_acct_data.get('rest_id')
    acct_info['is_blue_verified'] = tweeterpy_acct_data.get('is_blue_verified')
    acct_info['urls'] = tweeterpy_acct_data.get('legacy', {}).get('entities', {}).get('url', {}).get('urls')
    acct_info['description_urls'] = tweeterpy_acct_data.get('legacy', {}).get('entities', {}).get('description', {}).get('urls')
    
    # rename keys
    keys_mapping = {'profile_image_url_https': 'profile_image_url', 
                    'pinned_tweet_ids_str': 'pinned_tweet_ids',
                    'friends_count': 'following_count'}
    acct_info = rename_key_in_dict(acct_info, keys_mapping)

    # drop keys
    delete_keys = ['entities', 'profile_interstitial_type']
    acct_info = remove_key_values(acct_info, delete_keys)

    return acct_info

def align_tweeterpy_tweet_data(tweeterpy_tweet_data):
    # tweeterpy_tweet_data = result.get('data', {}).get('tweetResult', {}) or result.get('data', {}).get('tweetResults', {})
    info = tweeterpy_tweet_data.get('result', {})

    # for acct info
    acct_data = info.get('core', {}).get('user_results', {}).get('result', {})
    acct_data = align_tweeterpy_acct_data(acct_data)

    # for tweet info
    tweet_data = info.get('legacy')
    tweet_data['id'] = info.get('rest_id')

    return tweet_data, acct_data

def align_twikit_acct_data(twikit_acct_data):
    """process acct information from Twikit"""
    twikit_acct_info = twikit_acct_data.__dict__
    twikit_acct_info['_client'] = 'twikit_client'
    delete_keys = ['can_dm', 'can_media_tag', 'can_media_tag', 'want_retweets', 'protected']
    acct_info = remove_key_values(twikit_acct_info, delete_keys)
    return acct_info

def align_twikit_tweet_data(twikit_tweet_data):
    info = twikit_tweet_data.__dict__.get('_data', {})

    acct_data = info.get('core', {}).get('user_results', {}).get('result', {})
    acct_data = align_tweeterpy_acct_data(acct_data)
    acct_data['_client'] = 'twikit_client'
    keys_to_delete = ['following', 'can_dm', 'can_media_tag', 'want_retweets']
    acct_data = remove_key_values(acct_data, keys_to_delete)

    tweet_data = info.get('legacy', {})
    reply_to = twikit_tweet_data.__dict__.get('reply_to', [])
    if reply_to:
        in_reply_to_status_id_str = reply_to.__dict__.get('_data', {}).get('rest_id')
        in_reply_to_user_id_str = reply_to.__dict__.get('_data', {}).get('core', {}).get('rest_id')
        in_reply_to_screen_name = reply_to.__dict__.get('_data', {}).get('core', {}).get('user_results', {}).get('result', {}).get('legacy', {}).get('screen_name')
        tweet_data['in_reply_to_status_id_str'] = in_reply_to_status_id_str
        tweet_data['in_reply_to_user_id_str'] = in_reply_to_user_id_str
        tweet_data['in_reply_to_screen_name'] = in_reply_to_screen_name
        
    tweet_data['id'] = info.get('rest_id')
    return tweet_data, acct_data


class TwitterKit:
    def __init__(
            self, 
            proxy_list, 
            twikit_cookies_path: Optional[str]=None,
            x_login_name: Optional[str]=None,
            x_password: Optional[str]=None,
            x_login_email: Optional[str]=None,
            max_retires: Optional[int] = MAX_RETRIES
        ):
        """initiate twitter tools and set up parameters
        Args:
            proxy_lst: list of proxies in format like 'ip_addr:port'. support http proxies for now.
            x_login_name, x_password, x_login_email: X related login information. 
        Note:
            1. tweeterpy_client (based on tweeterpy package) is set up to get user id, user data and tweet given specific id.
            2. twikit_client (based on twikit package) is set up to get latest tweets from twitt account, retrieve tweets with replies.
            3. tweeterpy_client does not require login credentials, while twikit_client requires X related login information.
            4. tweeterpy_client is bound to rate limits constraint. It may resort to proxy to get over it.
            5. twikit_client use no proxy, since Twitter detects user's IP and may ban accounts with suspicious IP shifts.
            6. tweeterpy_clients_usage records client / proxy usage information for tweeterpy_client. It includes:
                - proxy: proxy used
                - initiate_tm: client first initiated
                - last_call_tm: client last called with API usage
                - remaining_requests: remaining usage cnt
                - next_reset_tm: rate limit next reset time
        """
        self.twikit_cookies_path = twikit_cookies_path
        self.x_login_name = x_login_name
        self.x_password = x_password
        self.x_login_email = x_login_email
        self.max_retires = max_retires

        self.tweeterpy_clients_usage = [{'proxy': proxy} for proxy in proxy_list]  # save client / proxy usage information
        self.twikit_client_usage = {}
        self.current_proxy = None

    def _load_tweeterpy_client(self, excluded_proxies: Optional[Set]=set()):
        """"load tweeterpy client
        Args:
            excluded_proxies: a set object with excluded proxies. (proxies connetable but may not work for specific function)
        """
        flag = 0

        # iterate all clients for usable one (both with connectable proxy and usage within rate limits)
        for idx, client_uage in enumerate(self.tweeterpy_clients_usage):
            if (client_uage.get('proxy') in excluded_proxies
                or client_uage.get('is_bad_proxy', False) == True   # client with bad proxy
                or (client_uage.get('remaining_requests', 20) <= 0 and client_uage.get('next_reset_tm') > int(time.time()))  # client restricted by rate limit
                ):
                continue
            else:
                try:
                    self.tweeterpy_client= TweeterPy(
                        proxies={'http': client_uage.get('proxy')}, 
                        log_level="INFO"
                    )
                    test_uid = self.tweeterpy_client.get_user_id('elonmask')  # test if client works
                    client_uage['initiate_tm'] = int(time.time())
                    self.current_proxy = client_uage['proxy']
                    flag = 1
                    break
                except Exception as e:
                    logging.warning(f"Failed to create TweeterPy client with proxy {client_uage['proxy']}: {e}")
                    client_uage['is_bad_proxy'] = True

        # no usable client
        if flag == 0:  
            logging.error(f"Exhausted all proxies and still could not establish TweeterPy client.")
            self.tweeterpy_client = None
            self.current_proxy = None


    def get_user_id(self, username) -> str:
        """Get user ID based on user name (screen name like 'elonmusk')."""
        attempt = 0
        excluded_proxies = set()
        while attempt < self.max_retires:
            try:
                uid = self.tweeterpy_client.get_user_id(username)
                return uid
            except Exception as e:
                excluded_proxies.add(self.current_proxy)
                self._load_tweeterpy_client(excluded_proxies)
                attempt += 1
        return None


    def get_user_info(self, username):
        """get user profile based on user name (screen name like 'elonmusk')
        Args:
            username (str): user name (screen name like 'elonmusk')
        Usage:
            uid = user_data.get('rest_id')
            tweet_acct_info = user_data.get('legacy')
        """
        attempt = 0
        excluded_proxies = set()
        while attempt < self.max_retires:
            try:
                user_info = self.tweeterpy_client.get_user_data(username)
                break
            except Exception as e:
                excluded_proxies.add(self.current_proxy)
                self._load_tweeterpy_client(excluded_proxies)
                attempt += 1
        
        # decode user info
        if user_info:
            try:
                return align_tweeterpy_acct_data(user_info)
            except Exception as e:
                print(f"TweeterPy decode error: {e}")
        return None


    def get_tweet_by_id(self, tweet_id):
        """Retrieves a tweet given specific tweet id.
        Args:
            username (str): user name (screen name like 'elonmusk')
            tweet_id (str): status id of tweet url
        Returns:
            tweet_dct (dict): information including tweet, user, and api usage
        Usage:
            tweet_id = tweet_dct.get('rest_id')  # tweet_id
            usage_data = tweet_dct.get('api_rate_limit')  # for api rate limit information
            tweet_info= tweet_dct.get('data', {}).get('tweetResult', {}).get('result', {})
            tweet_user_data = tweet_info.get('core', {}).get('user_results', {}).get('result', {})  # for user info
            tweet_data = tweet_info.get('legacy')  # for tweet info
        """
        attempt = 0
        excluded_proxies = set()
        while attempt < self.max_retires:
            try:
                tweet_info = self.tweeterpy_client.get_tweet(tweet_id)
                api_limit = tweet_info.get('api_rate_limit', {})
                # update client usage info
                idx = [x['proxy'] for x in self.tweeterpy_clients_usage].index(self.current_proxy)
                self.tweeterpy_clients_usage[idx]['last_call_tm'] = int(time.time())
                self.tweeterpy_clients_usage[idx]['remaining_requests'] = api_limit.get('remaining_requests_count')
                self.tweeterpy_clients_usage[idx]['next_reset_tm'] = int((datetime.datetime.now() + api_limit.get('reset_after_datetime_object')).timestamp())
                break
            
            except Exception as e:
                excluded_proxies.add(self.current_proxy)
                self._load_tweeterpy_client(excluded_proxies)
                attempt += 1
        
        # decode tweet info
        if tweet_info:
            try:
                tweet_data, acct_data = align_tweeterpy_tweet_data(tweet_info.get('data', {}).get('tweetResult', {}))
                return tweet_data, acct_data
            except Exception as e:
                print(f"TweeterPy decode error: {e}")
        return None, None


    def get_tweets_by_user(self, username, total=20):
        """get user tweets based on user name (screen name like 'elonmusk').
           Not recommended since the tweets retrived are not arranged in time sequence.
        Args:
            username (str): user name (screen name like 'elonmusk')
        """
        attempt = 0
        excluded_proxies = set()
        while attempt < self.max_retires:
            try:
                user_tweets_info = self.tweeterpy_client.get_user_tweets(username, total=total)
                api_limit = user_tweets_info.get('api_rate_limit', {})
                # update client usage info
                idx = [x['proxy'] for x in self.tweeterpy_clients_usage].index(self.current_proxy)
                self.tweeterpy_clients_usage[idx]['last_call_tm'] = int(time.time())
                self.tweeterpy_clients_usage[idx]['remaining_requests'] = api_limit.get('remaining_requests_count')
                self.tweeterpy_clients_usage[idx]['next_reset_tm'] = int((datetime.datetime.now() + api_limit.get('reset_after_datetime_object')).timestamp())
                break
            
            except Exception as e:
                excluded_proxies.add(self.current_proxy)
                self._load_tweeterpy_client()
                attempt += 1

        # decode tweet info
        if user_tweets_info and len(user_tweets_info) > 0:
            try:
                accts_data, tweets_data = [], []
                for item in user_tweets_info.get('data', []):
                    item_info = item.get('content', {}).get('itemContent')
                    tweet_data, acct_data = align_tweeterpy_tweet_data(item_info.get('tweet_results', {})) 
                    accts_data.append(acct_data)
                    tweets_data.append(tweet_data)
                return tweets_data, accts_data
            except Exception as e:
                print(f"TweeterPy decode error: {e}")
        return None, None
    
    async def _load_twikit_client(self):
        """"twikit require twitter account name, email and password
        Note:
            1. Do not use proxy, since Twitter detects user's IP and may ban accounts with suspicious IP shifts.
            2. Rate limit: overall constraint is 600 posts per day. Also in every 15 minutes:
                    get_latest_timeline	500	HomeLatestTimeline
                    get_timeline	500	HomeTimeline
                    get_list_tweets	500	ListLatestTweetsTimeline
                    get_trends	20000	guide.json
                    get_tweet_by_id	150	TweetDetail
                    get_user_by_id	500	UserByRestId
                    get_user_by_screen_name	95	UserByScreenName
                    get_user_tweets[tweet_type="Tweets"]	50	UserTweets
                    get_user_tweets[tweet_type="Replies"]	50	UserTweetsAndReplies
              More information could be found from: https://github.com/d60/twikit/blob/main/ratelimits.md
            3. Also try to best protect your account: https://github.com/d60/twikit/blob/main/ToProtectYourAccount.md
        """
        if self.twikit_cookies_path:
            try:
                self.twikit_client = twikit.Client('en-US')
                self.twikit_client.load_cookies(self.twikit_cookies_path)
                self.twikit_client_usage['initiate_tm'] = int(time.time())
                self.twikit_client_usage['remaining_requests'] = 50
                self.twikit_client_usage['next_reset_tm'] = int(time.time())+900

            except Exception as e:
                logging.error(f"Failed to initiate twkit! Please double check your cookies file in {self.twikit_cookies_path}.")
                self.twikit_client = None
                self.twikit_client_usage = None

        elif self.x_login_name and self.x_password and self.x_login_email:
            try:
                self.twikit_client = twikit.Client('en-US')
                await self.twikit_client.login(
                        auth_info_1=self.x_login_name ,
                        auth_info_2=self.x_login_email,
                        password=self.x_password
                    )
                self.twikit_client.save_cookies('cookies.json')
                self.twikit_client_usage = {
                    'initiate_tm': int(time.time()),
                    'remaining_requests': 50,
                    'next_reset_tm': int(time.time())+900}
            except Exception as e:
                logging.error(f"Failed to initiate twkit! Please double check your x_login_name / x_login_email / x_password.")
                self.twikit_client = None
                self.twikit_client_usage = None

        else:
            self.twikit_client = None


    async def async_get_user_info(self, screen_nm: Optional[str]=None, uid: Optional[str]=None):
        """get user info through twikit client"""
        attempt = 0
        if screen_nm is None and uid is None:
            return None
        
        while attempt < self.max_retires:
            try:
                if screen_nm is not None:
                    acct_data = await self.twikit_client.get_user_by_screen_name(screen_nm)
                    break
                else:
                    acct_data = await self.twikit_client.get_user_by_id(uid)
                    break
            except:
                attempt += 1
                acct_data = None
                time.sleep(BACKOFF_FACTOR * (2 ** attempt))  # Exponential backoff
        
        if acct_data:
            try:
                return align_twikit_acct_data(acct_data)
            except Exception as e:
                print(f"Twikit data decode error: {e}")
        return None
    

    async def async_get_tweeets_by_ids(self, tweet_ids: Optional[List[str]]):
        """get tweets info given twitter ids through Twikit"""
        attempt = 0
        while attempt < self.max_retires:
            if self.twikit_client_usage.get('remaining_requests', 20) <= 0 and self.twikit_client_usage.get('next_reset_tm') > int(time.time()):
                time_gap = self.twikit_client_usage.get('next_reset_tm') - int(time.time())
                time.sleep(time_gap)
                self.twikit_client_usage['remaining_requests'] = 50
                self.twikit_client_usage['next_reset_tm'] = int(time.time())+900
                continue
            else:
                self.twikit_client_usage['remaining_requests'] -= 1
                self.twikit_client_usage['last_call_tm'] = int(time.time())
                try:
                    tweets_info = await self.twikit_client.get_tweets_by_ids(tweet_ids)
                    break
                except:
                    attempt += 1
                    tweets_info = None
                    time.sleep(BACKOFF_FACTOR * (2 ** attempt))  # Exponential backoff

        if tweets_info:
            try:
                tweets_data, accts_data = [], []
                for item in tweets_info:
                    tweet_data, acct_data = align_twikit_tweet_data(item)
                    tweets_data.append(tweet_data)
                    accts_data.append(acct_data)
                return tweets_data, accts_data
            except Exception as e:
                print(f"Twikit data decode error: {e}")
        return None, None  


    async def async_get_tweets_by_user(self, user_id: str, tweet_type: Literal['Tweets', 'Replies', 'Media', 'Likes'], count: int = 40,):
        """search tweets info by key words through Twikit"""
        attempt = 0
        while attempt < self.max_retires:
            if self.twikit_client_usage.get('remaining_requests', 20) <= 0 and self.twikit_client_usage.get('next_reset_tm') > int(time.time()):
                time_gap = self.twikit_client_usage.get('next_reset_tm') - int(time.time())
                time.sleep(time_gap) 
                self.twikit_client_usage['remaining_requests'] = 50
                self.twikit_client_usage['next_reset_tm'] = int(time.time())+900
                continue
            else:
                self.twikit_client_usage['remaining_requests'] -= 1
                self.twikit_client_usage['last_call_tm'] = int(time.time())
                try:
                    tweets_info = await self.twikit_client.get_user_tweets(user_id, tweet_type, count)
                    break
                except:
                    attempt += 1
                    tweets_info = None
                    time.sleep(BACKOFF_FACTOR * (2 ** attempt))  # Exponential backoff
        
        if tweets_info:
            try:
                tweets_data, accts_data = [], []
                for item in tweets_info:
                    tweet_data, acct_data = align_twikit_tweet_data(item)
                    tweets_data.append(tweet_data)
                    accts_data.append(acct_data)
                return tweets_data, accts_data
            except Exception as e:
                print(f"Twikit data decode error: {e}")


    async def async_search_tweeets(self, query: str, product: Literal['Top', 'Latest', 'Media'], count: int = 20):
        """search tweets info by key words through Twikit"""
        attempt = 0
        while attempt < self.max_retires:
            if self.twikit_client_usage.get('remaining_requests', 20) <= 0 and self.twikit_client_usage.get('next_reset_tm') > int(time.time()):
                time_gap = self.twikit_client_usage.get('next_reset_tm') - int(time.time())
                time.sleep(time_gap) 
                self.twikit_client_usage['remaining_requests'] = 50
                self.twikit_client_usage['next_reset_tm'] = int(time.time())+900
                continue
            else:
                self.twikit_client_usage['remaining_requests'] -= 1
                self.twikit_client_usage['last_call_tm'] = int(time.time())      
                try:
                    tweets_info = await self.twikit_client.search_tweet(query, product, count)
                    break
                except:
                    attempt += 1
                    tweets_info = None
                    time.sleep(BACKOFF_FACTOR * (2 ** attempt))  # Exponential backoff
        
        if tweets_info:
            try:
                tweets_data, accts_data = [], []
                for item in tweets_info:
                    tweet_data, acct_data = align_twikit_tweet_data(item)
                    tweets_data.append(tweet_data)
                    accts_data.append(acct_data)
                return tweets_data, accts_data
            except Exception as e:
                print(f"Twikit data decode error: {e}")
        return None, None  
    

    async def async_get_recommended_tweeets(self, count: int = 20):
        """get recommended tweets from Home -> For You through Twikit"""
        attempt = 0
        while attempt < self.max_retires:
            try:
                tweets_info = await self.twikit_client.get_timeline(count)
                break
            except:
                attempt += 1
                tweets_info = None
                time.sleep(BACKOFF_FACTOR * (2 ** attempt))  # Exponential backoff
        
        if tweets_info:
            try:
                tweets_data, accts_data = [], []
                for item in tweets_info:
                    tweet_data, acctt_data = align_twikit_tweet_data(item)
                    tweets_data.append(tweet_data)
                    accts_data.append(acctt_data)
                return tweets_data, accts_data
            except Exception as e:
                print(f"Twikit data decode error: {e}")
        return None, None  
    

    async def async_get_following_tweeets_info(self, count: int = 20):
        """get recommended tweets from Home -> For You through Twikit"""
        attempt = 0
        while attempt < self.max_retires:
            try:
                tweets_info = await self.twikit_client.get_latest_timeline(count)
                break
            except:
                attempt += 1
                tweets_info = None
                time.sleep(BACKOFF_FACTOR * (2 ** attempt))  # Exponential backoff
        
        if tweets_info:
            try:
                tweets_data, accts_data = [], []
                for item in tweets_info:
                    tweet_data, acctt_data = align_twikit_tweet_data(item)
                    tweets_data.append(tweet_data)
                    accts_data.append(acctt_data)
                return tweets_data, accts_data
            except Exception as e:
                print(f"Twikit data decode error: {e}")
        return None, None  


    # yet another approach to get tweet by user naem and tweet id (not recommended)
    def scrape_tweet_by_id(self, screen_nm, tweet_id, user_agents, timeout:Optional[int]=10, ssl_verify:Optional[bool]=False):
        """scrape tweet using alternative urls
        Args:
            screen_nm (str): user name (screen name like 'elonmusk')
            tweet_id (str): status id of tweet url
        Returns:
            tweet_dcts (list of dict): 
                  a simplified version of tweet dicts, including only author, text, tweet_id, timestamp, media, links.
                  include multiple tweet under same user.
        """
        for _, item in enumerate(self.tweeterpy_clients_usage):
            if item.get('is_bad_proxy', False) == True:
                continue
            
            else:
                session = requests.Session()
                session.proxies = {'http': item.get('proxy')}
                link = f"{X_ALTER_URL}https://x.com/{screen_nm}/status/{tweet_id}"
                if user_agents and len(user_agents) > 0:
                    custom_headers = {"User-Agent": random.choice(user_agents)}
                else:
                    custom_headers = {}
                try:
                    response = session.get(
                        url=link,
                        headers=custom_headers,
                        timeout=timeout,
                        verify=ssl_verify
                    )
                    response.raise_for_status()  # Raise an exception for bad status codes (4xx or 5xx)
                    return response.json()
                except requests.exceptions.RequestException as e:
                    logging.error(f"Direct API request failed using proxy {item.get('proxy')}: {e}")
                    item['is_bad_proxy'] = True
                    time.sleep(3)
                    continue
        return None
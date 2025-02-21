import re
import ast
import datetime
import openreview
from semanticscholar import SemanticScholar

from Project.PaperPal.paper_critiques.llm import zhipu_llm

def search_paper(title, validate=False, limit=1):
    """search paper by title from Semantic Scholar and validate trhough semantic similarity
    """
    # Initialize the Semantic Scholar client
    sch = SemanticScholar()
    result = sch.search_paper(query=title)
    return result

class OpenReview:
    def __init__(self, username, password):
        self.client = openreview.api.OpenReviewClient(
            baseurl='https://api2.openreview.net', 
            username=username, 
            password=password)
        self.venues = self.get_venues()

    def get_venues(self):
        # get venue list
        venues_group = self.client.get_group(id='venues')
        venues = venues_group.members
        return venues
    
    def get_submissions_by_venue(self, venue_id, status='all'):
        # Retrieve the venue group information
        venue_group = self.client.get_group(venue_id)
        
        # Define the mapping of status to the respective content field
        status_mapping = {
            "all": venue_group.content['submission_name']['value'],
            "accepted": venue_group.id,  # Assuming 'accepted' status doesn't have a direct field
            "under_review": venue_group.content['submission_venue_id']['value'],
            "withdrawn": venue_group.content['withdrawn_venue_id']['value'],
            "desk_rejected": venue_group.content['desk_rejected_venue_id']['value']
        }

        # Fetch the corresponding submission invitation or venue ID
        if status in status_mapping:
            if status == "all":
                # Return all submissions regardless of their status
                return self.client.get_all_notes(invitation=f'{venue_id}/-/{status_mapping[status]}')
            
            # For all other statuses, use the content field 'venueid'
            return self.client.get_all_notes(content={'venueid': status_mapping[status]})
        
        raise ValueError(f"Invalid status: {status}. Valid options are: {list(status_mapping.keys())}")    

    def extract_submission_info(self, submission):
        # Helper function to convert timestamps to datetime
        def convert_timestamp_to_date(timestamp):
            return datetime.fromtimestamp(timestamp / 1000).strftime('%Y-%m-%d') if timestamp else None

        # Extract the required information
        submission_info = {
            'id': submission.id,
            'title': submission.content['title']['value'],
            'abstract': submission.content['abstract']['value'],
            'keywords': submission.content['keywords']['value'],
            'primary_area': submission.content['primary_area']['value'],
            'TLDR': submission.content['TLDR']['value'] if 'TLDR' in submission.content else "",
            'creation_date': convert_timestamp_to_date(submission.cdate),
            'original_date': convert_timestamp_to_date(submission.odate),
            'modification_date': convert_timestamp_to_date(submission.mdate),
            'forum_link': f"https://openreview.net/forum?id={submission.id}",
            'pdf_link': f"https://openreview.net/pdf?id={submission.id}"
        }
        return submission_info
    
    def filter_venue_id(self, year, journal_or_conference_name, query):
        """filter venue id for given criteria
        """
        mtched_venues = []

        # matching based on year and journal_or_conference name
        year_pattern = re.compile(r'\b\d{4}\b')
        for venue in self.venues:
            parts = venue.split('/')
            year_match = year_pattern.search(venue)
            if year_match:
                if parts[0] == journal_or_conference_name and year_match.group() == str(year):
                    mtched_venues.append(venue)

        # utilize LLM to match venue
        if len(mtched_venues) == 0:
            # first filter by year
            candidates = []
            for x in reviews.venues:
                year_match = year_pattern.search(x)
                if year_match and year_match.group() == str(year):
                    candidates.append(x)
            # then use LLM match the venues 
            # probaly should convert to strict match
            prompt = """## TASK
            Here are a list of journals and conferences.
            Find all potential matches given the following criteria:
            - the year should be '{year}';
            - the journal or conference name should related to '{venue}';

            ## CANDIDATE LISTS
            {candidates}

            ## OUTPUT FORMAT
            Output only the potential matches in list format and nothing else.
            """.format(year=year, venue=venue, candidates=candidates)

            response = zhipu_llm(sys_prompt=None, qa_promt=prompt)
        return ast.literal_eval(response)
    
    def get_paper_submission(self, title, doi):
        venue_ids = []

        # first find venues for paper
        srch_rslts = search_paper(title)
        if srch_rslts.total > 0:
            paper_info = srch_rslts[0]
            if 'doi' in paper_info['externalIds']:
                doi = paper_info['externalIds']
            venue = paper_info['venue']
            year = paper_info['year']
            
            venue_ids = self.filter_venue_id(year, venue, query='')
        
        # then find paper id for venue
        if len(venue_ids) > 0:
            for venue_id in venue_ids:
                submissions = self.get_submissions_by_venue(venue_id, status='all')
                for submission in submissions:
                    if submission.content['title']['value'] == title:
                        return submission
                        break
        return None

    def get_paper_reviews(self, forum_id):
        """get all paper reviews for given forum id"""
        reviews = self.client.get_notes(forum=forum_id)
        sorted_list = sorted(reviews, key=lambda x: x.cdate)
        return sorted_list

    def extract_review_info(self, forum_id): 
        reviews = self.get_paper_reviews(forum_id)

        info = []  # 用于存放基础信息
        chains = [] # 用于存放讨论的信息
        reviewer_conclusion = [] # 用于存放审稿人结论
        author_conclusion = [] # 用于存放作者最终总结
        visited = set()  # 用于存放已经访问过的note id

        root_id = forum_id

        for item in reviews:
            role = item.signatures[0].split('/')[-1]  # 获取角色

            if item.id == root_id and item.replyto is None:
                info.append(item.__dict__)
            
            elif item.replyto == root_id and role == 'Program_Chairs':  # 最终审稿人总结
                reviewer_conclusion.append(item.__dict__)
            
            elif item.replyto == root_id and role == 'Authors':  # 作者最终总结
                author_conclusion.append(item.__dict__)

            elif item.replyto is not None and item.id not in visited:  # 对于每一个元素
                # 检查它隶属于哪一个chain
                for chain in chains:
                    ids = [node['id'] for node in chain]
                    if item.replyto in ids:
                        # 如果找到了，把当前元素添加到这个chain中
                        chain.append(item.__dict__)
                        visited.add(item.id)
                        break
                else:
                    # 如果没有找到，创建一个新的chain
                    chains.append([item.__dict__])
                    visited.add(item.id)
        return {'paper_info':info, 'discussions':chains, 'paper_decision': reviewer_conclusion, 'author_feedbacks': author_conclusion}
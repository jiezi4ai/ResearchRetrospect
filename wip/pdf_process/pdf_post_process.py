# paper pdf post process
# ideally the paper table of content (toc), paper markdown text, paper content list of json are ready
# refer to mineru_tool.py for pdf processing 
import re 
from typing import List, Dict, Optional

import copy
import string
from bs4 import BeautifulSoup
from thefuzz import fuzz # pip install thefuzz  https://github.com/seatgeek/thefuzz

from pdf_process import APPENDDIX_TITLES, IMG_REGX_NAME_PTRN, TBL_REGX_NAME_PTRN, EQT_REGX_NAME_PTRN


def remove_non_text_chars(text, with_digits: Optional[bool]=True):
    """remove non text chars
    """
    valid_chars = string.ascii_letters
    if with_digits == True:
        valid_chars += string.digits  # 包含所有字母和数字的字符串
    cleaned_text = ''
    for char in text:
        if char in valid_chars:
            cleaned_text += char
    return cleaned_text


def text_match(text_a, text_b, with_digits: Optional[bool]=True):
    """"fuzzy match between text_a and text_b"""
    text_a = remove_non_text_chars(text_a, with_digits).lower()
    text_b = remove_non_text_chars(text_b, with_digits).lower()
    return fuzz.ratio(text_a, text_b)


def text_patial_match(shorter_text, longer_text, with_digits: Optional[bool]=True):
    """"partial fuzzy match between text_a and text_b"""
    shorter_text = remove_non_text_chars(shorter_text, with_digits).lower()
    longer_text = remove_non_text_chars(longer_text, with_digits).lower()
    return fuzz.partial_ratio(shorter_text, longer_text)

class PDFProcess:
    def __init__(self, pdf_path, pdf_toc, pdf_json):
        """load pdf related files and data
        Args:
            pdf_path: path to pdf file
            pdf_toc: table of content genreated from PDFOutline class
            pdf_json: json content from MinerU after processing PDF ("_content_list.json")
        """
        self.pdf_path = pdf_path
        self.pdf_toc = pdf_toc
        self.pdf_json = pdf_json

    # match title information from content list to that from PDF ToC
    def align_md_toc(self):
        """match title information from content list to that from PDF ToC"""
        mtched_toc_idx = []
        for idx1, item1 in enumerate(self.pdf_json):  # enumerate content json for titles
            if item1.get('type') == 'text' and item1.get('text_level') is not None:
                item1_page_idx = item1.get('page_idx')
                item1_title = item1.get('text')
                item1_title = re.sub(r"^[A-Za-z]\.", "", item1_title)
                
                pattern = '|'.join(re.escape(title) for title in APPENDDIX_TITLES) 
                if re.search(pattern, item1_title, re.IGNORECASE):
                    item1['type'] = 'title'
                    item1['if_aligned'] = True
                    item1['text_level'] = 1
                    item1['aligned_text'] = item1_title
                    item1['if_appendix'] = True
                    item1['if_collapse'] = False
                    continue

                for idx2, item2 in enumerate(self.pdf_toc):  # enumerate pdf toc 
                    if idx2 not in mtched_toc_idx:
                        item2_title = item2.get('title')
                        item2_title = re.sub(r"^[A-Za-z]\.", "", item2_title)
                        item2_page_idx = item2.get('page')

                        if item1_page_idx == item2_page_idx or item1_page_idx + 1 == item2_page_idx:  # titles of the same page
                            match_ratio = text_match(item1_title, item2_title, False)
                            if match_ratio > 90:  # confirmed title
                                item1['type'] = 'title'
                                item1['if_aligned'] = True
                                item1['text_level'] = item2.get('level')
                                item1['aligned_text'] = f"{item2['nameddest']} {item2_title}"
                                item1['if_appendix'] = item2.get('if_appendix')
                                item1['if_collapse'] = item2.get('if_collapse')
                                mtched_toc_idx.append(idx2)
                                break

    def align_content_json(self):
        """assign ids to images, tables and equations so as to better identify them in text
        Note:
            id: an unique identifier for each image, table and equation
            related_ids: other related ids of images, tables and equation that discussed in context 
        """
        i, j, k = 0, 0, 0
        for item in self.pdf_json:
            if item['type'] in ['image']:
                desc = "\n".join(item.get('img_caption', [])) + "\n" + "\n".join(item.get('img_footnote', []))
                mtch_rslts = re.finditer(IMG_REGX_NAME_PTRN, desc, re.IGNORECASE)

                img_ids = []
                for match in mtch_rslts:
                    img_ids.append(match.group(0))  # 直接获取整个匹配的字符串

                if len(img_ids) == 0:
                    img_ids = [f"Image_Number_{i}"]
                    i += 1

                item['id'] = img_ids[0]
                item['related_ids'] = img_ids[1:]
                item['if_aligned'] = True

            elif item['type'] == 'table':
                desc = "\n".join(item.get('table_caption', [])) + "\n" + "\n".join(item.get('table_footnote', []))
                mtch_rslts = re.finditer(TBL_REGX_NAME_PTRN, desc, re.IGNORECASE)

                tbl_ids = []
                for match in mtch_rslts:
                    tbl_ids.append(match.group(0))  # 直接获取整个匹配的字符串

                if len(tbl_ids) == 0:
                    tbl_ids = [f"Table_Number_{j}"]
                    j += 1

                item['id'] = tbl_ids[0]
                item['related_ids'] = tbl_ids[1:]
                item['if_aligned'] = True

            elif item['type'] == 'equation':
                desc = item.get('text')
                mtch_rslts = re.finditer(EQT_REGX_NAME_PTRN, desc, re.IGNORECASE)

                equation_ids = []
                for match in mtch_rslts:
                    equation_ids.append(match.group(0))  # 直接获取整个匹配的字符串

                if len(equation_ids) == 0:
                    equation_ids = [f"Equation_Number_{k}"]
                    k += 1

                item['id'] = equation_ids[0]
                item['related_ids'] = equation_ids[1:]
                item['if_aligned'] = True


    def align_reference_info(self, reference_metadata):
        """"identify reference items in pdf content json"""
        start_pos = 0
        end_pos = len(self.pdf_json)

        # search for reference title postion as start 
        for i in range(len(self.pdf_json)):
            if self.pdf_json[i].get('text_level') == 1:
                if text_match(self.pdf_json[i].get('text'), 'Reference', False) > 90:
                    start_pos = i + 1
                    break

        if start_pos > 0:
            for j in range(start_pos, len(self.pdf_json)):
                if self.pdf_json[j].get('text_level') is not None:
                    end_pos = j
                    break

        for idx in range(start_pos, end_pos):
            item = self.pdf_json[idx]
            if item.get('type') == 'text' and len(item.get('text')) < 500:
                if len(reference_metadata) > 0:
                    for ref in reference_metadata:
                        title = ref.get('citedPaper', {}).get('title')
                        ss_paper_id = ref.get('citedPaper', {}).get('paperId')
                        if title:
                            match_ratio = text_patial_match(title, item.get('text'), True) 
                            if match_ratio > 80:
                                item['if_aligned'] = True
                                item['type'] = "reference"
                                item['ss_paper_id'] = ss_paper_id
                                break
                else:
                    if start_pos > 0 and end_pos < len(self.pdf_json) and start_pos < end_pos:
                        item['if_aligned'] = True
                        item['type'] = "reference"
                        item['ss_paper_id'] = None
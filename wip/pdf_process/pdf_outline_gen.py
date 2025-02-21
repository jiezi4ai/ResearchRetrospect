import re
import fitz
import toml
import copy
from collections import Counter
from typing import List, Dict, Optional

from pdf_process.pdf_meta_det import extract_meta, dump_toml
from pdf_process.pdf_toc_det import gen_toc

from pdf_process import SECTION_TITLES, APPENDDIX_TITLES

def count_by_keys(lst_dct, keys):
    """get item count within a list of dict by specified dict keys
    Args:
        lst_dct: list of dict
        keys: specified dict keys like ['a', 'b', 'c']。
    Returns:
        dict: count of items based on keys combinations in descending order
    """
    key_combinations = []
    for dct in lst_dct:
        combination = tuple(dct.get(key) for key in keys)
        key_combinations.append(combination)
    result_cnt = Counter(key_combinations)
    sorted_result = sorted(result_cnt.items(), key=lambda item: item[0], reverse=True)
    return sorted_result


# OUtline Detection
class PDFOutline:
    def __init__(self, pdf_path):
        self.pdf_path = pdf_path
        self.doc = self.open_pdf()

    def open_pdf(self):
        """open pdf doc"""
        try:
            doc = fitz.open(self.pdf_path)
            return doc
        except Exception as e:
            print(f"处理 PDF 文件时出错: {self.pdf_path}, 错误信息: {e}")
            return None # 或者抛出异常，根据实际需求决定
        
    def toc_extraction(self, excpert_len:Optional[int]=300):
        """apply pymupdf to extract outline
        Args:
            pdf_path: path to pdf file
            excpert_len: excerpt lenght of initial text
        Return:
            pdf_toc: pdf toc including level, title, page, position, nameddest, if_collapse, excerpt
                     if_collapse: if contains next level title
                     excerpt: initial text
        """
        toc = self.doc.get_toc(simple=False) or []

        pdf_toc = []
        if len(toc) > 0:
            for item in toc:
                lvl = item[0] if len(item) > 0 else None
                title = item[1] if len(item) > 1 else None
                start_page = item[2] if len(item) > 2 else None
                pos = item[3].get('to') if len(item) > 3 and item[3] else None
                nameddest = item[3].get('nameddest') if len(item) > 3 and item[3] else None
                if_collapse = item[3].get('collapse', False) if len(item) > 3 and item[3] else None

                # get initial lines
                lines = ""
                if start_page is not None:
                    page = self.doc[start_page-1]
                    blocks = page.get_text("blocks")
                    for block in blocks:
                        x0, y0, x1, y1, text, _, _ = block
                        if len(lines) < excpert_len:
                            if pos and x0 >= pos.x:
                                lines += text
                        else:
                            break

                    pdf_toc.append({
                        "level": lvl,
                        "title": title,
                        "page": start_page,
                        "position": pos,
                        "nameddest": nameddest,
                        'if_collapse': if_collapse,
                        "excerpt": lines + "..."
                    })
        return pdf_toc
    
    def toc_detection(self, excpert_len:Optional[int]=300, titles=SECTION_TITLES):
        """identify toc based on title font, layout, etc"""
        matched_meta_lst = []
        pattern = '|'.join(re.escape(title) for title in titles)  
        for i in range(len(self.doc)):
            # extract_meta returns font size (size), font style (flags), font type (char_flags) 
            res = extract_meta(self.doc, pattern=pattern, page=i+1, ign_case=True)
            matched_meta_lst.extend(res)

        # get font size for titles
        keys = ['size']
        combinations = count_by_keys(matched_meta_lst, keys)  # get sorted count by keys in matched_meta_lst
        for x in combinations:
            if x[1] > 2:
                font_size = x[0][0]
                break

        # return to sampled_metadata to match all potential combinations
        title_meta_sample = [item for item in matched_meta_lst if item.get('size') == font_size]

        auto_level = 1
        addnl = False
        title_meta_toml = [dump_toml(m, auto_level, addnl) for m in title_meta_sample]

        # 直接使用 toml.loads 从字符串中加载 TOML 数据
        recipe = toml.loads('\n'.join(title_meta_toml))
        toc = gen_toc(self.doc, recipe)

        pdf_toc = []
        if len(toc) > 0:
            for item in toc:
                start_page = item.pagenum
                pos = item.pos
                
                # get initial lines
                if start_page is not None:
                    page = self.doc[start_page-1]
                    blocks = page.get_text("blocks")
                    lines = ""
                    for block in blocks:
                        x0, y0, x1, y1, text, _, _ = block
                        if len(lines) < excpert_len:
                            if pos and x0 >= pos.x:
                                lines += text
                        else:
                            break

                    pdf_toc.append({
                        "level": item.level,
                        "title": item.title,
                        "page": item.pagenum,
                        "position": item.pos,
                        "nameddest": "section.",
                        'if_collapse': None,
                        "excerpt": lines + "..."
                    })
        return pdf_toc
    
    def identify_toc_appendix(self, pdf_toc):
        pdf_toc_rvsd = copy.deepcopy(pdf_toc)
        pattern = '|'.join(re.escape(title) for title in APPENDDIX_TITLES) 

        for idx, item in enumerate(pdf_toc_rvsd):
            mtch = re.search(pattern, item.get('title'), re.IGNORECASE)
            if mtch:
                item['if_appendix'] = True
            elif 'appendix' in item.get('nameddest'):
                item['if_appendix'] = True
            elif idx > 0 and pdf_toc_rvsd[idx-1].get('if_appendix') == True:
                item['if_appendix'] = True
            else:
                item['if_appendix'] = False
        return pdf_toc_rvsd
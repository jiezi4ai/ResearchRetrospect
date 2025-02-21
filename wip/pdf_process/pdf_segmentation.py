# PDF Markdown Segmentation
# Run pdf_outline_gen, minerU process, pdf_post_process before this

import re 
from typing import List, Dict, Optional

from pdf_process import IMG_REGX_NAME_PTRN, TBL_REGX_NAME_PTRN, EQT_REGX_NAME_PTRN

class PDFSeg:
    def __init__(self, pdf_json):
        self.pdf_json = pdf_json

    def get_toc_hierachy(self):
        """generate ToC tree
        Args:
            pdf_json:
        Returns:
            tree form hierachy of sections
        """
        toc_hierachy = []
        section_stack = []

        for i, item in enumerate(self.pdf_json):
            if item['type'] == 'title':
                level = item['text_level']
                title = item['text']

                while section_stack and section_stack[-1]['level'] >= level:
                    popped_section = section_stack.pop()
                    popped_section['end_position'] = i - 1
                    if section_stack:
                        section_stack[-1]['subsection'].append(popped_section)
                    else:
                        toc_hierachy.append(popped_section)

                new_section = {'title': title, 'level': level, 'start_position': i, 'end_position': -1, 'subsection': []}
                section_stack.append(new_section)

        while section_stack:
            popped_section = section_stack.pop()
            popped_section['end_position'] = len(self.pdf_json) - 1
            if section_stack:
                section_stack[-1]['subsection'].append(popped_section)
            else:
                toc_hierachy.append(popped_section)

        return toc_hierachy
    
    def gen_seg_paras(self, toc_hierachy, seg_text_length:Optional[int]=20000):
        """segment content json based on toc hierachy"""
        pdf_texts = [item.get('text', '') for item in self.pdf_json]

        all_seg_paras = []
        for section in toc_hierachy:
            section_paras = []
            
            start_pos = section['start_position']
            end_pos = section['end_position']
            tmp_text = "\n".join(pdf_texts[start_pos:end_pos+1])
            
            if len(tmp_text) > seg_text_length and section.get('subsection', []) != []:
                # if the section is too long, then breakdown to subsection
                for subsection in section.get('subsection'):
                    sub_start_pos = subsection['start_position']
                    sub_end_pos = subsection['end_position']
                    section_paras.append(self.pdf_json[sub_start_pos:sub_end_pos+1])
                    tmp_text = "\n".join(pdf_texts[sub_start_pos:sub_end_pos+1])
                    print('subsection', subsection.get('title'), len(tmp_text))
            else:
                section_paras.append(self.pdf_json[start_pos:end_pos+1])
                print('section', section.get('title'), len(tmp_text))
                    
            all_seg_paras.extend(section_paras)
        return all_seg_paras

    def restore_seg_elements(self, seg_paras):
        """put all elements (images, tables, equations, refs) metioned in place where the refered to"""

        img_lst = [x for x in self.pdf_json if x.get('type')=='image']
        tbl_lst = [x for x in self.pdf_json if x.get('type')=='table']
        eqt_lst = [x for x in self.pdf_json if x.get('type')=='equation']
        ref_lst = [x for x in self.pdf_json if x.get('type')=='reference']

        seg_paras_rvsd = []
        for seg in seg_paras:
            seg_img_lst = [x for x in seg if x.get('type')=='image']
            seg_tbl_lst = [x for x in seg if x.get('type')=='table']
            seg_eqt_lst = [x for x in seg if x.get('type')=='equation']
            seg_ref_lst = [x for x in seg if x.get('type')=='reference']

            for item in seg:
                if item.get('if_being_reffered') is None:
                    item_text = item.get('text', '')

                    mtch_rslts = re.finditer(IMG_REGX_NAME_PTRN, item_text, re.IGNORECASE)
                    for match in mtch_rslts:
                        img_id = match.group(0)
                        if img_id not in [x.get('id') for x in seg_img_lst]:
                            added_items = [x for x in img_lst if x.get('id')==img_id]
                            print(added_items)
                            for y in added_items:
                                y['if_being_reffered'] = True
                            seg_img_lst.extend(added_items)
                            seg.extend(added_items)

                    mtch_rslts = re.finditer(TBL_REGX_NAME_PTRN, item_text, re.IGNORECASE)
                    for match in mtch_rslts:
                        tbl_id = match.group(0)
                        if tbl_id not in [x.get('id') for x in seg_tbl_lst]:
                            added_items = [x for x in tbl_lst if x.get('id')==tbl_id]
                            for y in added_items:
                                y['if_being_reffered'] = True
                            seg_tbl_lst.extend(added_items)
                            seg.extend(added_items)

                    mtch_rslts = re.finditer(EQT_REGX_NAME_PTRN, item_text, re.IGNORECASE)
                    for match in mtch_rslts:
                        eqt_id = match.group(0)
                        if eqt_id not in [x.get('id') for x in seg_eqt_lst]:
                            added_items = [x for x in eqt_lst if x.get('id')==eqt_id]
                            for y in added_items:
                                y['if_being_reffered'] = True
                            seg_eqt_lst.extend(added_items)
                            seg.extend(added_items)
            seg_paras_rvsd.append(seg)
        
        return seg_paras_rvsd
                
                
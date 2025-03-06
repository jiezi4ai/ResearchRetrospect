import os
import json
import time
import PIL.Image

from GitHub.ResearchRetrospect.wip.models.llms import llm_gen_w_retry, llm_image_gen_w_retry
from prompts import tags_example_json, tags_info_prompt, topics_example_json, topics_prompt
from prompts import role_prompt, summary_prompt, method_prompt, conclusion_prompt

class TopicGen:
    def __init__(self, seg_paras, api_key, model_name, temperature=0.6):
        self.api_key = api_key
        self.model_name = model_name
        self.temperature = temperature
        self.seg_paras = seg_paras

    def gen_md_from_json(self, content_json):
        """input json with predefined format and convert to markdown"""
        md_text = ""
        if len(content_json) > 0:
            for item in content_json:
                if item.get('type') == 'title':
                    md_text += f"{'#'*item.get('text_level')} {item.get('text')}  \n" 

                elif item.get('type') in ['image']:
                    alt_text = "\n".join(item.get('img_caption', [])) 
                    md_text += f"\n![{alt_text}]({item.get('img_path')} '{item.get('id')}')  \n"  
                    md_text += "\n".join(item.get('img_footnote'), []) 

                elif item.get('type') in ['table']:
                    alt_text = "\n".join(item.get('table_caption', [])) 
                    if item.get('img_path') is not None:
                        md_text += f"\n![{alt_text}]({item.get('img_path')} '{item.get('id')}')  \n" 
                    else:
                        md_text += f"\n{item.get('table_body')}  \n"  
                    md_text += "\n".join(item.get('table_footnote'), []) 

                elif item.get('type') in ['equation']:
                    md_text += f"""```latex\n{item.get('text')}\n```"""

                elif item.get('type') in ['text', 'reference']:
                    md_text += f"{item.get('text')}  \n"  
        return md_text
    
    def seg_topic_gen(self, domain,seg_json):
        """generate topic for segments"""
        md_text = self.gen_md_from_json(self, seg_json)  
        img_lst = [x for x in seg_json if x.get('img_path' is not None)]     

        if len(img_lst) > 0:
            img_info = ""
            pil_images = []
            for img in img_lst:
                img_url = img.get('img_path')
                pil_images.append(PIL.Image.open(img_url))
                img_info += f"- image title: {img.get('title')}  attached image: {os.path.basename(img_url)} \n"  
            imgs_prompt = f"Here are images mentioned in markdown text:\n{img_info}"
    
            qa_prompt = topics_prompt.format(
                domain = domain,
                example_json = json.dumps(topics_example_json, ensure_ascii=False), 
                markdown_text = md_text,
                further_information = imgs_prompt)

            res = llm_image_gen_w_retry(
                api_key=self.api_key, model_name=self.model_name, 
                qa_prompt=qa_prompt, pil_images=pil_images, sys_prompt=None, temperature=self.temperature)

        else:
            qa_prompt = topics_prompt.format(
                domain = domain,
                example_json = json.dumps(topics_example_json, ensure_ascii=False), 
                markdown_text = md_text,
                further_information = "")

            res = llm_gen_w_retry(
                api_key=self.api_key, model_name=self.model_name, 
                qa_prompt=qa_prompt, sys_prompt=None, temperature=self.temperature)
        return res

    def seg_keywords_gen(self, domain, seg_json):  
        """generate keywords, tags, etc for segments""" 
        md_text = self.gen_md_from_json(self, seg_json)  
        qa_prompt = tags_info_prompt.format(
            domain = domain,
            example_json = json.dumps(tags_example_json, ensure_ascii=False),
            markdown_text = md_text)

        res = llm_gen_w_retry(
            api_key=self.api_key, model_name=self.model_name, 
            qa_prompt=qa_prompt, sys_prompt=None, temperature=self.temperature)
        return res
    

    def paper_conclusion(self, paper_metadata, topics):
        """conclude key points, highlights, etc for paper"""

        abs_md_text = paper_metadata.get('abstract')

        intro_md_text, met_text, con_md_text = "", "", ""
        for item in self.seg_paras:
            title = item.get('title').strip()
            md_text = item.get('refined_text')
            if title.lower() in ['introduction', 'overview']:
                intro_md_text = md_text
            elif title.lower() in ['method', 'methodology', 'approach', 'framework']:
                met_text = md_text
            elif title.lower() in ['conclusion', 'summary']:
                con_md_text = md_text

        sum_md_text = """# Key Information  
        {md_text}
        """.format(md_text="\n".join(topics))

        summary_prompt = summary_prompt.format(
            abstract=abs_md_text, introduction=intro_md_text)
        summary_res = llm_gen_w_retry(
            api_key=self.api_key, model_name=self.model_name, 
            qa_prompt=summary_prompt, sys_prompt=None, temperature=self.temperature)
        
        method_prompt = method_prompt.format(
            method=met_text, summary=sum_md_text)
        method_res = llm_gen_w_retry(
            api_key=self.api_key, model_name=self.model_name, 
            qa_prompt=method_prompt, sys_prompt=None, temperature=self.temperature)
        
        conclusion_prompt = conclusion_prompt.format(
            conclusion=con_md_text, summary=sum_md_text)
        conclusion_res = llm_gen_w_retry(
            api_key=self.api_key, model_name=self.model_name, 
            qa_prompt=conclusion_prompt, sys_prompt=None, temperature=self.temperature)
        
        return summary_res, method_res, conclusion_res





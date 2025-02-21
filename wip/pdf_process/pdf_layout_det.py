# Source code attributed to PDF-Extract-Kit by opendatalab.


import os
import re
import gc
import sys
import fitz
import time
import torch
from PIL import Image, ImageDraw
from torchvision import transforms
from torch.utils.data import DataLoader

DEFAULT_DPI = 144

id_to_names = {
    0: 'title',
    1: 'plain text',
    2: 'abandon',
    3: 'figure',
    4: 'figure_caption',
    5: 'table',
    6: 'table_caption',
    7: 'table_footnote',
    8: 'isolate_formula',
    9: 'formula_caption'
}


# Reference link: [pdf_extract_kit/utils/dataset.py]
# (https://github.com/opendatalab/PDF-Extract-Kit/blob/710f577f308f3604e4450076fc04392d2d11009f/pdf_extract_kit/utils/dataset.py)
from torch.utils.data import Dataset

class MathDataset(Dataset):
    def __init__(self, image_paths, transform=None):
        self.image_paths = image_paths
        self.transform = transform

    def __len__(self):
        return len(self.image_paths)

    def __getitem__(self, idx):
        # if not pil image, then convert to pil image
        if isinstance(self.image_paths[idx], str):
            raw_image = Image.open(self.image_paths[idx])
        else:
            raw_image = self.image_paths[idx]
        if self.transform:
            image = self.transform(raw_image)
        return image


# Reference link: [pdf_extract_kit/utils/data_preprocess.py]
# (https://github.com/opendatalab/PDF-Extract-Kit/blob/710f577f308f3604e4450076fc04392d2d11009f/pdf_extract_kit/utils/data_preprocess.py)
def load_pdf_page(page, dpi):
    pix = page.get_pixmap(matrix=fitz.Matrix(dpi/72, dpi/72))
    image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    if pix.width > 3000 or pix.height > 3000:
        pix = page.get_pixmap(matrix=fitz.Matrix(1, 1), alpha=False)
        image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    return image

def load_pdf(pdf_path, dpi=DEFAULT_DPI):
    images = []
    doc = fitz.open(pdf_path)
    for i in range(len(doc)):
        page = doc[i]
        image = load_pdf_page(page, dpi)
        images.append(image)
    return images

# since there is a manipulation of image size, we need to map the image coordinates back to the pdf coordinates
def map_image_to_pdf(image_x, image_y, pix, dpi=DEFAULT_DPI):
    if pix.width <= 3000 and pix.height <= 3000:
        scale = dpi / 72
        pdf_x = image_x / scale
        pdf_y = image_y / scale
    else:
        pdf_x = image_x
        pdf_y = image_y
    return pdf_x, pdf_y


# Reference link: [pdf_extract_kit/utils/merge_blocks_and_spans.py]
# (https://github.com/opendatalab/PDF-Extract-Kit/blob/710f577f308f3604e4450076fc04392d2d11009f/pdf_extract_kit/utils/merge_blocks_and_spans.py)
def detect_lang(string):
    """
    检查整个字符串是否包含中文
    :param string: 需要检查的字符串
    :return: bool
    """

    for ch in string:
        if u'\u4e00' <= ch <= u'\u9fff':
            return 'zh'
    return 'en'

def ocr_escape_special_markdown_char(content):
    """
    转义正文里对markdown语法有特殊意义的字符
    """
    special_chars = ["*", "`", "~", "$"]
    for char in special_chars:
        content = content.replace(char, "\\" + char)

    return content

def __is_overlaps_y_exceeds_threshold(bbox1, bbox2, overlap_ratio_threshold=0.8):
    """检查两个bbox在y轴上是否有重叠，并且该重叠区域的高度占两个bbox高度更低的那个超过80%"""
    _, y0_1, _, y1_1 = bbox1
    _, y0_2, _, y1_2 = bbox2

    overlap = max(0, min(y1_1, y1_2) - max(y0_1, y0_2))
    height1, height2 = y1_1 - y0_1, y1_2 - y0_2
    max_height = max(height1, height2)
    min_height = min(height1, height2)

    return (overlap / min_height) > overlap_ratio_threshold

def calculate_overlap_area_in_bbox1_area_ratio(bbox1, bbox2):
    """
    计算box1和box2的重叠面积占bbox1的比例
    """
    # Determine the coordinates of the intersection rectangle
    x_left = max(bbox1[0], bbox2[0])
    y_top = max(bbox1[1], bbox2[1])
    x_right = min(bbox1[2], bbox2[2])
    y_bottom = min(bbox1[3], bbox2[3])

    if x_right < x_left or y_bottom < y_top:
        return 0.0

    # The area of overlap area
    intersection_area = (x_right - x_left) * (y_bottom - y_top)
    bbox1_area = (bbox1[2]-bbox1[0])*(bbox1[3]-bbox1[1])
    if bbox1_area == 0:
        return 0
    else:
        return intersection_area / bbox1_area

# 将每一个line中的span从左到右排序
def line_sort_spans_by_left_to_right(lines):
    line_objects = []
    for line in lines:
        # 按照x0坐标排序
        line.sort(key=lambda span: span['bbox'][0])
        line_bbox = [
            min(span['bbox'][0] for span in line),  # x0
            min(span['bbox'][1] for span in line),  # y0
            max(span['bbox'][2] for span in line),  # x1
            max(span['bbox'][3] for span in line),  # y1
        ]
        line_objects.append({
            "bbox": line_bbox,
            "spans": line,
        })
    return line_objects

def merge_spans_to_line(spans):
    if len(spans) == 0:
        return []
    else:
        # 按照y0坐标排序
        spans.sort(key=lambda span: span['bbox'][1])

        lines = []
        current_line = [spans[0]]
        for span in spans[1:]:
            # 如果当前的span类型为"isolated" 或者 当前行中已经有"isolated"
            # image和table类型，同上
            if span['type'] in ['isolated'] or any(
                    s['type'] in ['isolated'] for s in
                    current_line):
                # 则开始新行
                lines.append(current_line)
                current_line = [span]
                continue

            # 如果当前的span与当前行的最后一个span在y轴上重叠，则添加到当前行
            if __is_overlaps_y_exceeds_threshold(span['bbox'], current_line[-1]['bbox']):
                current_line.append(span)
            else:
                # 否则，开始新行
                lines.append(current_line)
                current_line = [span]

        # 添加最后一行
        if current_line:
            lines.append(current_line)

        return lines

def fix_interline_block(block):
    block_lines = merge_spans_to_line(block['spans'])
    sort_block_lines = line_sort_spans_by_left_to_right(block_lines)
    block['lines'] = sort_block_lines
    del block['spans']
    return block

def fix_text_block(block):
    # 文本block中的公式span都应该转换成行内type
    for span in block['spans']:
        if span['type'] == "isolated":
            span['type'] = "inline"
    block_lines = merge_spans_to_line(block['spans'])
    sort_block_lines = line_sort_spans_by_left_to_right(block_lines)
    block['lines'] = sort_block_lines
    del block['spans']
    return block

def fill_spans_in_blocks(blocks, spans, radio):
    '''
    将allspans中的span按位置关系，放入blocks中
    '''
    block_with_spans = []
    for block in blocks:
        block_type = block["category_type"]
        L = block['poly'][0]
        U = block['poly'][1]
        R = block['poly'][2]
        D = block['poly'][5]
        L, R = min(L, R), max(L, R)
        U, D = min(U, D), max(U, D)
        block_bbox = [L, U, R, D]
        block_dict = {
            'type': block_type,
            'bbox': block_bbox,
            'saved_info': block
        }
        block_spans = []
        for span in spans:
            span_bbox = span["bbox"]
            if calculate_overlap_area_in_bbox1_area_ratio(span_bbox, block_bbox) > radio:
                block_spans.append(span)

        '''行内公式调整, 高度调整至与同行文字高度一致(优先左侧, 其次右侧)'''
        # displayed_list = []
        # text_inline_lines = []
        # modify_y_axis(block_spans, displayed_list, text_inline_lines)

        '''模型识别错误的行间公式, type类型转换成行内公式'''
        # block_spans = modify_inline(block_spans, displayed_list, text_inline_lines)

        '''bbox去除粘连'''  # 去粘连会影响span的bbox，导致后续fill的时候出错
        # block_spans = remove_overlap_between_bbox_for_span(block_spans)

        block_dict['spans'] = block_spans
        block_with_spans.append(block_dict)

        # 从spans删除已经放入block_spans中的span
        if len(block_spans) > 0:
            for span in block_spans:
                spans.remove(span)

    return block_with_spans, spans

def fix_block_spans(block_with_spans):
    '''
    1、img_block和table_block因为包含caption和footnote的关系，存在block的嵌套关系
        需要将caption和footnote的text_span放入相应img_block和table_block内的
        caption_block和footnote_block中
    2、同时需要删除block中的spans字段
    '''
    fix_blocks = []
    for block in block_with_spans:
        block_type = block['type']

        # if block_type == BlockType.Image:
        #     block = fix_image_block(block, img_blocks)
        # elif block_type == BlockType.Table:
        #     block = fix_table_block(block, table_blocks)
        if block_type == "isolate_formula":
            block = fix_interline_block(block)
        else:
            block = fix_text_block(block)
        fix_blocks.append(block)
    return fix_blocks

def merge_para_with_text(para_block):
    para_text = ''
    for line in para_block['lines']:
        line_text = ""
        line_lang = ""
        for span in line['spans']:
            span_type = span['type']
            if span_type == "text":
                line_text += span['content'].strip()
        if line_text != "":
            line_lang = detect_lang(line_text)
        for span in line['spans']:
            span_type = span['type']
            content = ''
            if span_type == "text":
                content = span['content']
                content = ocr_escape_special_markdown_char(content)
                # language = detect_lang(content)
                # if language == 'en':  # 只对英文长词进行分词处理，中文分词会丢失文本
                    # content = ocr_escape_special_markdown_char(split_long_words(content))
                # else:
                #     content = ocr_escape_special_markdown_char(content)
            elif span_type == 'inline':
                content = f" ${span['content'].strip('$')}$ "
            elif span_type == 'ignore-formula':
                content = f" ${span['content'].strip('$')}$ "
            elif span_type == 'isolated':
                content = f"\n$$\n{span['content'].strip('$')}\n$$\n"    
            elif span_type == 'footnote':
                content_ori = span['content'].strip('$')
                if '^' in content_ori:
                    content = f" ${content_ori}$ "
                else:
                    content = f" $^{content_ori}$ "

            if content != '':
                if 'zh' in line_lang:  # 遇到一些一个字一个span的文档，这种单字语言判断不准，需要用整行文本判断
                    para_text += content.strip()  # 中文语境下，content间不需要空格分隔
                else:
                    para_text += content.strip() + ' '  # 英文语境下 content间需要空格分隔
    return para_text


# Reference link: [project/pdf2markdown/scripts/pdf2markdown.py]
# (https://github.com/opendatalab/PDF-Extract-Kit/blob/main/project/pdf2markdown/scripts/pdf2markdown.py)
def latex_rm_whitespace(s: str):
    """Remove unnecessary whitespace from LaTeX code.
    """
    text_reg = r'(\\(operatorname|mathrm|text|mathbf)\s?\*? {.*?})'
    letter = '[a-zA-Z]'
    noletter = '[\W_^\d]'
    names = [x[0].replace(' ', '') for x in re.findall(text_reg, s)]
    s = re.sub(text_reg, lambda match: str(names.pop(0)), s)
    news = s
    while True:
        s = news
        news = re.sub(r'(?!\\ )(%s)\s+?(%s)' % (noletter, noletter), r'\1\2', s)
        news = re.sub(r'(?!\\ )(%s)\s+?(%s)' % (noletter, letter), r'\1\2', news)
        news = re.sub(r'(%s)\s+?(%s)' % (letter, noletter), r'\1\2', news)
        if news == s:
            break
    return s

def crop_img(input_res, input_pil_img, padding_x=0, padding_y=0):
    crop_xmin, crop_ymin = int(input_res['poly'][0]), int(input_res['poly'][1])
    crop_xmax, crop_ymax = int(input_res['poly'][4]), int(input_res['poly'][5])
    # Create a white background with an additional width and height of 50
    crop_new_width = crop_xmax - crop_xmin + padding_x * 2
    crop_new_height = crop_ymax - crop_ymin + padding_y * 2
    return_image = Image.new('RGB', (crop_new_width, crop_new_height), 'white')

    # Crop image
    crop_box = (crop_xmin, crop_ymin, crop_xmax, crop_ymax)
    cropped_img = input_pil_img.crop(crop_box)
    return_image.paste(cropped_img, (padding_x, padding_y))
    return_list = [padding_x, padding_y, crop_xmin, crop_ymin, crop_xmax, crop_ymax, crop_new_width, crop_new_height]
    return return_image, return_list

class PDF2MARKDOWN:
    def __init__(self, layout_model, mfd_model, mfr_model, ocr_model):
        self.layout_model = layout_model
        self.mfd_model = mfd_model
        self.mfr_model = mfr_model
        self.ocr_model = ocr_model
        
        if self.mfr_model is not None:
            assert self.mfd_model is not None, "formula recognition based on formula detection, mfd_model can not be None."
            self.mfr_transform = transforms.Compose([self.mfr_model.vis_processor, ])
            
        self.color_palette  = {
            'title': (255, 64, 255),
            'plain text': (255, 255, 0),
            'abandon': (0, 255, 255),
            'figure': (255, 215, 135),
            'figure_caption': (215, 0, 95),
            'table': (100, 0, 48),
            'table_caption': (0, 175, 0),
            'table_footnote': (95, 0, 95),
            'isolate_formula': (175, 95, 0),
            'formula_caption': (95, 95, 0),
            'inline': (0, 0, 255),
            'isolated': (0, 255, 0),
            'text': (255, 0, 0)
        }

    def convert_format(self, yolo_res, id_to_names, ):
        """
        convert yolo format to pdf-extract format.
        """
        res_list = []
        for xyxy, conf, cla in zip(yolo_res.boxes.xyxy.cpu(), yolo_res.boxes.conf.cpu(), yolo_res.boxes.cls.cpu()):
            xmin, ymin, xmax, ymax = [int(p.item()) for p in xyxy]
            new_item = {
                'category_type': id_to_names[int(cla.item())],
                'poly': [xmin, ymin, xmax, ymin, xmax, ymax, xmin, ymax],
                'score': round(float(conf.item()), 2),
            }
            res_list.append(new_item)
        return res_list
    
    
    def process_single_pdf(self, file_path):
    # def process_single_pdf(self, image_list):
        """predict on one image, reture text detection and recognition results.
        
        Args:
            file_path (str): file path of pdf.
            # image_list: List[PIL.Image.Image]
            
        Returns:
            List[dict]: list of PDF extract results
            
        Return example:
            [
                {
                    "layout_dets": [
                        {
                            "category_type": "text",
                            "poly": [
                                380.6792698635707,
                                159.85058512958923,
                                765.1419999999998,
                                159.85058512958923,
                                765.1419999999998,
                                192.51073013642917,
                                380.6792698635707,
                                192.51073013642917
                            ],
                            "text": "this is an example text",
                            "score": 0.97
                        },
                        ...
                    ], 
                    "page_info": {
                        "page_no": 0,
                        "height": 2339,
                        "width": 1654,
                    }
                },
                ...
            ]
        """
        # first convert pdf to images
        if file_path.endswith(".pdf") or file_path.endswith(".PDF"):
            images = load_pdf(file_path)
        else:
            images = [Image.open(file_path)]

        pdf_extract_res = []
        mf_image_list = []
        latex_filling_list = []
        for idx, image in enumerate(images):
            img_W, img_H = image.size
            if self.layout_model is not None:
                ori_layout_res = self.layout_model.predict([image], "")[0]
                layout_res = self.convert_format(ori_layout_res, self.layout_model.id_to_names)
            else:
                layout_res = []
            single_page_res = {'layout_dets': layout_res}
            single_page_res['page_info'] = dict(
                page_no = idx,
                height = img_H,
                width = img_W
            )
            if self.mfd_model is not None:
                mfd_res = self.mfd_model.predict([image], "")[0]
                for xyxy, conf, cla in zip(mfd_res.boxes.xyxy.cpu(), mfd_res.boxes.conf.cpu(), mfd_res.boxes.cls.cpu()):
                    xmin, ymin, xmax, ymax = [int(p.item()) for p in xyxy]
                    new_item = {
                        'category_type': self.mfd_model.id_to_names[int(cla.item())],
                        'poly': [xmin, ymin, xmax, ymin, xmax, ymax, xmin, ymax],
                        'score': round(float(conf.item()), 2),
                        'latex': '',
                    }
                    single_page_res['layout_dets'].append(new_item)
                    if self.mfr_model is not None:
                        latex_filling_list.append(new_item)
                        bbox_img = image.crop((xmin, ymin, xmax, ymax))
                        mf_image_list.append(bbox_img)
                    
                pdf_extract_res.append(single_page_res)
                
                del mfd_res
                torch.cuda.empty_cache()
                gc.collect()
            
        # Formula recognition, collect all formula images in whole pdf file, then batch infer them.
        if self.mfr_model is not None:
            a = time.time()
            dataset = MathDataset(mf_image_list, transform=self.mfr_transform)
            dataloader = DataLoader(dataset, batch_size=self.mfr_model.batch_size, num_workers=0)

            mfr_res = []
            for imgs in dataloader:
                imgs = imgs.to(self.mfr_model.device)
                output = self.mfr_model.model.generate({'image': imgs})
                mfr_res.extend(output['pred_str'])
            for res, latex in zip(latex_filling_list, mfr_res):
                res['latex'] = latex_rm_whitespace(latex)
            b = time.time()
            print("formula nums:", len(mf_image_list), "mfr time:", round(b-a, 2))
        

        if self.ocr_model is not None:
            # ocr_res = self.ocr_model.predict(image)

            # ocr and table recognition
            for idx, image in enumerate(images):
                layout_res = pdf_extract_res[idx]['layout_dets']
                pil_img = image.copy()

                ocr_res_list = []
                table_res_list = []
                single_page_mfdetrec_res = []

                for res in layout_res:
                    if res['category_type'] in self.mfd_model.id_to_names.values():
                        single_page_mfdetrec_res.append({
                            "bbox": [int(res['poly'][0]), int(res['poly'][1]),
                                    int(res['poly'][4]), int(res['poly'][5])],
                        })
                    elif res['category_type'] in [self.layout_model.id_to_names[cid] for cid in [0, 1, 2, 4, 6, 7]]:
                        ocr_res_list.append(res)
                    elif res['category_type'] in [self.layout_model.id_to_names[5]]:
                        table_res_list.append(res)

                ocr_start = time.time()
                # Process each area that requires OCR processing
                for res in ocr_res_list:
                    new_image, useful_list = crop_img(res, pil_img, padding_x=25, padding_y=25)
                    paste_x, paste_y, xmin, ymin, xmax, ymax, new_width, new_height = useful_list
                    # Adjust the coordinates of the formula area
                    adjusted_mfdetrec_res = []
                    for mf_res in single_page_mfdetrec_res:
                        mf_xmin, mf_ymin, mf_xmax, mf_ymax = mf_res["bbox"]
                        # Adjust the coordinates of the formula area to the coordinates relative to the cropping area
                        x0 = mf_xmin - xmin + paste_x
                        y0 = mf_ymin - ymin + paste_y
                        x1 = mf_xmax - xmin + paste_x
                        y1 = mf_ymax - ymin + paste_y
                        # Filter formula blocks outside the graph
                        if any([x1 < 0, y1 < 0]) or any([x0 > new_width, y0 > new_height]):
                            continue
                        else:
                            adjusted_mfdetrec_res.append({
                                "bbox": [x0, y0, x1, y1],
                            })

                    # OCR recognition
                    ocr_res = self.ocr_model.ocr(new_image, mfd_res=adjusted_mfdetrec_res)[0]

                    # Integration results
                    if ocr_res:
                        for box_ocr_res in ocr_res:
                            p1, p2, p3, p4 = box_ocr_res[0]
                            text, score = box_ocr_res[1]

                            # Convert the coordinates back to the original coordinate system
                            p1 = [p1[0] - paste_x + xmin, p1[1] - paste_y + ymin]
                            p2 = [p2[0] - paste_x + xmin, p2[1] - paste_y + ymin]
                            p3 = [p3[0] - paste_x + xmin, p3[1] - paste_y + ymin]
                            p4 = [p4[0] - paste_x + xmin, p4[1] - paste_y + ymin]

                            layout_res.append({
                                'category_type': 'text',
                                'poly': p1 + p2 + p3 + p4,
                                'score': round(score, 2),
                                'text': text,
                            })

            ocr_cost = round(time.time() - ocr_start, 2)
            print(f"ocr cost: {ocr_cost}")

        # use pymupdf to get text if no ocr
        else:
            document = fitz.open(file_path)
            for idx, item in enumerate(pdf_extract_res):
                page = document.load_page(idx)

                pix = page.get_pixmap(matrix=fitz.Matrix(DEFAULT_DPI/72, DEFAULT_DPI/72))
                layout_res = item['layout_dets']

                for res in layout_res:
                    if res['category_type'] in [self.layout_model.id_to_names[cid] for cid in [0, 1, 2, 4, 6, 7]]:
                        area = res['poly']
                        x0, y0 = map_image_to_pdf(area[0], area[1], pix)
                        x1, y1 = map_image_to_pdf(area[4], area[5], pix)
                        rect = fitz.Rect(x0, y0, x1, y1)  # 使用左上角和右下角坐标创建矩形
                        text = page.get_text("text", clip=rect)

                        if text:
                            layout_res.append({
                                    'category_type': 'text',
                                    'poly': area,
                                    'score': 1,
                                    'text': text,
                                })

        return pdf_extract_res, images  # return extracted data as well as raw images
        # return pdf_extract_res
    
    def order_blocks(self, blocks):
        def calculate_oder(poly):
            xmin, ymin, _, _, xmax, ymax, _, _ = poly
            return ymin*3000 + xmin
        return sorted(blocks, key=lambda item: calculate_oder(item['poly']))
                 
    def convert2md(self, extract_res):
        blocks = []
        spans = []
        

        for item in extract_res['layout_dets']:
            if item['category_type'] in ['inline', 'text', 'isolated']:  # add plain text
                text_key = 'text' if item['category_type'] in ['text'] else 'latex'  # add plain text
                xmin, ymin, _, _, xmax, ymax, _, _ = item['poly']
                spans.append(
                    {
                        "type": item['category_type'],
                        "bbox": [xmin, ymin, xmax, ymax],
                        "content": item[text_key]
                    }
                )
                if item['category_type'] == "isolated":
                    item['category_type'] = "isolate_formula"
                    blocks.append(item)
            else:
                blocks.append(item)
                
        blocks_types = ["title", "plain text", "figure_caption", "table_caption", "table_footnote", "isolate_formula", "formula_caption"]

        need_fix_bbox = []
        final_block = []
        for block in blocks:
            block_type = block["category_type"]
            if block_type in blocks_types:
                need_fix_bbox.append(block)
            else:
                final_block.append(block)
                
        block_with_spans, spans = fill_spans_in_blocks(need_fix_bbox, spans, 0.6)
        
        fix_blocks = fix_block_spans(block_with_spans)
        for para_block in fix_blocks:
            result = merge_para_with_text(para_block)
            if para_block['type'] == "isolate_formula":
                para_block['saved_info']['latex'] = result
            else:
                para_block['saved_info']['text'] = result
            final_block.append(para_block['saved_info'])
            
        final_block = self.order_blocks(final_block)
        md_text = ""
        for block in final_block:
            if block['category_type'] == "title":
                md_text += "\n# "+block['text'] +"\n"
            elif block['category_type'] in ["plain text"]:
                md_text += " "+block['text']+" "
            # elif block['category_type'] in ["isolate_formula"]:
            #     md_text += "\n"+block['latex']+"\n"
            # elif block['category_type'] in ["plain text", "figure_caption", "table_caption"]:
            #     md_text += " "+block['text']+" "
            # elif block['category_type'] in ["figure", "table"]:
            #     continue
            # else:
            #     continue
        return final_block, md_text
        
    def process(self, input_path, save_dir=None, visualize=False, merge2markdown=False):
        file_list = self.prepare_input_files(input_path)
        res_list = []
        for fpath in file_list:
            basename = os.path.basename(fpath)[:-4]
            # modified by jiezi, 2024-11-12
            # if fpath.endswith(".pdf") or fpath.endswith(".PDF"):
            #     images = load_pdf(fpath)
            # else:
            #     images = [Image.open(fpath)]
            pdf_extract_res, images = self.process_single_pdf(fpath)
            res_list.append(pdf_extract_res)
            if save_dir:
                os.makedirs(save_dir, exist_ok=True)
                self.save_json_result(pdf_extract_res, os.path.join(save_dir, f"{basename}.json"))
                
                if merge2markdown:
                    final_blocks, md_content = [], []
                    for extract_res in pdf_extract_res:
                        final_block, md_text = self.convert2md(extract_res)
                        final_blocks.append(final_block)
                        md_content.append(md_text)
                    with open(os.path.join(save_dir, f"{basename}.md"), "w") as f:
                        f.write("\n\n".join(md_content))
                        
                if visualize:
                    for image, page_res in zip(images, pdf_extract_res):
                        self.visualize_image(image, page_res['layout_dets'], cate2color=self.color_palette)
                    if fpath.endswith(".pdf") or fpath.endswith(".PDF"):
                        first_page = images.pop(0)
                        first_page.save(os.path.join(save_dir, f'{basename}.pdf'), 'PDF', resolution=100, save_all=True, append_images=images)
                    else:
                        images[0].save(os.path.join(save_dir, f"{basename}.png"))

        return res_list, final_blocks, md_content

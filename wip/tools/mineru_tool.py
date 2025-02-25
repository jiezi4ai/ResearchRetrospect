# minerU API from https://mineru.net/apiManage/docs
# Note: 
# 1. recommend batch process for efficiency
# To-do 
# Note: monitor_batch_status need to be further tested
import os
import time
import uuid
import copy
import zipfile
import requests
import threading
from pathlib import Path  
from typing import List, Dict, Optional

TASK_URL = "https://mineru.net/api/v4/extract/task"
BATCH_URL = "https://mineru.net/api/v4/file-urls/batch"
BATCH_STATUS_URL = "https://mineru.net/api/v4/extract-results/batch"


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


def unzip_file(original_zip_file, destination_folder):
    assert os.path.splitext(original_zip_file)[-1] == '.zip'
    with zipfile.ZipFile(original_zip_file, 'r') as zip_ref:
        zip_ref.extractall(destination_folder)
        print(f"Successfully unzipped: {destination_folder}")


def download_file(url, filename):
    """Downloads a file from the given URL and saves it as filename."""
    try:
        response = requests.get(url)
        response.raise_for_status()  # Raise an exception for bad status codes

        with open(filename, 'wb') as f:
            f.write(response.content)

        print(f"Successfully downloaded: {filename}")
    except requests.exceptions.RequestException as e:
        print(f"Error downloading: {e}")


class MinerUKit:
    def __init__(self, api_key):
        self.api_key = api_key
        self.task_url = TASK_URL
        self.batch_url = BATCH_URL
        self.batch_status_url = BATCH_STATUS_URL
        self.header = {
                    'Content-Type':'application/json',
                    "Authorization":f"Bearer {self.api_key}"
                 }
        self.config = {
            "enable_formula": True,
            "language": "en",
            "layout_model":"doclayout_yolo",
            "enable_table": True
        }

    def single_process_url(self, pdf_url, if_ocr, lang):
        """apply MinerU API to process single PDF
        """
        data = copy.deepcopy(self.config)
        data['url'] = pdf_url
        data['is_ocr'] = if_ocr
        data['language'] = lang
        response = requests.post(url=self.task_url, headers=self.header, json=data)
        print(response.status_code)
        return response
    
    def batch_process_files(self, pdf_files:List[str], if_ocr:Optional[bool]=False, lang:Optional[str]='en'):
        """apply MinerU API to process multiple PDF in local path
        """
        files = []
        for file in pdf_files:
            files.append({"name": os.path.basename(file),
                          "data_id": str(uuid.uuid1())})
        data = copy.deepcopy(self.config)
        data['is_ocr'] = if_ocr
        data['language'] = lang
        data['files'] = files

        try:
            response = requests.post(url=self.batch_url,headers=self.header,json=data)
            if response.status_code == 200:
                result = response.json()
                print('response success. result:{}'.format(result))
                if result["code"] == 0:
                    batch_id = result["data"]["batch_id"]
                    urls = result["data"]["file_urls"]
                    print('batch_id:{},urls:{}'.format(batch_id, urls))

                    for idx, file_path in enumerate(pdf_files):
                        with open(file_path, 'rb') as f:
                            res_upload = requests.put(urls[idx], data=f)
                        if res_upload.status_code == 200:
                            print("upload success")
                        else:
                            print("upload failed")
                else:
                    print('apply upload url failed,reason:{}'.format(result.msg))
            else:
                print('response not success. status:{} ,result:{}'.format(response.status_code, response))
            return response
        except Exception as err:
            print(err)
        
        return None

    def batch_process_urls(self, pdf_urls:List[str], if_ocr:Optional[bool]=False, lang:Optional[str]='en'):
        """apply MinerU API to process multiple PDF urls
        """
        files = []
        for pdf_url in pdf_urls:
            files.append({"url": pdf_url,
                          "data_id": str(uuid.uuid1())})
        data = copy.deepcopy(self.config)
        data['is_ocr'] = if_ocr
        data['language'] = lang
        data['files'] = files

        try:
            response = requests.post(url=self.batch_url, headers=self.header, json=data)
            if response.status_code == 200:
                result = response.json()
                print('response success. result:{}'.format(result))
                if result["code"] == 0:
                    batch_id = result["data"]["batch_id"]
                    print('batch_id:{}'.format(batch_id))
                else:
                    print('submit task failed,reason:{}'.format(result.msg))
            else:
                print('response not success. status:{} ,result:{}'.format(response.status_code, response))
            return response
        except Exception as err:
            print(err)

        return None

    def batch_status_check(self, batch_id):
        """check status code of batch task
        """
        url = f'{self.batch_status_url}/{batch_id}'
        res = requests.get(url=url, headers=self.header)
        print(res.status_code)
        # print(res.json())
        return res
    
    def download_and_unzip(self, zip_url, download_file_name, unzip_folder_name):
        """download and unzip MinerU processed files"""
        download_file(zip_url, download_file_name)
        unzip_file(download_file_name, unzip_folder_name)
        os.remove(download_file_name) 

        for file in Path(unzip_folder_name).glob('*'): 
            file_nm = os.path.basename(file)
            if "_origin.pdf" in file_nm:
                os.remove(file) 
            elif "_content_list.json" in file_nm:
                os.rename(file, os.path.join(unzip_folder_name, "content_list.json"))

    def monitor_batch_status(self, batch_id, save_path, interval=10, max_retries=10):
        """
        monitor batch run status, try to download with max_retries

        Args:
            batch_id: batch id
            save_path: path to save processed files (in folder whose name aligned with orginal pdf)
            interval: time interval for next check (in seconds)
            max_retries: max retries
        Note:
            processed data would saved into folders whose name aligned with orginal pdf.
            files include:
                - full.md: final markdown file
                - _content_list.json: paragraph information
                - layout.json: detailed positions, etc.
        """
        downloaded_files = set()  # 记录已下载的文件名，避免重复下载

        for _ in range(max_retries):
            running_res = self.batch_status_check(batch_id)
            if running_res.json().get('msg') == 'ok':
                results = running_res.json().get('data', {}).get('extract_result', [])
                for item in results:
                    if item.get('state') == 'done':
                        file_name = item.get('file_name')
                        if file_name not in downloaded_files:  # 检查是否已下载
                            file_name_nosuffix = file_name.rsplit('.', 1)[0]
                            zip_url = item.get('full_zip_url')
                            download_file_name = os.path.join(save_path, file_name_nosuffix + ".zip")
                            unzip_folder_name = os.path.join(save_path, file_name_nosuffix)

                            # 使用线程下载并解压，避免阻塞主线程
                            thread = threading.Thread(
                                target=self.download_and_unzip,
                                args=(zip_url, download_file_name, unzip_folder_name)
                            )
                            thread.start()

                            downloaded_files.add(file_name)  # 标记为已下载
                
                # 检查是否全部完成
                all_done = all(item.get('state') == 'done' for item in results)
                if all_done:
                    print(f"Batch {batch_id} complte")
                    return

            print(f"Batch {batch_id} running, recheck in next {interval} seconds...")
            time.sleep(interval)

        print(f"Exit as batch {batch_id} reached max retries.")
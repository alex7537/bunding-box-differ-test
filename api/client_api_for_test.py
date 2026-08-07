import requests
from dataclasses import dataclass
import json
import pybase64
from typing import List
from api.api_data_format import *
#
# @dataclass
# class Bbox:
#     x: float
#     y: float
#     w: float
#     h: float
#
# @dataclass
# class RequestData:
#     bboxes: List[Bbox]      # 输入的bbox
#     request_id: int         # 请求id
#     image_weight: int
#     image_height: int
#     image_data: str = ""    # pybase64 encoded 图片
#     algo_name: str = ""     # 模型名称
#     algo_param: str = ""    # 模型配置参数
#
# @dataclass
# class ResponseData:
#     bboxes: List[Bbox]      # 输出的bbox
#     request_id: int         # 请求id
#     #image_weight: int
#     #image_height: int
#     #image_data: str = ""    # pybase64 encoded 图片
#     #algo_name: str = ""     # 模型名称
#     #algo_param: str = ""    # 模型配置参数

bbox = Bbox(1,2,3,4)
bbox2= Bbox(2,3,4,5)

image_data = open('/home/longqi/图片/b.jpg', 'rb').read()
image_encoded = pybase64.urlsafe_b64encode(image_data).decode('utf-8')

req = RequestData(
    bboxes = [bbox, bbox2],
    request_id=0,
    image_width = 768,        # 图片宽
    image_height = 1024,     # 图片高
    image_data = "",   # pybase64 encoded 图片, pybase64.urlsafe_b64encode(image_data).decode('utf-8')
    algo_name = "dimp",
    algo_param = "dimp50"
)
print(req)
json_data = json.dumps(req, default=lambda o: o.__dict__)
print(json_data)
req.image_data = image_encoded
json_data = json.dumps(req, default=lambda o: o.__dict__)

host_post_url = "http://127.0.0.1:5000"
action_url = "/api/v1/mot/dimp/launch_tracking"

result = requests.post(host_post_url+action_url, json=json_data)
result = result.json()
#print('result',result)
#response = ResponseData.from_json(result)
#print('response=',response)
print('result',result["bboxes"])

for i in range(10):
    action_url = "/api/v1/mot/dimp/track_next"
    result = requests.post(host_post_url+action_url, json=json_data)
    #result = result.json()
    print(result)
    response = ResponseData.from_json(result.text)
    print('response',response)


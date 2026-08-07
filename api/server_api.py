'''
    server rest api FOR tracking algorithms.
'''

import io

import PIL.Image
from flask import Flask, request
import json
import os
import sys
env_path = os.path.join(os.path.dirname(__file__), '..')
if env_path not in sys.path:
    sys.path.append(env_path)
from pytracking.evaluation import Tracker
import pybase64
import cv2
import numpy as np
from dataclasses import dataclass
from collections import OrderedDict

from dataclasses import dataclass
from typing import List
import inspect

from dataclasses_json import dataclass_json
import time


# (left-up corner): x,y
# w: width
# h: height
@dataclass_json
@dataclass
class Bbox:
    x: float
    y: float
    w: float
    h: float


@dataclass_json
@dataclass(order=True)
class RequestData:
    bboxes: List[Bbox]      # 输入的bbox
    request_id: str         # 请求id
    image_width: int        # 图片宽
    image_height: int       # 图片高
    image_data: str = ""    # pybase64 encoded 图片, pybase64.urlsafe_b64encode(image_data).decode('utf-8')
    algo_name: str = ""     # 模型名称
    algo_param: str = ""    # 模型配置参数

@dataclass_json
@dataclass
class ResponseData:
    bboxes: List[Bbox]      # 输出的bbox
    request_id: str         # 请求id
    status: str             # 200, 500, ...
    message: str = ""           # error message

    #image_weight: int
    #image_height: int
    #image_data: str = ""    # pybase64 encoded 图片
    #algo_name: str = ""     # 模型名称
    #algo_param: str = ""    # 模型配置参数

app = Flask(__name__)

memory = {}

'''
urls
    format:
        /api/{version}/{task_type}/{algorithm}/action
        
        version: v1
        task_type: {mot, object_detection}
        algorithm: {dimp, ..., }
    action:
        - launch_tracking
            url = /api/v1/mot/dimp/launch_tracking
            method = post
            args: 
                request_id:
                algo_name:   dimp
                algo_param:  dimp50
                image_data:  pybase64
                image_url:   abs_path_of_image
                annotation:
                    [
                        {
                            "bbox" = [x1,y1,x2,y2,x3,y3,x4,y4]  左上、右上、右下、左下
                            "class" = class_name
                        }
                    ]
                classes:
                    {
                        "0": class_name0,
                        "1": class_name1
                    }
        - track_following
            url = /api/v1/mot/dimp/track_following
            method = post
            args: 
                request_id:
                algo_name:
                algo_param:
                image_data:
                image_url:
                annotation:
                classes:
        
'''
url_launch_tracking = "/api/v1/mot/pytracking/launch_tracking"
url_track_next =      "/api/v1/mot/pytracking/track_next"


def base64_to_cv(img_base64):
    f = io.BytesIO()
    f.write(img_base64)
    img_pil = PIL.Image.open(f)
    #mg_pil.show()
    img_arr = np.array(img_pil)
    img_arr_cv = cv2.cvtColor(img_arr, cv2.COLOR_RGB2BGR)
    return img_arr_cv


@app.route(url_launch_tracking, methods=["POST"])
def launch_tracking():
    # default
    #response = ResponseData(status=200, error="", out_bboxes=OrderedDict(), data="")
    error_msg = ""

    response = ResponseData(
        status="200",
        message='',
        bboxes=[],
        request_id=""
    )

#    request_id_time = (int)(time.time()*1000)   # 以毫秒时刻作为请求的id
    request_ip_address = request.remote_addr
    response.request_id = request_ip_address

    if not request.method == "POST":
        response.status = "500"
        response.message = "please use POST method"
        response.bboxes=[]
        response.request_id = -1
        return json.dumps(response,  default=lambda o: o.__dict__)

    request_data_str = request.get_json(force=True)
    #request_data = json.loads(request_data_str)
    #print(request_data)
    request_data_dc = RequestData.from_json(request_data_str)

    try:
        decoded_image_data = pybase64.urlsafe_b64decode(request_data_dc.image_data)
        img_arr_cv = base64_to_cv(decoded_image_data)
    except Exception as e:
        error_msg += str(e)
        response.message = error_msg
        response.status = "500"
        return json.dumps(response, default=lambda o: o.__dict__)

    tracker = Tracker(
        name = request_data_dc.algo_name,
        parameter_name = request_data_dc.algo_param
    )

    bboxes = []
    for box in request_data_dc.bboxes:
        bboxes.append([box.x, box.y, box.w, box.h])

    if not bboxes:
        response.message = "请给出初始目标框。"
        response.status = "500"
        return json.dumps(response, default=lambda o: o.__dict__)
    else:
        status, msg, tracker_instance, info = tracker.run_track_first_frame(image_data=img_arr_cv,
                                                           optional_boxes=bboxes)
    if status == False:
        error_msg += msg
        response.message = error_msg
        response.status = "500"
    else:
        print('input', bboxes)
        my_memory = {}
    #   tracker_instance, info = tracker.run_track_first_frame(image_data=img_arr_cv, optional_boxes=[[1,1,1,1],[2,2,2,2]])
        my_memory["tracker"] = tracker_instance
        my_memory["info"] = info

        memory[response.request_id] = my_memory

        response.bboxes = []
        for key in info["previous_output"]["target_bbox"].keys():
            t_bbox = info["previous_output"]["target_bbox"][key]
            bbox = Bbox(t_bbox[0],t_bbox[1],t_bbox[2],t_bbox[3])
            response.bboxes.append(bbox)
        print(response)

    return json.dumps(response, default=lambda o: o.__dict__)


@app.route(url_track_next, methods=["POST"])
def track_next():
    response = ResponseData(
        status="200",
        message='',
        bboxes=[],
        request_id=""
    )

    if not request.method == "POST":
        response.status = "500"
        response.message = "please use POST method"
        return json.dumps(response, default=lambda o: o.__dict__)

    data_str = request.get_json(force=True)
    data = json.loads(data_str)

    request_id = data.get("request_id")

    my_memory = memory.get(request_id)

    if not my_memory:
        response.status = "500"
        response.message = "缓存丢失，请重新连接。"
    else:
        tracker_instance = my_memory["tracker"]
        info = my_memory["info"]

        #   加入request_id识别不同的请求
        #   tracker_instance = memory["tracker"]
        #   info = memory["info"]

        image_file = data.get("image_data")
        if image_file:
            image_data = pybase64.urlsafe_b64decode(image_file)
            img_arr_cv = base64_to_cv(image_data)
            output = tracker_instance.track(img_arr_cv, info)
            print(output)
            info["previous_output"] = output

            my_memory["tracker"] = tracker_instance
            my_memory["info"] = info
            memory[request_id] = my_memory

        if tracker_instance:
            response.bboxes = []
            for key in info["previous_output"]["target_bbox"].keys():
                t_bbox = info["previous_output"]["target_bbox"][key]
                bbox = Bbox(t_bbox[0], t_bbox[1], t_bbox[2], t_bbox[3])
                response.bboxes.append(bbox)
            return json.dumps(response, default=lambda o: o.__dict__)
        return json.dumps(response, default=lambda o: o.__dict__)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
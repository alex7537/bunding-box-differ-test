from dataclasses import dataclass
from typing import List
import inspect
from dataclasses_json import dataclass_json

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


def from_dict_to_dataclass(cls, data):
    return cls(
        **{
            key: (data[key] if val.default == val.empty else data.get(key, val.default))
            for key, val in inspect.signature(cls).parameters.items()
        }
    )

bbox = Bbox(1,2,3,4)
response = ResponseData(status=200, bboxes=[bbox,bbox], message='', request_id=0)

res_json = response.to_json()
print(res_json)

res_from_json = ResponseData.from_json(res_json)
print(res_from_json)
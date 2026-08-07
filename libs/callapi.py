import pybase64
import requests
import time
from PyQt5.QtCore import QThread, pyqtSignal, QRectF
from PyQt5.QtWidgets import QMessageBox

from libs.opencv_tracker import OpenCVTracker
from dataclasses import dataclass
import logging
import os
import json
from PIL import Image
from libs.api_data_format import Bbox, RequestData, ResponseData

logger = logging.getLogger('mylogger')
logger.setLevel(logging.DEBUG)


class Callapi(QThread):
    # signal = Signal(object)
    # signal_frame = pyqtSignal(object)
    # signal_stop = pyqtSignal(object)

    load_file_signal = pyqtSignal(object)
    save_file_signal = pyqtSignal(object, int)
    show_message_signal = pyqtSignal(str, str)

    def __init__(self, main_window, remote=False, model_name=None, model_param=None, config=None, speed_track=None):
        super().__init__()
        self.speed_track = speed_track
        self.main_window = main_window
        # self.url = url
        # self.host = host
        self.is_stoped = False
        self.remote = remote
        self.model_name = model_name
        self.model_param = model_param
        self.config = config

    def stop(self):
        self.is_stoped = True

    def get_tracker_by_selection(self):
        tracker_name = self.main_window.model_combobox

    def do_call_remote_api(self):
        def xywh_to_points(x, y, w, h, image_width, image_height):

            x = x if x > 0 else 0
            y = y if y > 0 else 0
            x_w = x + w if x + w < image_width else image_width
            y_h = y + h if y + h < image_height else image_height

            return [
                (x, y), (x + w, y), (x_w, y_h), (x, y_h)
            ]

        #            return [(x,y),(x+w,y),(x+w,y+h),(x,y+h)]
        def points_to_xywh(s):
            points = [(p.x(), p.y()) for p in s.points]
            bbox = Bbox(
                x=points[0][0],
                y=points[0][1],
                w=points[1][0] - points[0][0],
                h=points[3][1] - points[0][1]
            )
            return bbox

        image_files = self.main_window.m_img_list

        if not (self.main_window.cur_img_idx < len(image_files)):
            logger.debug('out of index, cur_img_idx')
            return

        try:
            request_id = ""
            filename = self.main_window.m_img_list[self.main_window.cur_img_idx]
            if os.path.exists(filename):
                image = Image.open(filename)
                # 获取图片的宽度和高度
                width, height = image.size
                image.close()

                image_data = open(filename, 'rb').read()
                image_encoded = pybase64.urlsafe_b64encode(image_data).decode('utf-8')
                bboxes = [points_to_xywh(shape) for shape in self.main_window.canvas.shapes]
                labels = [shape.label for shape in self.main_window.canvas.shapes]
                request_data = RequestData(
                    bboxes=bboxes,
                    algo_name=self.model_name,
                    algo_param=self.model_param,
                    image_data=image_encoded,
                    request_id="",
                    image_width=width,
                    image_height=height
                )
                json_reqeust_data = json.dumps(request_data, default=lambda o: o.__dict__)
                host_post_url = self.config.get("HOST_PORT_URL")
                action_url = self.config.get("LAUNCH_URL")
                try:
                    response = requests.post(host_post_url + action_url, json=json_reqeust_data)
                    response = response.json()
                    request_id = response["request_id"]

                    if not response["status"] == "200":
                        # QMessageBox.information(self.main_window, u'错误', response["message"])
                        self.show_message_signal.emit("错误",
                                                      f'错误代码：{response["status"]}, 详细信息：{response["message"]}')
                        logger.debug(f'错误代码：{response["status"]}, 详细信息：{response["message"]}')
                        return
                except Exception as e:
                    self.show_message_signal.emit("错误", f'详细信息：{str(e)}')
                    logger.debug(f'详细信息：{str(e)}')
                    return

            try:
                shapes = [points_to_xywh(shape) for shape in self.main_window.canvas.shapes]
                labels = [shape.label for shape in self.main_window.canvas.shapes]
            except Exception as e:
                logger.debug(str(e))

            image_nums = 0  # 当前标注的样本数量
            time_total_used = 0  # 标注花费的时间


            while (True):
                if self.is_stoped:
                    break
                if self.main_window.cur_img_idx >= len(self.main_window.m_img_list):
                    logger.debug(f'cur_img_idx={self.main_window.cur_img_idx}, len={len(self.main_window.m_img_list)}')
                    time.sleep(1)
                    pass
                else:
                    t = time.time()
                    filename = self.main_window.m_img_list[self.main_window.cur_img_idx]
                    if os.path.exists(filename):
                        image = Image.open(filename)
                        # 获取图片的宽度和高度
                        width, height = image.size
                        image.close()

                        image_data = open(filename, 'rb').read()
                        image_encoded = pybase64.urlsafe_b64encode(image_data).decode('utf-8')
                        # shapes = [points_to_xywh(shape) for shape in self.main_window.canvas.shapes]
                        # labels = [shape.label for shape in self.main_window.canvas.shapes]
                        print(labels)
                        request_data = RequestData(
                            bboxes=shapes,
                            algo_name=self.model_name,
                            algo_param=self.model_param,
                            image_data=image_encoded,
                            image_width=width,
                            image_height=height,
                            request_id=request_id
                        )
                        json_data = json.dumps(request_data, default=lambda o: o.__dict__)
                        host_post_url = self.config.get("HOST_PORT_URL")
                        action_url = self.config.get("TRACK_NEXT_URL")
                        # action_url = "/api/v1/mot/pytracking/track_next"
                        try:
                            response = requests.post(host_post_url + action_url, json=json_data)
                            response = response.json()
                        except Exception as e:
                            self.show_message_signal.emit("错误", f'详细信息：{str(e)}')
                            logger.debug(f'详细信息：{str(e)}')
                            return

                        results = []
                        print('bboxes=', response["bboxes"])

                        for bbox in response["bboxes"]:
                            result = {}
                            result["points"] = xywh_to_points(bbox["x"], bbox["y"], bbox["w"], bbox["h"],
                                                              image_width=width, image_height=height)
                            results.append(result)

                        logger.debug(filename)
                        logger.debug(response["bboxes"])
                        logger.debug(f'len result: {len(results)}, len labels: {len(labels)}')
                        image_nums += 1
                        time_used = time.time() - t
                        time_total_used += time_used
                        fps = image_nums / time_total_used
                        logger.debug(f'模型: {self.model_name},  标注速度 {fps} frame/second')
                        assert (len(results) == len(labels))

                        for i in range(len(labels)):
                            results[i]["label"] = labels[i]

                        self.save_file_signal.emit(results, self.main_window.cur_img_idx)

                        # self.main_window.queue.put((results, self.main_window.cur_img_idx))
                        #   TODO: 把写入的过程变成异步的，将内容写入队列
                        # time.sleep(0.5)
                    # self.main_window.cur_img_idx += 1
                    self.main_window.cur_img_idx_move_to_next()
                    time.sleep(self.speed_track)
                    print("speed",self.speed_track)
        except Exception as e:
            print(e)
            logger.debug(e)
        return

    def do_call_local_api(self):
        image_files = self.main_window.m_img_list

        # shapes = self.main_window.canvas.shapes["points"]

        def format_shape(s):
            return dict(label=s.label,
                        line_color=s.line_color.getRgb(),
                        fill_color=s.fill_color.getRgb(),
                        points=[(p.x(), p.y()) for p in s.points],
                        # add chris
                        difficult=s.difficult)

        shapes = [format_shape(shape) for shape in self.main_window.canvas.shapes]

        if self.main_window.cur_img_idx < len(image_files):
            opencvtrakcer = OpenCVTracker(image_files=image_files,
                                          shapes=shapes,
                                          cur_img_idx=self.main_window.cur_img_idx,
                                          tracker_name=self.model_name)
        else:
            print("cur img idx out of range!", self.main_window.cur_img_idx)
            logger.debug(f'cur img idx out of range!", {self.main_window.cur_img_idx}')
            return

        image_nums = 0  # 当前标注的样本数量
        time_total_used = 0  # 标注花费的时间
        while (True):
            # print('cur_img_idx:', self.main_window.cur_img_idx)
            if self.is_stoped:
                break

            if self.main_window.cur_img_idx >= len(self.main_window.m_img_list):
                print(f'cur_img_idx={self.main_window.cur_img_idx}, len={len(self.main_window.m_img_list)}')
                time.sleep(1)
                pass
            else:
                t = time.time()
                filename = self.main_window.m_img_list[self.main_window.cur_img_idx]
                if filename:
                    result = opencvtrakcer.do_tracking(filename)
                    print(result)
                    self.save_file_signal.emit(result, self.main_window.cur_img_idx)
                    image_nums += 1
                    time_used = time.time() - t
                    time_total_used += time_used
                    fps = image_nums / time_total_used
                    logger.debug(f'模型: {self.model_name},  标注速度 {fps} frame/second')
                    # self.main_window.queue.put((result, self.main_window.cur_img_idx))
                # self.main_window.cur_img_idx += 1
                self.main_window.cur_img_idx_move_to_next()
                time.sleep(self.speed_track)
        return

    def run(self):
        if self.remote:
            self.do_call_remote_api()
        else:
            self.do_call_local_api()

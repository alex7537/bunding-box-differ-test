import cv2
import json
import os
import logging
from typing import List, Dict, Any, Optional

import numpy as np

# 配置日志
logging.basicConfig(
    level=logging.DEBUG,  # 根据需要设置为 INFO 或 WARNING
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)

logger = logging.getLogger('mylogger')


class OpenCVTracker:
    TRACKER_FACTORIES = {
        'BOOSTING': 'TrackerBoosting_create',
        'MIL': 'TrackerMIL_create',
        'KCF': 'TrackerKCF_create',
        'TLD': 'TrackerTLD_create',
        'MEDIANFLOW': 'TrackerMedianFlow_create',
        'MOSSE': 'TrackerMOSSE_create',
        'CSRT': 'TrackerCSRT_create'
    }

    def __init__(self, image_files: List[str], shapes: List[Dict[str, Any]],
                 cur_img_idx: int, tracker_name: str):
        """
        初始化 OpenCVTracker 类。
        :param image_files: 图像文件路径列表。
        :param shapes: 包含点和标签的形状字典列表。
        :param cur_img_idx: 当前图像的索引。
        :param tracker_name: 使用的追踪器名称。
        """
        logger.debug('初始化 OpenCVTracker')
        self.image_files = image_files
        self.shapes = shapes
        logger.debug(f"形状: {shapes}")
        self.cur_img_idx = cur_img_idx

        self.trackers = cv2.legacy.MultiTracker_create()

        # frame = cv2.imread(image_files[cur_img_idx])
        frame = cv2.imdecode(np.fromfile(image_files[cur_img_idx], dtype=np.uint8), cv2.IMREAD_COLOR)
        if frame is None:
            logger.error(f"无法读取初始图像: {image_files[cur_img_idx]}")
            raise FileNotFoundError(f"图像未找到: {image_files[cur_img_idx]}")

        self.init_tracker(tracker_name=tracker_name, frame=frame)

    @classmethod
    def is_tracker_available(cls, trackerType: str) -> bool:
        if trackerType.startswith("inner_opencv_tracker_"):
            trackerType = trackerType[len("inner_opencv_tracker_"):]
        legacy = getattr(cv2, 'legacy', None)
        factory_name = cls.TRACKER_FACTORIES.get(trackerType.upper())
        return legacy is not None and factory_name is not None and hasattr(legacy, factory_name)

    def createTrackerByName(self, trackerType: str):
        """
        根据追踪器名称创建追踪器。
        :param trackerType: 追踪器名称。
        :return: OpenCV 追踪器对象或 None。
        """
        if trackerType.startswith("inner_opencv_tracker_"):
            trackerType = trackerType[len("inner_opencv_tracker_"):]

        factory_name = self.TRACKER_FACTORIES.get(trackerType.upper())
        tracker_func = getattr(getattr(cv2, 'legacy', None), factory_name, None) if factory_name else None
        if tracker_func is None:
            logger.error(f"不支持的追踪器类型: {trackerType}")
            return None

        return tracker_func()

    def init_tracker(self, tracker_name: str, frame: Any):
        """
        初始化所有追踪器。
        :param tracker_name: 追踪器名称。
        :param frame: 初始化帧。
        """
        logger.debug("初始化所有追踪器")
        for idx, shape in enumerate(self.shapes):
            tracker = self.createTrackerByName(tracker_name)
            if tracker is None:
                logger.error(f"无法为形状索引 {idx} 创建追踪器")
                continue
            try:
                bbox = self.shape_to_box(shape)
                self.trackers.add(tracker, frame, bbox)
                logger.debug(f"已添加追踪器 {tracker_name}，形状索引 {idx}，边界框 {bbox}")
            except Exception as e:
                logger.error(f"添加追踪器时出错，形状索引 {idx}: {e}")

    @staticmethod
    def shape_to_box(shape: Dict[str, Any]) -> tuple:
        """
        将形状点转换为边界框。
        :param shape: 包含 'points' 的字典。
        :return: 边界框元组 (x, y, w, h)。
        """
        points = shape.get("points", [])
        if len(points) < 4:
            logger.error(f"形状点数不足，无法定义边界框: {points}")
            raise ValueError("形状必须包含至少四个点。")

        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        x_min, x_max = min(xs), max(xs)
        y_min, y_max = min(ys), max(ys)
        w = x_max - x_min
        h = y_max - y_min

        if w == 0 or h == 0:
            logger.error(f"无效的边界框，宽度或高度为零: x={x_min}, y={y_min}, w={w}, h={h}")
            raise ValueError("边界框的宽度和高度必须大于零。")

        logger.debug(f"将形状转换为边界框: x={x_min}, y={y_min}, w={w}, h={h}")
        return x_min, y_min, w, h

    def do_tracking(self, image_file: str) -> Optional[List[Dict[str, Any]]]:
        """
        更新追踪器并返回新的形状位置。
        :param image_file: 新图像文件路径。
        :return: 更新后的形状列表或 None。
        """
        frame = cv2.imread(image_file)
        if frame is None:
            logger.error(f"无法读取图像: {image_file}")
            return None
        try:
            success, boxes = self.trackers.update(frame)
            if not success:
                logger.warning("追踪更新失败。")
                return None

            def xywh_to_xy_points(box):
                x, y, w, h = box
                return [(x, y), (x, y + h), (x + w, y + h), (x + w, y)]

            shapes = []
            if len(self.shapes) != len(boxes):
                logger.warning("追踪对象数量发生变化。")
                return None
            for idx, box in enumerate(boxes):
                if box[2] <= 0 or box[3] <= 0:
                    logger.error(f"无效的边界框，宽度或高度为零: {box}")
                    continue
                shape = {
                    "points": xywh_to_xy_points(box),
                    "label": self.shapes[idx].get("label", "")
                }
                shapes.append(shape)
            logger.debug(f"更新后的形状: {shapes}")
            return shapes.copy()
        except cv2.error as e:
            logger.error(f"OpenCV 追踪过程中出错: {e}")
        except Exception as e:
            logger.error(f"追踪过程中发生意外错误: {e}")
        return None

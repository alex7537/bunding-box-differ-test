#!/usr/bin/env python
# -*- coding: utf-8 -*-
import argparse
import asyncio
import codecs
import datetime
import io
import math
from queue import Queue
from PIL import Image
import cProfile

import os.path
import platform
import shutil
import webbrowser as wb
from functools import partial

import numpy as np
import yaml
from PIL import ImageEnhance
from PIL.ImageFile import ImageFile
from watchdog.observers import Observer
from concurrent.futures import ThreadPoolExecutor, as_completed, ProcessPoolExecutor, wait
from scipy.ndimage import map_coordinates
from libs.callapi import *
from libs.canvas import Canvas
from libs.colorDialog import ColorDialog
from libs.combobox import ComboBox
from libs.constants import *
from libs.create_ml_io import CreateMLReader
from libs.create_ml_io import JSON_EXT
from libs.data_tools import DataMainWindow
from libs.hashableQListWidgetItem import HashableQListWidgetItem
from libs.labelDialog import LabelDialog
from libs.labelFile import LabelFile, LabelFileError, LabelFileFormat
from libs.load_yaml import LoadConfig
from libs.output_json import *
from libs.pascal_voc_io import PascalVocReader
from libs.pascal_voc_io import XML_EXT
from libs.resources import *
from libs.settings import Settings
from libs.shape import Shape, DEFAULT_LINE_COLOR, DEFAULT_FILL_COLOR
from libs.stringBundle import StringBundle
from libs.toolBar import ToolBar
from libs.ustr import ustr
from libs.utils import *
# from libs.autoLabeler import *
# from libs import autoLabeler
from libs.yolo2voc import *
from libs.yolo_io import TXT_EXT
from libs.yolo_io import YoloReader
from libs.zoomWidget import ZoomWidget
from libs.fileEventHandler import FileEventHandler, extensions
from watchdog.events import FileSystemEventHandler
# from watchdog.observers.inotify_buffer import
import logging
from libs.docker import show_docker_manager_window, DockerManagerApp

__appname__ = 'label_tools  1.0-alpha'

logger = logging.getLogger('mylogger')
logger.setLevel(logging.DEBUG)

if not os.path.exists('log'):
    os.mkdir('log')
logger = logging.getLogger('mylogger')
logger.setLevel(logging.DEBUG)

if not os.path.exists('log'):
    os.mkdir('log')

# 格式化时间字符串，避免非法字符
timestamp = datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')

# 创建日志文件路径
log_file_path = os.path.join('log', f'{timestamp}.log')

# 创建 FileHandler
fh = logging.FileHandler(log_file_path, encoding="utf-8")
fh.setLevel(logging.DEBUG)

# 创建日志格式
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
fh.setFormatter(formatter)

# 将 FileHandler 添加到 logger
logger.addHandler(fh)

Image.MAX_IMAGE_PIXELS = None  # 允许加载大图片


class MyHandler(FileSystemEventHandler):
    """
    监听文件夹变化，用于持续加载文件夹中新增的文件
    """

    def __init__(self, main_window):
        self.main_window = main_window
        self.cache_path = {}
        for i in range(self.main_window.file_list_widget.count()):
            self.cache_path[self.main_window.file_list_widget.item(i).text()] = True

    def on_deleted(self, event):
        import os
        t = time.time()
        file_path = event.src_path
        # 对删除的文件路径进行标准化处理
        file_norm = os.path.normpath(os.path.abspath(file_path))
        for i in range(self.main_window.file_list_widget.count()):
            # 获取列表中每个项目的文件路径，并进行标准化处理
            item_text = self.main_window.file_list_widget.item(i).text()
            item_norm = os.path.normpath(os.path.abspath(item_text))
            if file_norm == item_norm:
                self.main_window.file_list_widget.takeItem(i)
                if self.cache_path.get(file_norm):
                    del self.cache_path[file_norm]

                break
        # 更新内部文件列表
        self.main_window.m_img_list = [
            self.main_window.file_list_widget.item(i).text()
            for i in range(self.main_window.file_list_widget.count())
        ]
        logger.debug(f'delete {file_norm}, using {time.time() - t} sec')

    def on_any_event(self, event):
        pass  # logger.debug(event)

    def is_repeated_path(self, path):
        if self.cache_path.get(path):
            return True
        return False

    def do_cache_path(self, path):
        self.cache_path[path] = True

    def on_moved(self, event):
        t = time.time()
        logger.debug(event)
        filepath = event.dest_path
        if event.dest_path.lower().endswith(tuple(extensions)):
            if self.is_repeated_path(filepath):
                return
            item = QListWidgetItem(filepath)
            self.main_window.file_list_widget.addItem(item)
            self.main_window.m_img_list.append(filepath)
            self.do_cache_path(filepath)
            logger.debug(f'on moved 插入图片 {filepath}, using {time.time() - t}sec')

    def on_closed(self, event):
        if event.is_directory:
            return
        if event.src_path.lower().endswith(tuple(extensions)):
            t = time.time()
            logger.debug(event)
            filepath = event.src_path
            if self.is_repeated_path(filepath):
                return
            item = QListWidgetItem(filepath)
            self.main_window.file_list_widget.addItem(item)
            self.main_window.m_img_list.append(filepath)
            self.do_cache_path(filepath)
            logger.debug(f'on closed 插入图片{filepath}, using {time.time() - t}sec')


class FrameExtractSettingsDialog(QDialog):
    def __init__(self, parent=None, default_interval=1,
                 default_width=1920, default_height=1080,
                 default_format="PNG"):
        super(FrameExtractSettingsDialog, self).__init__(parent)
        self.setWindowTitle("提取帧设置")
        self.setWindowModality(Qt.WindowModal)

        layout = QFormLayout()

        # 帧间隔
        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(1, 999999)
        self.interval_spin.setValue(default_interval)
        layout.addRow("帧间隔 (每隔多少帧提取一次)：", self.interval_spin)

        # 图像宽度
        self.width_spin = QSpinBox()
        self.width_spin.setRange(1, 999999)
        self.width_spin.setValue(default_width)
        layout.addRow("图像宽度：", self.width_spin)

        # 图像高度
        self.height_spin = QSpinBox()
        self.height_spin.setRange(1, 999999)
        self.height_spin.setValue(default_height)
        layout.addRow("图像高度：", self.height_spin)

        # 图像格式
        self.format_combo = QComboBox()
        self.format_combo.addItems(["PNG", "JPG", "BMP"])
        # 默认值
        index = self.format_combo.findText(default_format)
        if index >= 0:
            self.format_combo.setCurrentIndex(index)
        layout.addRow("图像格式：", self.format_combo)

        # 确定 / 取消
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addRow(button_box)

        self.setLayout(layout)

    def get_values(self):
        """
        获取用户在对话框中输入/选择的所有值
        """
        interval = self.interval_spin.value()
        width = self.width_spin.value()
        height = self.height_spin.value()
        format_str = self.format_combo.currentText()
        return interval, width, height, format_str


class ImageProcessingWorker(QThread):
    result_signal = pyqtSignal(object)

    def __init__(self, img_array, black_level, white_level, gamma, parent=None):
        super().__init__(parent)
        self.img_array = img_array
        self.black_level = black_level
        self.white_level = white_level
        self.gamma = gamma
        self.scale = 255.0 / (self.white_level - self.black_level)
        self.inv_gamma = 1.0 / self.gamma
        self.lookup_table = np.array([(i / 255.0) ** self.inv_gamma * 255.0 for i in range(256)], dtype='uint8')

    def run(self):
        start_time = time.time()

        # 检查并转换图像通道数
        self.img_array = self.convert_to_3_channels(self.img_array)

        if len(self.img_array.shape) == 2:
            height, width = self.img_array.shape
            channels = 1
        elif len(self.img_array.shape) == 3:
            height, width, channels = self.img_array.shape
        else:
            print("不支持的图像格式")
            return

        print(f"图像尺寸: 高度={height}, 宽度={width}, 通道数={channels}")
        num_blocks = 16  # 根据实际情况调整块的数量
        block_height = height // num_blocks

        with ThreadPoolExecutor() as executor:
            futures = [
                executor.submit(
                    self.process_block,
                    self.img_array[i * block_height:(i + 1) * block_height, :]
                )
                for i in range(num_blocks)
            ]
            results = [future.result() for future in futures]

        # 合并处理后的块
        final_result = np.vstack(results)

        # 发回处理后的完整图像
        self.result_signal.emit(final_result)

        end_time = time.time()
        print(f"图像处理完成，共耗时: {end_time - start_time:.3f} 秒")

    def convert_to_3_channels(self, img):
        """如果图像有4个通道，则转换为3通道"""
        if len(img.shape) == 3 and img.shape[2] == 4:
            print("检测到4通道图像，正在转换为3通道...")
            img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
        return img

    def process_block(self, img_block):
        """处理单个图像块"""
        adjusted = cv2.convertScaleAbs(img_block, alpha=self.scale, beta=-self.black_level * self.scale)
        adjusted = cv2.LUT(adjusted, self.lookup_table)
        return adjusted


class AutoAdjustmentWorker(QThread):
    adjustment_signal = pyqtSignal(float, float)

    def __init__(self, img_array, parent=None, num_threads=16):
        super().__init__(parent)
        self.img_array = img_array
        self.num_threads = num_threads

    def run(self):
        try:
            # 检查并转换图像通道数
            self.img_array = self.convert_to_3_channels(self.img_array)

            # 分块计算黑白场
            split_arrays = np.array_split(self.img_array, self.num_threads, axis=0)

            with ThreadPoolExecutor(max_workers=self.num_threads) as executor:
                futures = [executor.submit(self.calculate_percentiles, part) for part in split_arrays]

                black_levels, white_levels = zip(*(future.result() for future in as_completed(futures)))

            # 计算全局黑白场
            black_level = min(black_levels)
            white_level = max(white_levels)

            self.adjustment_signal.emit(black_level, white_level)

        except Exception as e:
            print(f"自适应色阶计算时出错: {e}")

    def convert_to_3_channels(self, img):
        """如果图像有4个通道，则转换为3通道"""
        if len(img.shape) == 3 and img.shape[2] == 4:
            print("检测到4通道图像，正在转换为3通道...")
            img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
        return img

    def calculate_percentiles(self, img_part):
        """计算每部分的 2% 和 98% 分位数。"""
        black_level = np.percentile(img_part, 2)
        white_level = np.percentile(img_part, 98)
        return black_level, white_level


class WindowMixin(object):
    def menu(self, title, actions=None):
        self.setStyleSheet("QMenu::item:selected { background-color: #0078D7; color: black; }")
        menu = self.menuBar().addMenu(title)
        if actions:
            add_actions(menu, actions)
        return menu

    def toolbar(self, title, actions=None):
        toolbar = ToolBar(title)
        toolbar.setObjectName(u'%sToolBar' % title)
        # toolbar.setOrientation(Qt.Vertical)
        toolbar.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        if actions:
            add_actions(toolbar, actions)
        self.addToolBar(Qt.LeftToolBarArea, toolbar)
        return toolbar


class MainWindow(QMainWindow, WindowMixin, QWidget):
    FIT_WINDOW, FIT_WIDTH, MANUAL_ZOOM = list(range(3))
    stop_signal = pyqtSignal()
    models_info = []  # 定义为类属性，可以在整个类中访问

    def __init__(self, default_filename=None, default_prefdef_class_file=None, default_save_dir=None):
        super(MainWindow, self).__init__()
        self.start_time = None  # 用于记录滑块停止到界面更新的起始时间

        self.undo_stack = []

        # self.current_adjustments = None
        self.new_windows_exists = False

        self.setStyleSheet("QMenu::item:selected { background-color: #0078D7; color: black; }")

        self.cache_v = 0  # v
        self.cache_h = 0  # height
        self.cache_z = 100  # zoom_widget_value

        self.sample_numbers = 0
        self.model_combobox = None  # 初始化为 None
        self.task_start_time = time.time()  # start time
        self.desp_json = {}

        self.update_timer = QTimer()  # 防止频繁更新
        self.update_timer.setSingleShot(True)
        self.update_timer.timeout.connect(self.applyAdjustments)

        self.current_adjustments = {'black_level': 10, 'white_level': 255, 'gamma': 1.0}
        self.thread_pool = QThreadPool()
        self.original_image = None
        self.img_array = None  # 存储当前加载的 NumPy 数组
        # self.current_adjustments = {
        #     'brightness': 100,
        #     'contrast': 100,
        #     'red_levels': 100,
        #     'green_levels': 100,
        #     'blue_levels': 100,
        # }

        self.current_adjustments = {'black_level': 10, 'white_level': 255, 'gamma': 100}

        config_loader = LoadConfig()
        self.isOutputJson = True
        self.isOutputJson = config_loader.get_is_output_json()
        logger.debug(f'是否输出JSON: {self.isOutputJson}')

        config = config_loader.load_models()
        # print(config_loader.load_models())
        # self.model_combobox.addItem("")  # 第一行为空
        self.models_info = config.get('models', [])
        # MainWindow.models_info = config.get('models', [])
        # 获取模型名称列表
        self.model_names = [
            model['model_name'] for model in self.models_info
            if not model['model_name'].startswith('inner_opencv_tracker_')
            or OpenCVTracker.is_tracker_available(model['model_name'])
        ]
        # print(self.models_info)
        self.model_combobox = QComboBox()
        self.model_combobox.addItem("")  # 第一行为空
        for model_name in self.model_names:
            self.model_combobox.addItem(model_name)
        self.model_combobox.currentIndexChanged.connect(self.model_combobox_changed)

        print("Model ComboBox Initialized!")  # 添加的调试语句
        # 输出至description.json
        self.desp_path = ""  # "/home/server/.micros/cognition/desc/descriptions.json"

        self.observer = None
        self.setWindowTitle(__appname__)
        self.setStyleSheet("background-color:white")

        # Load setting in the main thread
        self.settings = Settings()
        self.settings.load()
        settings = self.settings
        self.settings.reset()
        self.os_name = platform.system()

        # Load string bundle for i18n
        self.string_bundle = StringBundle.get_bundle()
        get_str = lambda str_id: self.string_bundle.get_string(str_id)

        # Save as yolo
        self.default_save_dir = config_loader.get_paths("default_save_dir_path")
        self.label_file_format = settings.get(SETTING_LABEL_FILE_FORMAT, LabelFileFormat.YOLO)

        # For loading all image under a directory
        self.m_img_list = []
        self.dir_name = None
        self.label_hist = []
        self.last_open_dir = None
        self.cur_img_idx = 0
        self.img_count = 0
        self.default_save_dir = self.last_open_dir
        self.label_file_format = settings.get(SETTING_LABEL_FILE_FORMAT, LabelFileFormat.YOLO)
        # Whether we need to save or not.
        self.dirty = False

        self._no_selection_slot = False
        self._beginner = True
        self.screencast = ""

        # Load predefined classes to the list
        # self.load_predefined_classes(default_prefdef_class_file)

        # Main widgets and related state.
        self.label_dialog = LabelDialog(parent=self, list_item=self.label_hist)

        self.items_to_shapes = {}
        self.shapes_to_items = {}
        self.prev_label_text = ''

        list_layout = QVBoxLayout()
        list_layout.setContentsMargins(0, 0, 0, 0)

        list_layout.addWidget(self.model_combobox)

        # Create a widget for using default label
        self.use_default_label_checkbox = QCheckBox(get_str('useDefaultLabel'))
        self.use_default_label_checkbox.setChecked(False)
        self.default_label_text_line = QComboBox()
        self.default_label_text_line.addItem("")  # 第一行为空
        self.subcategory_combo = QComboBox(self)
        use_default_label_qhbox_layout = QHBoxLayout()
        use_default_label_qhbox_layout.addWidget(self.use_default_label_checkbox)
        use_default_label_qhbox_layout.addWidget(self.default_label_text_line)
        use_default_label_qhbox_layout.addWidget(self.subcategory_combo)

        self.load_categories_from_yaml('config/tags.yaml')

        # 信号连接：当一级菜单改变时，更新二级菜单
        self.default_label_text_line.currentIndexChanged.connect(self.update_subcategories)

        use_default_label_container = QWidget()
        use_default_label_container.setLayout(use_default_label_qhbox_layout)

        # Create a widget for edit and diffc button
        # self.diffc_button = QCheckBox(get_str('useDifficult'))
        # self.diffc_button.setChecked(False)
        # self.diffc_button.stateChanged.connect(self.button_state)

        self.enable_enhance_checkbox = QCheckBox("启用图像增强")
        self.enable_enhance_checkbox.setChecked(False)  # 默认开启
        self.enable_enhance_checkbox.stateChanged.connect(self.updateImage)
        list_layout.addWidget(self.enable_enhance_checkbox)

        self.black_level_slider = QSlider(Qt.Horizontal, self)
        self.black_level_slider.setRange(1, 100)
        self.black_level_slider.setValue(0)
        self.black_level_slider.valueChanged.connect(self.updateImage)

        # 创建白场滑块 (White Level)
        self.white_level_slider = QSlider(Qt.Horizontal, self)
        self.white_level_slider.setRange(155, 255)
        self.white_level_slider.setValue(255)
        self.white_level_slider.valueChanged.connect(self.updateImage)

        # 创建 Gamma 滑块 (中间灰度)
        self.gamma_slider = QSlider(Qt.Horizontal, self)
        self.gamma_slider.setRange(10, 300)
        self.gamma_slider.setValue(100)  # 对应 1.0 值
        self.gamma_slider.valueChanged.connect(self.updateImage)

        list_layout.addWidget(QLabel('Black Level'))
        list_layout.addWidget(self.black_level_slider)

        list_layout.addWidget(QLabel('White Level'))
        list_layout.addWidget(self.white_level_slider)

        list_layout.addWidget(QLabel('Gamma (x 0.01)'))
        list_layout.addWidget(self.gamma_slider)
        # 添加SpinBox组件来添加控制标注速度
        self.speed_track = 0.02
        self.speed_label = QLabel("标注速度控制：")
        self.double_spin_box = QDoubleSpinBox()
        self.double_spin_box.setMinimum(0.02)
        self.double_spin_box.setMaximum(1)
        self.double_spin_box.setSingleStep(0.02)
        self.double_spin_box.valueChanged.connect(self.on_value_changed)

        self.edit_button = QToolButton()
        self.edit_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)

        # Add some of widgets to list_layout
        # list_layout.addWidget(self.edit_button)
        # list_layout.addWidget(self.diffc_button)
        list_layout.addWidget(use_default_label_container)

        # SpinBox组件布局
        list_layout.addWidget(self.speed_label)
        list_layout.addWidget(self.double_spin_box)
        list_layout.addStretch()

        # Create and add combobox for showing unique labels in group
        self.combo_box = ComboBox(self)
        list_layout.addWidget(self.combo_box)

        # Create and add a widget for showing current label items
        self.label_list = QListWidget()
        label_list_container = QWidget()
        label_list_container.setLayout(list_layout)
        self.label_list.itemActivated.connect(self.label_selection_changed)
        self.label_list.itemSelectionChanged.connect(self.label_selection_changed)
        # self.label_list.itemClicked.connect(self.move_to_center)
        self.label_list.itemDoubleClicked.connect(self.edit_label)
        # Connect to itemChanged to detect checkbox changes.
        self.label_list.itemChanged.connect(self.label_item_changed)
        # 点击标签，标注框居中显示
        self.label_list.itemClicked.connect(self.center_label_on_canvas)

        list_layout.addWidget(self.label_list)

        self.dock = QDockWidget(get_str('boxLabelText'), self)

        self.dock.setObjectName(get_str('labels'))
        self.dock.setWidget(label_list_container)

        self.file_list_widget = QListWidget()
        # self.file_list_widget.itemDoubleClicked.connect(self.file_item_double_clicked)
        self.file_list_widget.itemDoubleClicked.connect(self.file_item_double_clicked)
        file_list_layout = QVBoxLayout()
        file_list_layout.setContentsMargins(0, 0, 0, 0)
        file_list_layout.addWidget(self.file_list_widget)
        file_list_container = QWidget()
        file_list_container.setLayout(file_list_layout)
        self.file_dock = QDockWidget(get_str('fileList'), self)
        self.file_dock.setObjectName(get_str('files'))
        self.file_dock.setWidget(file_list_container)

        self.zoom_widget = ZoomWidget()
        self.color_dialog = ColorDialog(parent=self)

        self.canvas = Canvas(parent=self)
        self.canvas.main_window = self
        self.canvas.zoomRequest.connect(self.zoom_request)
        self.canvas.set_drawing_shape_to_square(settings.get(SETTING_DRAW_SQUARE, False))

        scroll = QScrollArea()
        scroll.setWidget(self.canvas)
        scroll.setWidgetResizable(True)
        self.scroll_bars = {
            Qt.Vertical: scroll.verticalScrollBar(),
            Qt.Horizontal: scroll.horizontalScrollBar()
        }
        self.scroll_area = scroll
        self.canvas.scrollRequest.connect(self.scroll_request)

        self.canvas.newShape.connect(self.new_shape)
        self.canvas.shapeMoved.connect(self.set_dirty)
        self.canvas.selectionChanged.connect(self.shape_selection_changed)
        self.canvas.drawingPolygon.connect(self.toggle_drawing_sensitive)
        self.setCentralWidget(scroll)
        self.addDockWidget(Qt.RightDockWidgetArea, self.dock)
        self.addDockWidget(Qt.RightDockWidgetArea, self.file_dock)
        self.file_dock.setFeatures(QDockWidget.DockWidgetFloatable)

        self.dock_features = QDockWidget.DockWidgetClosable | QDockWidget.DockWidgetFloatable
        self.dock.setFeatures(self.dock.features() ^ self.dock_features)
        self.start_folder_watcher()

        # Actions
        action = partial(new_action, self)
        quit = action(get_str('quit'), self.close,
                      'Ctrl+Q', 'quit', get_str('quitApp'))

        open = action(get_str('openFile'), self.open_file,
                      'Ctrl+O', 'open', get_str('openFileDetail'))

        open_dir = action(get_str('openDir'), self.open_dir_dialog,
                          'Ctrl+u', 'open', get_str('openDir'))

        change_save_dir = action(get_str('changeSaveDir'), self.change_save_dir_dialog,
                                 'Ctrl+r', 'open', get_str('changeSavedAnnotationDir'))

        change_desp_json_dir = action(get_str('changeDespJsonDir'), self.change_desp_json_dir_dialog,
                                      'Ctrl+r', 'open', get_str('changeSavedDespJsonDir'))

        open_annotation = action(get_str('openAnnotation'), self.open_annotation_dialog,
                                 'Ctrl+Shift+O', 'open', get_str('openAnnotationDetail'))
        copy_prev_bounding = action(get_str('copyPrevBounding'), self.copy_previous_bounding_boxes, 'Ctrl+v', 'copy',
                                    get_str('copyPrevBounding'))

        open_next_image = action(get_str('nextImg'), self.open_next_image,
                                 'd', 'next', get_str('nextImgDetail'))

        open_prev_image = action(get_str('prevImg'), self.open_prev_image,
                                 'a', 'prev', get_str('prevImgDetail'))

        save = action(get_str('save'), self.save_file,
                      'Ctrl+S', 'save', get_str('saveDetail'), enabled=False)

        autolabel = action(get_str('autoLabel'), self.auto_label, 'Ctrl+space', 'autolabel', get_str('autoLabelDetail'))
        # label = action(get_str('skamma'), self.label(), 'Ctrl+P', 'autolabel', get_str('autoLabelDetail'))

        stopautolabel = action(get_str('stopautoLabel'), self.stop_auto_label, 'space', 'stopautolabel',
                               get_str('autoLabelDetail'))

        save_json = action(get_str('save_json'), self.save_json, 'Ctrl+P', 'autolabel', get_str('autoLabelDetail'),
                           enabled=self.isOutputJson)

        docker_manager = action(get_str('docker_manager'), self.docker_manager, 'Ctrl+P', 'docker', )
        undo_action = action(get_str('undo_action'), self.undo_delete, 'Ctrl+z')

        # data_process = action(get_str('data_process'), self.data_process, 'Ctrl+M', 'data', )

        def get_format_meta(format):
            """
            返回所选格式的元信息 (标题, 图标名称)。
            """
            format_mapping = {
                LabelFileFormat.PASCAL_VOC: ('&PascalVOC', 'format_voc'),
                LabelFileFormat.YOLO: ('&YOLO(TO VOC)', 'format_yolo'),
            }
            # 提供默认值，避免未知格式时崩溃
            return format_mapping.get(format, ('&Unknown', 'format_unknown'))

        save_format = action(get_format_meta(self.label_file_format)[0],
                             self.change_format, 'Ctrl+',
                             get_format_meta(self.label_file_format)[1],
                             get_str('changeSaveFormat'), enabled=True)

        save_format_beginner = action(get_format_meta(self.label_file_format)[0],
                                      self.change_format_beginner, 'Ctrl+',
                                      get_format_meta(self.label_file_format)[1],
                                      get_str('changeSaveFormat'), enabled=True)

        save_as = action(get_str('saveAs'), self.save_file_as,
                         'Ctrl+Shift+S', 'save-as', get_str('saveAsDetail'), enabled=False)

        close = action(get_str('closeCur'), self.close_file, 'Ctrl+W', 'close', get_str('closeCurDetail'))

        delete_image = action(get_str('deleteImg'), self.delete_image, 'Ctrl+Shift+D', 'close',
                              get_str('deleteImgDetail'))

        reset_all = action(get_str('resetAll'), self.reset_all, None, 'resetall', get_str('resetAllDetail'))

        color1 = action(get_str('boxLineColor'), self.choose_color1,
                        'Ctrl+L', 'color_line', get_str('boxLineColorDetail'))

        create_mode = action(get_str('crtBox'), self.set_create_mode,
                             'w', 'new', get_str('crtBoxDetail'), enabled=False)
        edit_mode = action(get_str('editBox'), self.set_edit_mode,
                           'Ctrl+J', 'edit', get_str('editBoxDetail'), enabled=False)

        create = action(get_str('crtBox'), self.create_shape,
                        'w', 'new', get_str('crtBoxDetail'), enabled=False)
        delete = action(get_str('delBox'), self.delete_selected_shape,
                        'Delete', 'delete', get_str('delBoxDetail'), enabled=False)
        copy = action(get_str('dupBox'), self.copy_selected_shape,
                      'Ctrl+c', 'copy', get_str('dupBoxDetail'),
                      enabled=False)

        # advanced_mode = action(get_str('advancedMode'), self.toggle_advanced_mode,
        #                        'Ctrl+Shift+A', 'expert', get_str('advancedModeDetail'),
        #                        checkable=True)

        hide_all = action(get_str('hideAllBox'), partial(self.toggle_polygons, False),
                          'Ctrl+H', 'hide', get_str('hideAllBoxDetail'),
                          enabled=False)
        show_all = action(get_str('showAllBox'), partial(self.toggle_polygons, True),
                          'Ctrl+A', 'hide', get_str('showAllBoxDetail'),
                          enabled=False)

        # help_default = action("Github Page", self.show_default_tutorial_dialog, None, 'help', get_str('tutorialDetail'))
        show_info = action(get_str('info'), self.show_info_dialog, None, 'help', get_str('info'))
        show_shortcut = action(get_str('shortcut'), self.show_shortcuts_dialog, None, 'help', get_str('shortcut'))

        zoom = QWidgetAction(self)
        zoom.setDefaultWidget(self.zoom_widget)
        self.zoom_widget.setWhatsThis(
            u"Zoom in or out of the image. Also accessible with"
            " %s and %s from the canvas." % (format_shortcut("Ctrl+[-+]"),
                                             format_shortcut("Ctrl+Wheel")))
        self.zoom_widget.setEnabled(False)

        zoom_in = action(get_str('zoomin'), partial(self.add_zoom, 10),
                         'Ctrl++', 'zoom-in', get_str('zoominDetail'), enabled=False)
        zoom_out = action(get_str('zoomout'), partial(self.add_zoom, -10),
                          'Ctrl+-', 'zoom-out', get_str('zoomoutDetail'), enabled=False)
        zoom_org = action(get_str('originalsize'), partial(self.set_zoom, 100),
                          'Ctrl+=', 'zoom', get_str('originalsizeDetail'), enabled=False)
        fit_window = action(get_str('fitWin'), self.set_fit_window,
                            'Ctrl+F', 'fit-window', get_str('fitWinDetail'),
                            checkable=True, enabled=False)
        fit_width = action(get_str('fitWidth'), self.set_fit_width,
                           'Ctrl+Shift+F', 'fit-width', get_str('fitWidthDetail'),
                           checkable=True, enabled=False)
        # Group zoom controls into a list for easier toggling.
        zoom_actions = (self.zoom_widget, zoom_in, zoom_out,
                        zoom_org, fit_window, fit_width)
        self.zoom_mode = self.MANUAL_ZOOM
        self.scalers = {
            self.FIT_WINDOW: self.scale_fit_window,
            self.FIT_WIDTH: self.scale_fit_width,
            # Set to one to scale to 100% when loading files.
            self.MANUAL_ZOOM: lambda: 1,
        }

        edit = action(get_str('editLabel'), self.edit_label,
                      'Ctrl+E', 'edit', get_str('editLabelDetail'),
                      enabled=False)
        # self.edit_button.setDefaultAction(edit)

        shape_line_color = action(get_str('shapeLineColor'), self.choose_shape_line_color,
                                  icon='color_line', tip=get_str('shapeLineColorDetail'),
                                  enabled=False)
        shape_fill_color = action(get_str('shapeFillColor'), self.choose_shape_fill_color,
                                  icon='color', tip=get_str('shapeFillColorDetail'),
                                  enabled=False)

        labels = self.dock.toggleViewAction()
        labels.setText(get_str('showHide'))
        labels.setShortcut('Ctrl+Shift+L')

        # Label list context menu.
        label_menu = QMenu()
        add_actions(label_menu, (edit, delete))
        self.label_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.label_list.customContextMenuRequested.connect(
            self.pop_label_list_menu)

        # Draw squares/rectangles
        self.draw_squares_option = QAction(get_str('drawSquares'), self)
        self.draw_squares_option.setShortcut('Ctrl+Shift+R')
        self.draw_squares_option.setCheckable(True)
        self.draw_squares_option.setChecked(settings.get(SETTING_DRAW_SQUARE, False))
        self.draw_squares_option.triggered.connect(self.toggle_draw_square)

        # Store actions for further handling.
        self.actions = Struct(save=save, save_format=save_format, undo_action=undo_action,
                              # save_format_beginner=save_format_beginner,
                              saveAs=save_as, open=open, close=close, resetAll=reset_all, deleteImg=delete_image,
                              lineColor=color1, create=create, delete=delete, edit=edit, copy=copy,
                              createMode=create_mode, editMode=edit_mode,
                              shapeLineColor=shape_line_color, shapeFillColor=shape_fill_color,
                              zoom=zoom, zoomIn=zoom_in, zoomOut=zoom_out, zoomOrg=zoom_org,
                              fitWindow=fit_window, fitWidth=fit_width,
                              zoomActions=zoom_actions,
                              fileMenuActions=(
                                  open, open_dir, save, save_as, close, reset_all, quit),
                              beginner=(), advanced=(),
                              editMenu=(edit, copy, delete,
                                        None, color1, self.draw_squares_option),
                              beginnerContext=(create, edit, copy, delete),
                              advancedContext=(create_mode, edit_mode, edit, copy,
                                               delete, shape_line_color, shape_fill_color),
                              onLoadActive=(
                                  close, create, create_mode, edit_mode),
                              onShapesPresent=(save_as, hide_all, show_all))

        self.menus = Struct(
            file=self.menu(get_str('menu_file')),
            edit=self.menu(get_str('menu_edit')),
            view=self.menu(get_str('menu_view')),
            help=self.menu(get_str('menu_help')),
            recentFiles=QMenu(get_str('menu_openRecent')),
            labelList=label_menu)

        # Auto saving : Enable auto saving if pressing next
        self.auto_saving = QAction(get_str('autoSaveMode'), self)
        self.auto_saving.setCheckable(True)
        self.auto_saving.setChecked(settings.get(SETTING_AUTO_SAVE, False))
        # Sync single class mode from PR#106
        self.single_class_mode = QAction(get_str('singleClsMode'), self)
        self.single_class_mode.setShortcut("Ctrl+Shift+S")
        self.single_class_mode.setCheckable(True)
        self.single_class_mode.setChecked(settings.get(SETTING_SINGLE_CLASS, False))
        self.lastLabel = None
        # Add option to enable/disable labels being displayed at the top of bounding boxes
        self.display_label_option = QAction(get_str('displayLabel'), self)
        self.display_label_option.setShortcut("Ctrl+Shift+P")
        self.display_label_option.setCheckable(True)
        self.display_label_option.setChecked(settings.get(SETTING_PAINT_LABEL, False))
        self.display_label_option.triggered.connect(self.toggle_paint_labels_option)

        add_actions(self.menus.file,
                    (open, open_dir, change_save_dir, undo_action, change_desp_json_dir, copy_prev_bounding,
                     self.menus.recentFiles,
                     save,
                     save_format,
                     # save_format_beginner,
                     save_as, close, reset_all, delete_image, quit))
        add_actions(self.menus.help, (show_info, show_shortcut))
        add_actions(self.menus.view, (
            self.auto_saving,
            self.single_class_mode,
            self.display_label_option,
            labels, None,
            hide_all, show_all, None,
            zoom_in, zoom_out, zoom_org, None,
            fit_window, fit_width))

        self.menus.file.aboutToShow.connect(self.update_file_menu)

        # Custom context menu for the canvas widget:
        add_actions(self.canvas.menus[0], self.actions.beginnerContext)
        add_actions(self.canvas.menus[1], (
            action('&Copy here', self.copy_shape),
            action('&Move here', self.move_shape)))

        self.tools = self.toolbar('Tools')
        self.actions.beginner = (
            open_dir, change_save_dir, open_next_image, open_prev_image, save_format, save,
            # save_format_beginner,
            autolabel, stopautolabel,
            save_json, create, copy,
            delete,
            zoom_in, zoom_out, fit_window, fit_width, edit, docker_manager)
        # docker_manager, data_process
        self.actions.advanced = (
            open, open_dir, change_save_dir, open_next_image, open_prev_image, save, save_format, None,
            create_mode, edit_mode, None,
            hide_all, show_all)

        self.statusBar().showMessage('%s started.' % __appname__)
        self.statusBar().show()

        # Application state.
        self.image = QImage()
        self.file_path = self.last_open_dir
        # self.last_open_dir = None
        self.recent_files = []
        self.max_recent = 7
        self.line_color = None
        self.fill_color = None
        self.zoom_level = 100
        self.fit_window = False
        # Add Chris
        self.difficult = False

        # Fix the compatible issue for qt4 and qt5. Convert the QStringList to python list
        if settings.get(SETTING_RECENT_FILES):
            if have_qstring():
                recent_file_qstring_list = settings.get(SETTING_RECENT_FILES)
                self.recent_files = [ustr(i) for i in recent_file_qstring_list]
            else:
                self.recent_files = recent_file_qstring_list = settings.get(SETTING_RECENT_FILES)

        size = settings.get(SETTING_WIN_SIZE, QSize(2850, 1900))
        position = QPoint(0, 0)
        saved_position = settings.get(SETTING_WIN_POSE, position)
        # Fix the multiple monitors issue
        for i in range(QApplication.desktop().screenCount()):
            if QApplication.desktop().availableGeometry(i).contains(saved_position):
                position = saved_position
                break
        self.resize(size)
        self.move(position)
        save_dir = ustr(settings.get(SETTING_SAVE_DIR, None))
        self.last_open_dir = ustr(settings.get(SETTING_LAST_OPEN_DIR, None))

        self.restoreState(settings.get(SETTING_WIN_STATE, QByteArray()))
        Shape.line_color = self.line_color = QColor(settings.get(SETTING_LINE_COLOR, DEFAULT_LINE_COLOR))
        Shape.fill_color = self.fill_color = QColor(settings.get(SETTING_FILL_COLOR, DEFAULT_FILL_COLOR))
        self.canvas.set_drawing_color(self.line_color)
        # Add chris
        Shape.difficult = self.difficult

        def xbool(x):
            if isinstance(x, QVariant):
                return x.toBool()
            return bool(x)

        # if xbool(settings.get(SETTING_ADVANCE_MODE, False)):
        #     self.actions.advancedMode.setChecked(True)
        #     self.toggle_advanced_mode()

        # Populate the File menu dynamically.
        self.update_file_menu()

        # Since loading the file may take some time, make sure it runs in the background.
        if self.file_path and os.path.isdir(self.file_path):
            self.queue_event(partial(self.import_dir_images, self.file_path or ""))
        elif self.file_path:
            self.queue_event(partial(self.load_file, self.file_path or ""))

        # Callbacks:
        self.zoom_widget.valueChanged.connect(self.paint_canvas)

        self.populate_mode_actions()

        # Display cursor coordinates at the right of status bar
        self.label_coordinates = QLabel('')
        self.statusBar().addPermanentWidget(self.label_coordinates)

        # Open Dir if default file
        if self.file_path and os.path.isdir(self.file_path):
            self.open_dir_dialog(dir_path=self.file_path, silent=True)

        # self.load_file('./resources/icons/app.png')

    # 标注速度调整
    def on_value_changed(self):
        # global global_var
        self.speed_track = self.double_spin_box.value()
        print("speed", round(self.speed_track, 2))

    def model_combobox_changed(self):
        print("Model ComboBox Changed!")  # 添加的调试语句
        selected_model_name = self.model_combobox.currentText()

        if selected_model_name == "":
            return
        if selected_model_name.startswith('inner'):
            return
        else:
            print(selected_model_name)
            config_loader = LoadConfig()
            config_data = config_loader.load_model_config(selected_model_name)
            print(config_data)

    def keyReleaseEvent(self, event):
        if event.key() == Qt.Key_Control:
            self.canvas.set_drawing_shape_to_square(False)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Control:
            # Draw rectangle if Ctrl is pressed
            self.canvas.set_drawing_shape_to_square(True)

    # Support Functions #

    def canvas_to_mem(self, filename):
        '''
            将画布上的标注结果，存入内存中维护的变量desp_json，以备后续持久化
        '''

        def format_shape(s):
            return dict(label=s.label,
                        line_color=s.line_color.getRgb(),
                        fill_color=s.fill_color.getRgb(),
                        points=[(p.x(), p.y()) for p in s.points],
                        # add chris
                        difficult=s.difficult)

        shapes = [format_shape(shape) for shape in self.canvas.shapes]

        print(self.label_hist)

        if not self.desp_json:
            self.desp_json = init_json_mem(self.label_hist)
            print("Init description json file.")

        abs_filename = filename
        rel_filename = os.path.relpath(filename, self.desp_path)
        sample_content = append_json_mem(filename=rel_filename, abs_filename=abs_filename, shapes=shapes,
                                         classes=self.label_hist)
        self.desp_json["samples"][rel_filename] = sample_content

    def cur_img_idx_move_to_next(self):
        if self.cur_img_idx < 0:
            self.cur_img_idx = 0
        if self.cur_img_idx + 1 < len(self.m_img_list):
            self.cur_img_idx += 1
        # self.file_list_widget.setCurrentRow(self.cur_img_idx)

    def dump_json(self):
        '''
        同时将内存中的desp_json,sample_json写入磁盘
        Returns:

        '''
        if not self.desp_json:
            self.desp_json = init_json_mem(self.label_hist)
            logger.debug("Init description json memory.")
        self.desp_json = update_classes_mem(self.desp_json, self.label_hist)
        if self.label_file is None:
            self.label_file = LabelFile()
            self.label_file.verified = self.canvas.verified
        self.label_file.save_desp_format(self.desp_json, self.desp_path)
        self.label_file.save_sample_number(self.desp_json, self.desp_path)
        # print(self.desp_json)

    def save_json(self):
        if self.isOutputJson:
            if not self.desp_path:
                self.show_message("Error", "请先在文件菜单中设置json文件存放目录")
                return
            else:
                attention_get = QMessageBox.question(self, 'Attention',
                                                     '是否扫描整个文件夹并保存JSON文件，是：扫描整个文件夹，否只保存当前结果。',
                                                     QMessageBox.Cancel | QMessageBox.No | QMessageBox.Yes)  # 创建一个二次确认框
                if attention_get == QMessageBox.Cancel:
                    return
                elif attention_get == QMessageBox.Yes:
                    if not self.file_path:
                        self.show_message("Error", "请打开图片存放目录")
                        return
                    else:
                        self.file_path = self.m_img_list[self.cur_img_idx]
                        self.cur_img_idx = 0
                        lf = LabelFile()

                    def format_shape(s):
                        return dict(label=s.label,
                                    line_color=s.line_color.getRgb(),
                                    fill_color=s.fill_color.getRgb(),
                                    points=[(p.x(), p.y()) for p in s.points],
                                    # add chris
                                    difficult=s.difficult)

                    for idx in range(len(self.m_img_list)):

                        self.setWindowTitle(str(idx) + 'of' + str(len(self.m_img_list)))

                        self.cur_img_idx = idx
                        self.file_list_widget.setCurrentRow(self.cur_img_idx)
                        # print(self.cur_img_idx)
                        filename = self.m_img_list[self.cur_img_idx]
                        if filename:
                            self.load_file(filename)
                        #            self.show_bounding_box_from_annotation_file(filename)
                        shapes = [format_shape(shape) for shape in self.canvas.shapes]

                        # if idx == 0:
                        if not self.desp_json:
                            self.desp_json = init_json_mem(self.label_hist)
                            logger.debug("Init description json in memory.")

                        self.desp_json = update_classes_mem(self.desp_json, self.label_hist)

                        abs_filename = filename
                        rel_filename = os.path.relpath(filename, self.desp_path)
                        sample_content = append_json_mem(filename=rel_filename, abs_filename=abs_filename,
                                                         shapes=shapes,
                                                         classes=self.label_hist)
                        self.desp_json["samples"][rel_filename] = sample_content

                    if self.label_file is None:
                        self.label_file = LabelFile()
                        self.label_file.verified = self.canvas.verified
                    self.label_file.save_desp_format(self.desp_json, self.desp_path)
                    self.label_file.save_sample_number(self.desp_json, self.desp_path)

                # 只保存当前进度
                elif attention_get == QMessageBox.No:
                    self.dump_json()
                else:
                    return
                QMessageBox.information(self, u'Information', '保存成功')

    def set_format(self, save_format):
        if save_format == FORMAT_PASCALVOC:
            self.actions.save_format.setText(FORMAT_PASCALVOC)
            self.actions.save_format.setIcon(new_icon("format_voc"))
            self.label_file_format = LabelFileFormat.PASCAL_VOC
            LabelFile.suffix = XML_EXT

        elif save_format == FORMAT_YOLO:
            self.actions.save_format.setText(FORMAT_YOLO)
            self.actions.save_format.setIcon(new_icon("format_yolo"))
            self.label_file_format = LabelFileFormat.YOLO
            LabelFile.suffix = TXT_EXT

    def set_format_beginner(self, save_format_beginner):
        if save_format_beginner == FORMAT_PASCALVOC:
            self.actions.save_format_beginner.setText(FORMAT_PASCALVOC)
            self.actions.save_format_beginner.setIcon(new_icon("format_voc"))
            self.label_file_format = LabelFileFormat.PASCAL_VOC
            LabelFile.suffix = XML_EXT

        elif save_format_beginner == FORMAT_YOLO:
            self.actions.save_format_beginner.setText(FORMAT_YOLO)
            self.actions.save_format_beginner.setIcon(new_icon("format_yolo"))
            self.label_file_format = LabelFileFormat.YOLO
            LabelFile.suffix = TXT_EXT

    def change_format(self):
        """在 PASCAL_VOC 和 YOLO 格式之间切换。"""
        print(f"当前格式: {self.label_file_format}")  # 调试输出

        if self.label_file_format == LabelFileFormat.PASCAL_VOC:
            new_format = 'Pascal_VOC'
        elif self.label_file_format == LabelFileFormat.YOLO:
            new_format = 'Pascal_VOC'
        else:
            raise ValueError('Unknown label file format.')

        # 更新格式并刷新显示
        self.set_format(new_format)
        self.set_dirty()

    def change_format_beginner(self):
        pass

    def no_shapes(self):
        return not self.items_to_shapes

    def toggle_advanced_mode(self, value=True):
        self._beginner = not value
        self.canvas.set_editing(True)
        self.populate_mode_actions()
        if value:
            self.actions.createMode.setEnabled(True)
            self.actions.editMode.setEnabled(False)
            self.dock.setFeatures(self.dock.features() | self.dock_features)
        else:
            self.dock.setFeatures(self.dock.features() ^ self.dock_features)

    def populate_mode_actions(self):
        if self.beginner():
            tool, menu = self.actions.beginner, self.actions.beginnerContext
        else:
            tool, menu = self.actions.advanced, self.actions.advancedContext
        self.tools.clear()
        add_actions(self.tools, tool)
        self.canvas.menus[0].clear()
        add_actions(self.canvas.menus[0], menu)
        self.menus.edit.clear()
        actions = (self.actions.create,) if self.beginner() \
            else (self.actions.createMode, self.actions.editMode)
        add_actions(self.menus.edit, actions + self.actions.editMenu)

    def set_beginner(self):
        self.tools.clear()
        add_actions(self.tools, self.actions.beginner)

    def set_advanced(self):
        self.tools.clear()
        add_actions(self.tools, self.actions.advanced)

    def set_dirty(self):
        self.dirty = True
        self.actions.save.setEnabled(True)

    def set_clean(self):
        self.dirty = False
        self.actions.save.setEnabled(False)
        self.actions.create.setEnabled(True)

    def toggle_actions(self, value=True):
        """Enable/Disable widgets which depend on an opened image."""
        for z in self.actions.zoomActions:
            z.setEnabled(value)
        for action in self.actions.onLoadActive:
            action.setEnabled(value)

    def queue_event(self, function):
        QTimer.singleShot(0, function)

    def status(self, message, delay=5000):
        self.statusBar().showMessage(message, delay)

    def reset_state(self):
        self.items_to_shapes.clear()
        self.shapes_to_items.clear()
        self.label_list.clear()
        self.file_path = None
        self.image_data = None
        self.label_file = None
        self.canvas.reset_state()
        self.label_coordinates.clear()
        self.combo_box.cb.clear()

    def current_item(self):
        items = self.label_list.selectedItems()
        if items:
            return items[0]
        return None

    def add_recent_file(self, file_path):
        if file_path in self.recent_files:
            self.recent_files.remove(file_path)
        elif len(self.recent_files) >= self.max_recent:
            self.recent_files.pop()
        self.recent_files.insert(0, file_path)

    def beginner(self):
        return self._beginner

    def advanced(self):
        return not self.beginner()

    def show_tutorial_dialog(self, browser='default', link=None):
        if link is None:
            link = self.screencast

        if browser.lower() == 'default':
            wb.open(link, new=2)
        elif browser.lower() == 'chrome' and self.os_name == 'Windows':
            if shutil.which(browser.lower()):  # 'chrome' not in wb._browsers in windows
                wb.register('chrome', None, wb.BackgroundBrowser('chrome'))
            else:
                chrome_path = "D:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe"
                if os.path.isfile(chrome_path):
                    wb.register('chrome', None, wb.BackgroundBrowser(chrome_path))
            try:
                wb.get('chrome').open(link, new=2)
            except:
                wb.open(link, new=2)
        elif browser.lower() in wb._browsers:
            wb.get(browser.lower()).open(link, new=2)

    def show_default_tutorial_dialog(self):
        self.show_tutorial_dialog(browser='default')

    def show_info_dialog(self):
        from libs.__init__ import __version__
        # msg = u'Name:{0} \nApp Version:{1} \n{2} '.format(__appname__, __version__, sys.version_info)
        msg = u'Name:{0} \nApp Version:{1} '.format(__appname__, __version__)

        QMessageBox.information(self, u'Information', msg)

    # def show_shortcuts_dialog(self):
    #     self.show_tutorial_dialog(browser='default')
    def show_shortcuts_dialog(self):
        # 调用 show_tutorial_dialog，传入快捷键信息
        self.show_tutorial_dialog(browser='shortcuts')

    def show_tutorial_dialog(self, browser='default'):
        if browser == 'default':
            # 默认显示一些普通的教程内容
            tutorial_content = "Welcome to the tutorial. Here are some basics..."
        elif browser == 'shortcuts':
            # 显示快捷键信息
            tutorial_content = """
            常用快捷键：

            Ctrl + 空格 : 自动标注
            空格      : 停止标注
            W         : 绘制标注框
            A         : 上一张
            D         : 下一张
            双击右侧标签栏的 label : 修改标签
            Ctrl + 鼠标滑轮 : 放大缩小
            """
        else:
            # 如果是其他浏览器类型，则加载相应的内容
            tutorial_content = "Content not found for this browser type."

        # 显示相应的内容
        self.show_dialog_with_content(tutorial_content)

    def show_dialog_with_content(self, content):
        # 这里的代码负责显示一个对话框，展示传入的内容
        dialog = QDialog(self)
        dialog.setWindowTitle("快捷键帮助")

        # 创建标签并设置内容
        label = QLabel(content, dialog)
        label.setWordWrap(True)  # 使文本自动换行

        # 创建布局并添加标签
        layout = QVBoxLayout(dialog)
        layout.addWidget(label)
        dialog.setLayout(layout)

        # 显示对话框
        dialog.exec_()

    def create_shape(self):
        assert self.beginner()
        self.canvas.set_editing(False)
        self.actions.create.setEnabled(False)

    def toggle_drawing_sensitive(self, drawing=True):
        """In the middle of drawing, toggling between modes should be disabled."""
        self.actions.editMode.setEnabled(not drawing)
        if not drawing and self.beginner():
            # Cancel creation.
            print('Cancel creation.')
            self.canvas.set_editing(True)
            self.canvas.restore_cursor()
            self.actions.create.setEnabled(True)

    def toggle_draw_mode(self, edit=True):
        self.canvas.set_editing(edit)
        self.actions.createMode.setEnabled(edit)
        self.actions.editMode.setEnabled(not edit)

    def set_create_mode(self):
        assert self.advanced()
        self.toggle_draw_mode(False)

    def set_edit_mode(self):
        assert self.advanced()
        self.toggle_draw_mode(True)
        self.label_selection_changed()

    def update_file_menu(self):
        curr_file_path = self.file_path

        def exists(filename):
            return os.path.exists(filename)

        menu = self.menus.recentFiles
        menu.clear()
        files = [f for f in self.recent_files if f !=
                 curr_file_path and exists(f)]
        for i, f in enumerate(files):
            icon = new_icon('labels')
            action = QAction(
                icon, '&%d %s' % (i + 1, QFileInfo(f).fileName()), self)
            action.triggered.connect(partial(self.load_recent, f))
            menu.addAction(action)

    def pop_label_list_menu(self, point):
        self.menus.labelList.exec_(self.label_list.mapToGlobal(point))

    def center_label_on_canvas(self, item):
        """当用户点击标签列表时，将对应的标注框居中显示"""
        if not hasattr(self, 'canvas') or not self.canvas.shapes:
            return

        # 获取选中的 shape
        shape = self.items_to_shapes.get(item)
        if not shape:
            return

        # 获取 shape 的边界矩形
        bounding_rect = shape.bounding_rect()
        if bounding_rect.isEmpty():
            return

        # ✅ 改为从 scroll_area 获取 viewport
        viewport = self.scroll_area.viewport()
        viewport_width = viewport.width()
        viewport_height = viewport.height()

        # 计算 shape 中心点（相对于画布）
        center_x = bounding_rect.center().x()
        center_y = bounding_rect.center().y()

        # 获取当前缩放比例
        scale = self.canvas.scale

        # 转换为带缩放的坐标
        center_x *= scale
        center_y *= scale
        viewport_center_x = viewport_width / 2
        viewport_center_y = viewport_height / 2

        # 获取滚动条对象
        h_bar = self.scroll_bars[Qt.Horizontal]
        v_bar = self.scroll_bars[Qt.Vertical]

        new_h_value = center_x - viewport_center_x
        new_v_value = center_y - viewport_center_y

        # 设置滚动条位置
        h_bar.setValue(int(new_h_value))
        v_bar.setValue(int(new_v_value))

        # 刷新画布
        self.canvas.update()

    def edit_label(self):
        if not self.canvas.editing():
            return
        item = self.current_item()
        if not item:
            return
        text = self.label_dialog.pop_up(item.text())
        if text is not None:
            item.setText(text)
            item.setBackground(generate_color_by_text(text))
            self.set_dirty()
            self.update_combo_box()

    def file_item_double_clicked(self, item=None):
        if item is None:
            return

        item_text = ustr(item.text())
        try:
            self.cur_img_idx = self.m_img_list.index(item_text)
            filename = self.m_img_list[self.cur_img_idx]
            if filename:
                self.load_file(filename)
        except ValueError as e:
            print(f"Error: {e}")
            print(f"Item text: {item_text}")
            print(f"m_img_list: {self.m_img_list}")

    # Add chris
    def button_state(self, item=None):
        """ Function to handle difficult examples
        Update on each object """
        if not self.canvas.editing():
            return

        item = self.current_item()
        if not item:  # If not selected Item, take the first one
            item = self.label_list.item(self.label_list.count() - 1)

        difficult = self.diffc_button.isChecked()

        try:
            shape = self.items_to_shapes[item]
        except:
            pass
        # Checked and Update
        try:
            if difficult != shape.difficult:
                shape.difficult = difficult
                self.set_dirty()
            else:  # User probably changed item visibility
                self.canvas.set_shape_visible(shape, item.checkState() == Qt.Checked)
        except:
            pass

    # React to canvas signals.
    def shape_selection_changed(self, selected=False):
        if self._no_selection_slot:
            self._no_selection_slot = False
        else:
            shape = self.canvas.selected_shape
            if shape:
                self.shapes_to_items[shape].setSelected(True)
            else:
                self.label_list.clearSelection()
        self.actions.delete.setEnabled(selected)
        self.actions.copy.setEnabled(selected)
        self.actions.edit.setEnabled(selected)
        self.actions.shapeLineColor.setEnabled(selected)
        self.actions.shapeFillColor.setEnabled(selected)

    def add_label(self, shape):
        shape.paint_label = self.display_label_option.isChecked()
        item = HashableQListWidgetItem(shape.label)
        item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
        item.setCheckState(Qt.Checked)
        item.setBackground(generate_color_by_text(shape.label))
        self.items_to_shapes[item] = shape
        self.shapes_to_items[shape] = item
        self.label_list.addItem(item)
        for action in self.actions.onShapesPresent:
            action.setEnabled(True)
        self.update_combo_box()

    def remove_label(self, shape):
        if shape is None:
            # print('rm empty label')
            return
        item = self.shapes_to_items[shape]
        self.label_list.takeItem(self.label_list.row(item))
        del self.shapes_to_items[shape]
        del self.items_to_shapes[item]
        self.update_combo_box()

    def load_labels(self, shapes):
        """
        从canvas.shapes中加载label
        Args:
            shapes:

        Returns:

        """
        s = []
        for label, points, line_color, fill_color, difficult in shapes:
            shape = Shape(label=label)
            for x, y in points:

                # Ensure the labels are within the bounds of the image. If not, fix them.
                x, y, snapped = self.canvas.snap_point_to_canvas(x, y)
                if snapped:
                    self.set_dirty()

                shape.add_point(QPointF(x, y))
            shape.difficult = difficult
            shape.close()
            s.append(shape)

            if line_color:
                shape.line_color = QColor(*line_color)
            else:
                shape.line_color = generate_color_by_text(label)

            if fill_color:
                shape.fill_color = QColor(*fill_color)
            else:
                shape.fill_color = generate_color_by_text(label)

            self.add_label(shape)
        self.update_combo_box()
        self.canvas.load_shapes(s)

    def update_combo_box(self):
        # Get the unique labels and add them to the Combobox.
        items_text_list = [str(self.label_list.item(i).text()) for i in range(self.label_list.count())]

        unique_text_list = list(set(items_text_list))
        # Add a null row for showing all the labels
        unique_text_list.append("")
        unique_text_list.sort()

        self.combo_box.update_items(unique_text_list)

    def thread_my_save_labels(self):
        while True:
            if self.queue.empty():
                time.sleep(0.1)
            else:
                results, idx = self.queue.get()
                print(results, idx)
                if not results:
                    return
                if idx < len(self.m_img_list):
                    self.file_path = self.m_img_list[idx]
                else:
                    return
                if self.default_save_dir is not None and len(ustr(self.default_save_dir)):
                    if self.file_path:
                        image_file_name = os.path.basename(self.file_path)
                        saved_file_name = os.path.splitext(image_file_name)[0]
                        saved_path = os.path.join(ustr(self.default_save_dir), saved_file_name)
                        self._save_file(saved_path)
                else:
                    image_file_dir = os.path.dirname(self.file_path)
                    image_file_name = os.path.basename(self.file_path)
                    saved_file_name = os.path.splitext(image_file_name)[0]
                    saved_path = os.path.join(image_file_dir, saved_file_name)
                    self._save_file(saved_path if self.label_file
                                    else self.save_file_dialog(remove_ext=False))

                annotation_file_path = ustr(saved_path)
                if self.label_file is None:
                    self.label_file = LabelFile()
                    self.label_file.verified = self.canvas.verified

                def my_result_to_shape(result):
                    label = result["label"]
                    points = result["points"]

                    return dict(label=label,
                                points=points,
                                difficult=0)

                shapes = [my_result_to_shape(result) for result in results]
                # Can add different annotation formats here
                try:
                    if self.label_file_format == LabelFileFormat.PASCAL_VOC:
                        if annotation_file_path[-4:].lower() != ".xml":
                            annotation_file_path += XML_EXT
                        self.label_file.save_pascal_voc_format(annotation_file_path, shapes, self.file_path,
                                                               self.image_data,
                                                               self.line_color.getRgb(), self.fill_color.getRgb())
                    elif self.label_file_format == LabelFileFormat.YOLO:
                        if annotation_file_path[-4:].lower() != ".txt":
                            annotation_file_path += TXT_EXT
                        self.label_file.save_yolo_format(annotation_file_path, shapes, self.file_path, self.image_data,
                                                         self.label_hist,
                                                         self.line_color.getRgb(), self.fill_color.getRgb())
                    else:
                        self.label_file.save(annotation_file_path, shapes, self.file_path, self.image_data,
                                             self.line_color.getRgb(), self.fill_color.getRgb())

                    # 输出至description.json
                    if self.isOutputJson:
                        if not self.desp_json:
                            self.desp_json = init_json_mem(self.label_hist)
                            print("Init description json file.")

                        abs_filename = self.file_path
                        rel_filename = os.path.relpath(abs_filename, os.path.dirname(self.desp_path))

                        # if there is valid results, append to the descriptions.json
                        if results:
                            sample_content = append_json_mem(filename=rel_filename, abs_filename=abs_filename,
                                                             shapes=shapes,
                                                             classes=self.label_hist)
                            self.desp_json["samples"][rel_filename] = sample_content

                        if self.cur_img_idx % 100 == 0:
                            self.label_file.save_desp_format(self.desp_json, self.desp_path)
                            self.label_file.save_sample_number(self.desp_json, self.desp_path)
                        self.set_clean()

                    self.load_file_with_annotation(self.file_path)
                # return True
                except LabelFileError as e:
                    self.error_message(u'Error saving label data', u'<b>%s</b>' % e)
                # return False

    def my_save_labels(self, results, idx):
        # (results, idx) = results_with_idx
        if not results:
            return
        if idx < len(self.m_img_list):
            self.file_path = self.m_img_list[idx]
        else:
            return
        if self.default_save_dir is not None and len(ustr(self.default_save_dir)):
            if self.file_path:
                image_file_name = os.path.basename(self.file_path)
                saved_file_name = os.path.splitext(image_file_name)[0]
                saved_path = os.path.join(ustr(self.default_save_dir), saved_file_name)
                self._save_file(saved_path)
        else:
            image_file_dir = os.path.dirname(self.file_path)
            image_file_name = os.path.basename(self.file_path)
            saved_file_name = os.path.splitext(image_file_name)[0]
            saved_path = os.path.join(image_file_dir, saved_file_name)
            self._save_file(saved_path if self.label_file
                            else self.save_file_dialog(remove_ext=False))

        annotation_file_path = ustr(saved_path)
        if self.label_file is None:
            self.label_file = LabelFile()
            self.label_file.verified = self.canvas.verified

        def my_result_to_shape(result):
            label = result["label"]
            points = result["points"]

            return dict(label=label,
                        points=points,
                        difficult=0)

        shapes = [my_result_to_shape(result) for result in results]
        # Can add different annotation formats here
        try:
            if self.label_file_format == LabelFileFormat.PASCAL_VOC:
                if annotation_file_path[-4:].lower() != ".xml":
                    annotation_file_path += XML_EXT
                self.label_file.save_pascal_voc_format(annotation_file_path, shapes, self.file_path, self.image_data,
                                                       self.line_color.getRgb(), self.fill_color.getRgb())
            elif self.label_file_format == LabelFileFormat.YOLO:
                if annotation_file_path[-4:].lower() != ".txt":
                    annotation_file_path += TXT_EXT
                self.label_file.save_yolo_format(annotation_file_path, shapes, self.file_path, self.image_data,
                                                 self.label_hist,
                                                 self.line_color.getRgb(), self.fill_color.getRgb())
            else:
                self.label_file.save(annotation_file_path, shapes, self.file_path, self.image_data,
                                     self.line_color.getRgb(), self.fill_color.getRgb())

            # 输出至description.json
            if self.isOutputJson:
                if not self.desp_json:
                    self.desp_json = init_json_mem(self.label_hist)
                    print("Init description json file.")

                abs_filename = self.file_path
                rel_filename = os.path.relpath(abs_filename, os.path.dirname(self.desp_path))

                # if there is valid results, append to the descriptions.json
                if results:
                    sample_content = append_json_mem(filename=rel_filename, abs_filename=abs_filename, shapes=shapes,
                                                     classes=self.label_hist)
                    self.desp_json["samples"][rel_filename] = sample_content

                if self.cur_img_idx % 100 == 0:
                    self.label_file.save_desp_format(self.desp_json, self.desp_path)
                    self.label_file.save_sample_number(self.desp_json, self.desp_path)
                    asyncio.gather()
                self.set_clean()

            self.load_file_with_annotation(self.file_path)
            return True
        except LabelFileError as e:
            self.error_message(u'Error saving label data', u'<b>%s</b>' % e)
            return False

    def save_labels(self, annotation_file_path):
        annotation_file_path = ustr(annotation_file_path)
        if self.label_file is None:
            self.label_file = LabelFile()
            self.label_file.verified = self.canvas.verified

        def format_shape(s):
            return dict(label=s.label,
                        line_color=s.line_color.getRgb(),
                        fill_color=s.fill_color.getRgb(),
                        points=[(p.x(), p.y()) for p in s.points],
                        # add chris
                        difficult=s.difficult)

        shapes = [format_shape(shape) for shape in self.canvas.shapes]
        # Can add different annotation formats here
        try:
            if self.label_file_format == LabelFileFormat.PASCAL_VOC:
                if annotation_file_path[-4:].lower() != ".xml":
                    annotation_file_path += XML_EXT
                self.label_file.save_pascal_voc_format(annotation_file_path, shapes, self.file_path, self.image_data,
                                                       self.line_color.getRgb(), self.fill_color.getRgb())
            elif self.label_file_format == LabelFileFormat.YOLO:
                if annotation_file_path[-4:].lower() != ".txt":
                    annotation_file_path += TXT_EXT
                self.label_file.save_yolo_format(annotation_file_path, shapes, self.file_path, self.image_data,
                                                 self.label_hist,
                                                 self.line_color.getRgb(), self.fill_color.getRgb())

            else:
                self.label_file.save(annotation_file_path, shapes, self.file_path, self.image_data,
                                     self.line_color.getRgb(), self.fill_color.getRgb())
            print('Image:{0} -> Annotation:{1}'.format(self.file_path, annotation_file_path))
            return True
        except LabelFileError as e:
            self.error_message(u'Error saving label data', u'<b>%s</b>' % e)
            return False

    def copy_selected_shape(self):
        self.add_label(self.canvas.copy_selected_shape())
        # fix copy and delete
        self.shape_selection_changed(True)

    def combo_selection_changed(self, index):
        text = self.combo_box.cb.itemText(index)
        for i in range(self.label_list.count()):
            if text == "":
                self.label_list.item(i).setCheckState(2)
            elif text != self.label_list.item(i).text():
                self.label_list.item(i).setCheckState(0)
            else:
                self.label_list.item(i).setCheckState(2)

    def label_selection_changed(self):
        item = self.current_item()
        if item and self.canvas.editing():
            self._no_selection_slot = True
            self.canvas.select_shape(self.items_to_shapes[item])
            shape = self.items_to_shapes[item]
            # Add Chris
            # self.diffc_button.setChecked(shape.difficult)

    def label_item_changed(self, item):
        shape = self.items_to_shapes[item]
        label = item.text()
        if label != shape.label:
            shape.label = item.text()
            shape.line_color = generate_color_by_text(shape.label)
            self.set_dirty()
        else:  # User probably changed item visibility
            self.canvas.set_shape_visible(shape, item.checkState() == Qt.Checked)

    def new_shape(self):
        """Pop-up and give focus to the label editor.

        position MUST be in global coordinates.
        """
        if self.use_default_label_checkbox.isChecked():
            # 使用二级菜单中的选项作为标签
            text = self.subcategory_combo.currentText()
        else:
            # 如果没有选中复选框，则按照原逻辑弹出对话框获取标签
            if len(self.label_hist) > 0:
                self.label_dialog = LabelDialog(
                    parent=self, list_item=self.label_hist
                )

            # 使用单类模式的最后一个标签
            if self.single_class_mode.isChecked() and self.lastLabel:
                text = self.lastLabel
            else:
                text = self.label_dialog.pop_up(text=self.prev_label_text)
                self.lastLabel = text

        # Add Chris
        # self.diffc_button.setChecked(False)
        if text is not None:
            self.prev_label_text = text
            generate_color = generate_color_by_text(text)
            shape = self.canvas.set_last_label(text, generate_color, generate_color)
            self.add_label(shape)

            if self.beginner():  # 切换到编辑模式
                self.canvas.set_editing(True)
                self.actions.create.setEnabled(True)
            else:
                self.actions.editMode.setEnabled(True)

            self.set_dirty()

            # 将新标签加入历史记录
            if text not in self.label_hist:
                self.label_hist.append(text)
        else:
            # 如果没有标签，重置画布
            self.canvas.reset_all_lines()

    def scroll_request(self, delta, orientation):
        units = -delta / (8 * 15)
        bar = self.scroll_bars[orientation]
        # print(f'bar before {bar.value()}')

        # 更新滚动条位置
        new_value = bar.value() + bar.singleStep() * units
        bar.setValue(int(min(max(new_value, 0), bar.maximum())))  # 确保在合法范围内
        # print(f'bar after {bar.value()} delta {delta}, orientation {orientation}')
        # self.applyAdjustments()
        # self.applyViewportAdjustments()

        # 进行图像调整
        self.cache_zoom()
        # self.applyAdjustments()

    def set_zoom(self, value):
        self.actions.fitWidth.setChecked(False)
        self.actions.fitWindow.setChecked(False)
        self.zoom_mode = self.MANUAL_ZOOM

        # 获取视口中心点
        viewport = self.scroll_area.viewport()
        center_point = QPoint(viewport.width() // 2, viewport.height() // 2)
        # 转换为内容坐标
        content_widget = self.scroll_area.widget()
        content_center_before = content_widget.mapToParent(center_point)

        # 设置新的缩放值
        self.zoom_widget.setValue(value)

        # 获取内容中心点在缩放前的位置比例
        if content_widget.width() == 0 or content_widget.height() == 0:
            return  # 避免除以零

        # 计算缩放后的内容尺寸
        new_content_width = content_widget.width()
        new_content_height = content_widget.height()

        # 计算缩放后的内容中心点位置
        content_center_after = content_widget.mapFromParent(center_point)

        # 计算滚动条新的值以保持中心点不变
        h_bar = self.scroll_bars[Qt.Horizontal]
        v_bar = self.scroll_bars[Qt.Vertical]
        new_h_value = h_bar.value() + (content_center_after.x() - content_center_before.x())
        new_v_value = v_bar.value() + (content_center_after.y() - content_center_before.y())

        # 确保滚动条值在合法范围内
        h_bar.setValue(int(min(max(new_h_value, 0), h_bar.maximum())))
        v_bar.setValue(int(min(max(new_v_value, 0), v_bar.maximum())))

        # 如果内容尺寸小于视口尺寸，居中内容
        viewport_width = viewport.width()
        viewport_height = viewport.height()

        if new_content_width < viewport_width:
            h_bar.setValue((h_bar.maximum() - h_bar.minimum()) // 2)
        if new_content_height < viewport_height:
            v_bar.setValue((v_bar.maximum() - v_bar.minimum()) // 2)

    def add_zoom(self, increment=10):
        self.set_zoom(self.zoom_widget.value() + increment)

    def set_zoom_by_cache(self):
        self.set_zoom(self.cache_z)
        self.scroll_bars[Qt.Horizontal].setValue(self.cache_h)
        self.scroll_bars[Qt.Vertical].setValue(self.cache_v)

    def cache_zoom(self):
        self.cache_z = self.zoom_widget.value()
        self.cache_h = self.scroll_bars[Qt.Horizontal].value()
        self.cache_v = self.scroll_bars[Qt.Vertical].value()

    def zoom_request(self, delta):
        # 获取当前水平和垂直滚动条
        h_bar = self.scroll_bars[Qt.Horizontal]
        v_bar = self.scroll_bars[Qt.Vertical]

        # 缓存缩放前的滚动条值
        h_bar_value_before = h_bar.value()
        v_bar_value_before = v_bar.value()
        # print(f"滚动条值前: 水平 = {h_bar_value_before}, 垂直 = {v_bar_value_before}")

        # 获取鼠标的全局位置，并将其转换为控件内部坐标
        global_pos = QCursor.pos()
        relative_pos = self.mapFromGlobal(global_pos)

        cursor_x = relative_pos.x()
        cursor_y = relative_pos.y()
        # print(f"鼠标位置: (全局) ({global_pos.x()}, {global_pos.y()}) -> (控件内部) ({cursor_x}, {cursor_y})")

        # 获取当前内容的尺寸和可视区域的大小
        content_width = self.scroll_area.widget().width()
        content_height = self.scroll_area.widget().height()
        viewport_width = self.scroll_area.viewport().width()
        viewport_height = self.scroll_area.viewport().height()
        # print(f"内容尺寸: 宽度 = {content_width}, 高度 = {content_height}")
        # print(f"可视区域: 宽度 = {viewport_width}, 高度 = {viewport_height}")

        # 计算鼠标位置在内容中的相对比例 (基于内容尺寸)
        if content_width == 0 or content_height == 0:
            return  # 避免除以零

        content_x_ratio = (h_bar_value_before + cursor_x) / content_width
        content_y_ratio = (v_bar_value_before + cursor_y) / content_height
        # print(f"鼠标位置比例: 水平 = {content_x_ratio:.4f}, 垂直 = {content_y_ratio:.4f}")

        # 执行缩放
        units = delta / (8 * 30)  # 计算缩放步长
        scale = 8  # 每步缩放的基准
        self.add_zoom(scale * units)
        # print(f"缩放: 步长 = {units}, 缩放因子 = {scale * units}")

        # 获取缩放后的内容尺寸和滚动条的最大值
        new_content_width = self.scroll_area.widget().width()
        new_content_height = self.scroll_area.widget().height()
        # print(f"缩放后的内容尺寸: 宽度 = {new_content_width}, 高度 = {new_content_height}")

        # 根据鼠标位置比例计算新的滚动条位置
        new_h_value = content_x_ratio * new_content_width - cursor_x
        new_v_value = content_y_ratio * new_content_height - cursor_y
        # print(f"新的滚动条值: 水平 = {new_h_value:.2f}, 垂直 = {new_v_value:.2f}")

        # 确保滚动条值在合法范围内
        h_bar.setValue(int(min(max(new_h_value, 0), h_bar.maximum())))
        v_bar.setValue(int(min(max(new_v_value, 0), v_bar.maximum())))
        # print(f"设置滚动条值: 水平 = {h_bar.value()}, 垂直 = {v_bar.value()}")

        # 缓存当前的缩放状态
        self.cache_zoom()
        # self.applyAdjustments()
        # self.applyViewportAdjustments()
        # print("缩放状态已缓存")

    def set_fit_window(self, value=True):
        # print(f"set_fit_window: {value}")
        if value:
            self.actions.fitWidth.setChecked(True)
        self.zoom_mode = self.FIT_WINDOW if value else self.MANUAL_ZOOM
        self.adjust_scale()

    def set_fit_width(self, value=True):
        # print(f"set_fit_width: {value}")
        if value:
            self.actions.fitWindow.setChecked(False)
        self.zoom_mode = self.FIT_WIDTH if value else self.MANUAL_ZOOM
        self.adjust_scale()

    def toggle_polygons(self, value):
        # print(f"toggle_polygons: {value}")
        for item, shape in self.items_to_shapes.items():
            item.setCheckState(Qt.Checked if value else Qt.Unchecked)

    def load_file(self, file_path=None):
        """加载指定文件，如果未指定则加载最后打开的文件。"""
        self.reset_state()
        self.canvas.setEnabled(False)

        # 如果未指定路径，则从设置中获取上次打开的文件路径
        file_path = ustr(file_path or self.settings.get(SETTING_FILENAME))
        # print('file_path:', file_path)

        unicode_file_path = os.path.abspath(ustr(file_path))

        # 高亮文件列表中的项目
        if self.file_list_widget.count() > 0:
            if unicode_file_path in self.m_img_list:
                index = self.m_img_list.index(unicode_file_path)
                self.file_list_widget.item(index).setSelected(True)
            else:
                self.file_list_widget.clear()
                self.m_img_list.clear()

        if not os.path.exists(unicode_file_path):
            print(f"文件不存在: {unicode_file_path}")
            return False

        # print('unicode_file_path:', unicode_file_path)

        # 初始化画布
        self.canvas.shapes = []
        self.canvas.update()

        try:
            if LabelFile.is_label_file(unicode_file_path):
                self.label_file = LabelFile(unicode_file_path)
                self.image_data = self.label_file.image_data
                self.line_color = QColor(*self.label_file.lineColor)
                self.fill_color = QColor(*self.label_file.fillColor)
                self.canvas.verified = self.label_file.verified
            else:
                # 读取图像数据
                self.image_data = read(unicode_file_path, None)
                self.label_file = None
                self.canvas.verified = False

            # 将数据转换为 QImage
            image = self.image_data if isinstance(self.image_data, QImage) else QImage.fromData(self.image_data)

            if image.isNull():
                raise ValueError(f"无法打开文件: {unicode_file_path}")

            # 打开原始图片
            self.original_image = Image.open(unicode_file_path)

            self.img_array = np.array(self.original_image, dtype=np.float32)

            # 启动自适应色阶计算线程
            self.auto_worker = AutoAdjustmentWorker(self.img_array)
            self.auto_worker.adjustment_signal.connect(self.onAutoAdjustmentComplete)
            self.auto_worker.start()

            # 应用图像调整并更新画布
            # self.applyAdjustments()
            self.status(f"Loaded {os.path.basename(unicode_file_path)}")

            # 更新状态和画布
            self.image = image
            self.file_path = unicode_file_path

            self.canvas.load_pixmap(QPixmap.fromImage(image))

            if self.label_file:
                self.load_labels(self.label_file.shapes)
            else:
                self.canvas.shapes = []

            self.set_clean()
            self.canvas.setEnabled(True)
            self.set_zoom_by_cache()
            self.paint_canvas()
            self.add_recent_file(self.file_path)
            self.toggle_actions(True)

            # 显示注释框（如果存在）
            self.show_bounding_box_from_annotation_file(unicode_file_path)
        except (LabelFileError, ValueError) as e:
            self.error_message(
                'Error opening file',
                f"<p><b>{e}</b></p><p>Make sure <i>{unicode_file_path}</i> is a valid label or image file.</p>"
            )
            print(f"加载文件时出错: {e}")
            return False
        except Exception as e:

            logger.debug(f"意外错误: {e}")
            return False

        self.canvas.setFocus(True)
        return True

    def onAutoAdjustmentComplete(self, black_level, white_level):
        if self.enable_enhance_checkbox.isChecked():
            """接收自动色阶计算结果并应用调整"""
            print(f"自动色阶计算完成: 黑场={black_level}, 白场={white_level}")

            # 初始化滑块调整值
            self.current_adjustments = {
                'black_level': black_level,
                'white_level': white_level,
                'gamma': 100  # 默认伽马为 1.0
            }

            # 启动后台线程处理图像
            self.applyAdjustments()
        else:
            print("色阶自动调整已禁用")

    def get_visible_image(self):
        """
        获取视口中当前显示的图像区域。
        :return: 当前显示区域的 NumPy 数组图像
        """
        if not hasattr(self, 'original_image') or self.original_image is None:
            print("没有加载的原始图像")
            return None

        # 获取当前滚动条的位置
        h_bar = self.scroll_bars[Qt.Horizontal]
        v_bar = self.scroll_bars[Qt.Vertical]
        x1, y1 = h_bar.value(), v_bar.value()
        print(f"当前滚动条位置: 水平 = {x1}, 垂直 = {y1}")

        # 获取视口大小和缩放比例
        viewport_width = int(self.scroll_area.viewport().width() / self.canvas.scale)
        viewport_height = int(self.scroll_area.viewport().height() / self.canvas.scale)
        print(f"视口大小: 宽度 = {viewport_width}, 高度 = {viewport_height}")
        print(f"缩放比例: {self.canvas.scale}")

        # 计算裁剪区域的结束坐标 (确保不超出图像范围)
        x2, y2 = min(x1 + viewport_width, self.original_image.width), min(y1 + viewport_height,
                                                                          self.original_image.height)
        print(f"裁剪区域的结束坐标: x2 = {x2}, y2 = {y2}")

        # 确保坐标在图像的有效范围内
        x1, y1 = max(x1, 0), max(y1, 0)
        print(f"调整后的裁剪区域起始坐标: x1 = {x1}, y1 = {y1}")

        # 裁剪出视口中的图像区域并转换为 NumPy 数组
        cropped_image = self.original_image.crop((x1, y1, x2, y2))
        print(f"裁剪后的图像尺寸: {cropped_image.size}")

        # 将裁剪后的图像转换为 NumPy 数组并返回
        image_array = np.array(cropped_image, dtype=np.float32)
        print(f"返回的 NumPy 数组形状: {image_array.shape}")

        return image_array

    def applyAdjustments(self):
        """从滑块获取调整值，并在后台处理图像。"""
        if not hasattr(self, 'original_image') or self.original_image is None:
            print("没有原始图片可调整")
            return

        saved_shapes = self.canvas.shapes.copy()
        print(f"保存的图形对象数量: {len(saved_shapes)}")

        try:
            # self.img_array = self.get_visible_image()
            # 确保 img_array 已存在，避免重复转换
            if not hasattr(self, 'img_array') or self.img_array is None:
                print("转换原始图像为 NumPy 数组...")
                self.img_array = np.array(self.original_image, dtype=np.float32)

            # 获取滑块的当前值
            black_level = self.current_adjustments['black_level']
            white_level = self.current_adjustments['white_level']
            gamma = self.current_adjustments['gamma'] / 100.0
            print(f"当前调整值: 黑色级别 = {black_level}, 白色级别 = {white_level}, Gamma = {gamma}")

            # 如果已有线程正在运行，则安全地终止它
            if hasattr(self, 'worker') and self.worker.isRunning():
                print("终止现有图像处理线程...")
                self.worker.terminate()

            self.start_time = time.time()

            # 启动新的后台线程进行图像处理
            print("启动新的图像处理线程...")
            self.worker = ImageProcessingWorker(self.img_array, black_level, white_level, gamma)
            self.worker.result_signal.connect(lambda img: self.updateCanvas(img, saved_shapes))
            self.worker.start()
        except Exception as e:
            print(f"应用调整时出错: {e}")

    def updateCanvas(self, image, shapes=None):
        print("更新画布中...")
        height, width, channels = image.shape if len(image.shape) == 3 else (image.shape[0], image.shape[1], 1)
        fmt = QImage.Format_RGB888 if channels == 3 else QImage.Format_Grayscale8
        bytes_per_line = channels * width
        qimage = QImage(image.data, width, height, bytes_per_line, fmt)
        self.canvas.load_pixmap(QPixmap.fromImage(qimage))

        if shapes:
            self.canvas.load_shapes(shapes)
        # self.canvas.update()
        self.canvas.repaint()

        end_time = time.time()
        if self.start_time:
            print(f"滑块停止到界面更新总耗时: {end_time - self.start_time:.3f} 秒")
            self.start_time = None  # 重置起始时间

    def updateImage(self):
        if self.enable_enhance_checkbox.isChecked():

            """滑块变化时更新调整参数"""
            if self.img_array is None:
                print("未加载图像，无法更新")
                return

            try:
                # 更新滑块值并标记为手动调整
                self.current_adjustments = {
                    'black_level': self.black_level_slider.value(),
                    'white_level': self.white_level_slider.value(),
                    'gamma': self.gamma_slider.value()
                }
                # print(f"滑块值更新: 黑色级别 = {self.current_adjustments['black_level']}, "
                #       f"白色级别 = {self.current_adjustments['white_level']}, "
                #       f"Gamma = {self.current_adjustments['gamma']}")

                self.manual_adjustment = True  # 标记为手动调整

                # 使用防抖动定时器，避免频繁处理
                # print("启动更新定时器，等待50ms后执行调整...")
                self.update_timer.start(50)  # 100ms 后执行调整

            except Exception as e:
                print(f"获取滑块值时出错: {e}")
        else:
            print("图像增强已禁用，跳过处理")

    def _pre_switch_tasks(self):
        """执行切换图片前的任务，如果阻止切换则返回 False。"""
        if self.auto_saving.isChecked():
            if self.default_save_dir:
                if self.dirty:
                    self.save_file()
            else:
                self.change_save_dir_dialog()
                return False

        return self.may_continue()

    def open_prev_image(self, _value=False):
        """切换到上一张图片，并确保切换过程平滑。"""
        if not self._pre_switch_tasks():
            return

        if self.cur_img_idx > 0:
            self.cur_img_idx -= 1
            filename = self.m_img_list[self.cur_img_idx]
            self._smooth_switch_image(filename)

    def open_next_image(self, _value=False):
        """切换到下一张图片，并确保切换过程平滑。"""
        if not self._pre_switch_tasks():
            return

        filename = None
        if self.file_path is None and self.m_img_list:
            filename = self.m_img_list[0]
            self.cur_img_idx = 0
        elif self.cur_img_idx + 1 < len(self.m_img_list):
            self.cur_img_idx += 1
            filename = self.m_img_list[self.cur_img_idx]

        self._smooth_switch_image(filename)

    def _smooth_switch_image(self, filename):
        """平滑切换图片，并根据标注文件加载标注框。"""
        if not filename:
            return

        self.canvas.setUpdatesEnabled(False)

        try:
            self.load_file(filename)
            self.file_list_widget.setCurrentRow(self.cur_img_idx)
            # self.applyAdjustments()
            # self.loadImage(filename)
        except Exception as e:
            print(f"切换图片时出错: {e}")
        finally:
            self.canvas.setUpdatesEnabled(True)
            self.canvas.update()

    def load_categories_from_yaml(self, yaml_file):
        """从 YAML 文件加载数据，并填充到一级菜单中"""
        with open(yaml_file, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)

        self.categories = data.get('categories', {})
        self.default_label_text_line.addItems(self.categories.keys())

    def update_subcategories(self, index):
        """当一级菜单改变时，更新二级菜单选项"""
        self.subcategory_combo.clear()
        category = self.default_label_text_line.currentText()
        subcategories = self.categories.get(category, [])
        self.subcategory_combo.addItems(subcategories)

    def counter_str(self):
        """
        Converts image counter to string representation.
        """
        #        return '[{} / {}]'.format(self.cur_img_idx + 1, self.img_count)
        return '[{} / {}]'.format(self.cur_img_idx + 1, len(self.m_img_list))

    def show_bounding_box_from_annotation_file(self, file_path):
        # 确保传入的文件路径有效
        if not file_path:
            print("No file path provided.")
            return

        # if self.default_save_dir is not None:
        #     basename = os.path.basename(os.path.splitext(file_path)[0])
        #     xml_path = os.path.join(self.default_save_dir, basename + XML_EXT)
        #     txt_path = os.path.join(self.default_save_dir, basename + TXT_EXT)
        #     json_path = os.path.join(self.default_save_dir, basename + JSON_EXT)

        # 获取图像的目录和基础文件名（不带扩展名）
        path = os.path.dirname(file_path)
        basename = os.path.splitext(os.path.basename(file_path))[0]

        # 构造完全匹配的 XML 文件路径
        xml_primary = os.path.join(self.default_save_dir, f"{basename}.xml")
        xml_secondary = None

        # 查找可能的带置信度的 XML 文件
        for file in os.listdir(path):
            if file.startswith(basename) and file.endswith('.xml') and '#' in file:
                xml_secondary = os.path.join(self.default_save_dir, file)
                print(f"Found secondary XML: {xml_secondary}")
                break  # 找到第一个符合条件的文件后退出循环

        # 优先加载完全匹配的 XML 文件
        if os.path.isfile(xml_primary):
            print(f"Loading primary XML: {xml_primary}")
            self.load_pascal_xml_by_filename(xml_primary)
        elif xml_secondary:
            print(f"Loading secondary XML: {xml_secondary}")
            self.load_pascal_xml_by_filename(xml_secondary)

        else:
            # # 如果没有找到任何 XML 文件，继续检查是否有 YOLO 文件
            txt_path = os.path.join(self.default_save_dir, f"{basename}.txt")
            if os.path.isfile(txt_path):
                print(f"Loading YOLO TXT: {txt_path}")
                self.load_yolo_txt_by_filename(txt_path)
            # else:
            #     print("No suitable annotation file found.")

    def resizeEvent(self, event):
        if self.canvas and not self.image.isNull() \
                and self.zoom_mode != self.MANUAL_ZOOM:
            self.adjust_scale()
        super(MainWindow, self).resizeEvent(event)

    def paint_canvas(self):
        # assert not self.image.isNull(), "cannot paint null image"
        self.canvas.scale = 0.01 * self.zoom_widget.value()
        self.canvas.label_font_size = int(0.02 * max(self.image.width(), self.image.height()))
        self.canvas.adjustSize()
        self.canvas.update()

    def adjust_scale(self, initial=True):
        value = self.scalers[self.FIT_WINDOW if initial else self.zoom_mode]()
        self.zoom_widget.setValue(int(100 * value))

    def scale_fit_window(self):
        """Figure out the size of the pixmap in order to fit the main widget."""
        e = 2.0  # So that no scrollbars are generated.
        w1 = self.centralWidget().width() - e
        h1 = self.centralWidget().height() - e
        a1 = w1 / h1
        # Calculate a new scale value based on the pixmap's aspect ratio.
        w2 = self.canvas.pixmap.width() - 0.0
        h2 = self.canvas.pixmap.height() - 0.0
        a2 = w2 / h2
        return w1 / w2 if a2 >= a1 else h1 / h2

    def scale_fit_width(self):
        # The epsilon does not seem to work too well here.
        w = self.centralWidget().width() - 2.0
        return w / self.canvas.pixmap.width()

    def closeEvent(self, event):
        if not self.may_continue():
            event.ignore()
        settings = self.settings
        # If it loads images from dir, don't load it at the beginning
        if self.dir_name is None:
            settings[SETTING_FILENAME] = self.file_path if self.file_path else ''
        else:
            settings[SETTING_FILENAME] = ''

        settings[SETTING_WIN_SIZE] = self.size()
        settings[SETTING_WIN_POSE] = self.pos()
        settings[SETTING_WIN_STATE] = self.saveState()
        settings[SETTING_LINE_COLOR] = self.line_color
        settings[SETTING_FILL_COLOR] = self.fill_color
        settings[SETTING_RECENT_FILES] = self.recent_files
        settings[SETTING_ADVANCE_MODE] = not self._beginner
        if self.default_save_dir and os.path.exists(self.default_save_dir):
            settings[SETTING_SAVE_DIR] = ustr(self.default_save_dir)
        else:
            settings[SETTING_SAVE_DIR] = ''

        if self.last_open_dir and os.path.exists(self.last_open_dir):
            settings[SETTING_LAST_OPEN_DIR] = self.last_open_dir
        else:
            settings[SETTING_LAST_OPEN_DIR] = ''

        settings[SETTING_AUTO_SAVE] = self.auto_saving.isChecked()
        settings[SETTING_SINGLE_CLASS] = self.single_class_mode.isChecked()
        settings[SETTING_PAINT_LABEL] = self.display_label_option.isChecked()
        settings[SETTING_DRAW_SQUARE] = self.draw_squares_option.isChecked()
        settings[SETTING_LABEL_FILE_FORMAT] = self.label_file_format
        settings.save()

    def load_recent(self, filename):
        if self.may_continue():
            self.load_file(filename)

    def scan_all_images(self, folder_path):
        """
        扫描指定文件夹中的所有支持格式的图像文件，不遍历子文件夹。

        Args:
            folder_path (str): 要扫描的文件夹路径。

        Returns:
            list: 符合条件的图像文件的绝对路径列表。
        """
        extensions = ['.%s' % fmt.data().decode("ascii").lower() for fmt in QImageReader.supportedImageFormats()]
        images = []
        try:
            # 仅遍历指定文件夹，不递归子文件夹
            for file in os.listdir(folder_path):
                file_path = os.path.join(folder_path, file)
                if os.path.isfile(file_path) and file.lower().endswith(tuple(extensions)):
                    path = ustr(os.path.abspath(file_path))
                    images.append(path)
        except Exception as e:
            self.show_message("错误", f"扫描目录时发生错误: {e}")
            return []

        # 使用自然排序
        natural_sort(images, key=lambda x: x.lower())
        return images

    def change_save_dir_dialog(self, _value=False):
        """
        改变标注结果保存目录，同时重置标注状态json状态为空。
        Args:
            _value:

        Returns:
        """

        print("default:", self.default_save_dir)
        if self.default_save_dir is not None:
            path = ustr(self.default_save_dir)
        else:
            path = '.'

        dir_path = ustr(QFileDialog.getExistingDirectory(self,
                                                         '%s - Save annotations to the directory' % __appname__, path,
                                                         QFileDialog.ShowDirsOnly
                                                         | QFileDialog.DontResolveSymlinks))

        if dir_path is not None and len(dir_path) > 1:
            self.default_save_dir = dir_path
            print("默认：", dir_path)
            self.status(f'标注文件存放目录已修改为：{self.default_save_dir}')
            print("标签存放路径：", self.default_save_dir)
            yolo_classes_path = os.path.join(dir_path, 'classes.txt')
            if os.path.exists(yolo_classes_path):
                self.load_predefined_classes(yolo_classes_path)
            # 重置（清空）当前的标注状态，self.desp_json
            self.desp_json = {}
        else:
            self.show_message("错误", "没有选择label保存路径，请重新选择。")
            return

    def change_desp_json_dir_dialog(self, _value=False):
        if not self.isOutputJson:
            return

        if self.default_save_dir is not None:
            path = ustr(self.default_save_dir)
        else:
            path = '.'

        dir_path = ustr(QFileDialog.getExistingDirectory(self,
                                                         '%s - Save desp_json to the directory' % __appname__, path,
                                                         QFileDialog.ShowDirsOnly
                                                         | QFileDialog.DontResolveSymlinks))

        if dir_path is not None and len(dir_path) > 1:
            self.desp_path = os.path.join(dir_path, "descriptions.json")

            # Check if the JSON file exists
            if os.path.exists(self.desp_path):
                reply = QMessageBox.question(self, '提示',
                                             '检测到该目录包含 descriptions.json，是否加载？ 是：从已有标注结果中恢复。否：从头开始标注。',
                                             QMessageBox.Yes | QMessageBox.No, QMessageBox.No)

                if reply == QMessageBox.Yes:
                    # Load JSON content into self.desp_json
                    try:
                        with open(self.desp_path, 'r', encoding='utf-8') as json_file:
                            self.desp_json = json.load(json_file)
                        self.statusBar().showMessage('descriptions.json 文件已加载.')

                        im_path = list(self.desp_json["samples"].keys())[-1]
                        img_file_name = os.path.basename(im_path)

                        load_file_path = os.path.join(self.last_open_dir, img_file_name)
                        logger.debug(load_file_path)
                        self.cur_img_idx = 0
                        for i in range(self.file_list_widget.count()):
                            if self.file_list_widget.item(i).text() == load_file_path:
                                self.cur_img_idx = i
                                self.file_list_widget.setCurrentRow(i)
                                self.load_file(load_file_path)
                                break
                    except Exception as e:
                        QMessageBox.warning(self, '警告', f'加载 descriptions.json 文件时发生错误: {str(e)}')

    def open_annotation_dialog(self, _value=False):
        if self.file_path is None:
            # self.statusBar().showMessage('Please select image first')
            # self.statusBar().show()
            return

        path = os.path.dirname(ustr(self.file_path)) \
            if self.file_path else '.'
        if self.label_file_format == LabelFileFormat.PASCAL_VOC:
            filters = "Open Annotation XML file (%s)" % ' '.join(['*.xml'])
            filename = ustr(QFileDialog.getOpenFileName(self, '%s - Choose a xml file' % __appname__, path, filters))
            if filename:
                if isinstance(filename, (tuple, list)):
                    filename = filename[0]
            self.load_pascal_xml_by_filename(filename)

    def open_dir_dialog(self, _value=False, dir_path=None, silent=False):
        """
        打开目录选择对话框，并根据用户选择或默认路径执行操作。

        Args:
            _value (bool): 触发该函数的控件的值（通常不用）。
            dir_path (str): 传入的目录路径（可选）。
            silent (bool): 是否静默运行，不弹出对话框。

        Returns:
            None
        """
        # 如果用户未确认继续，则退出
        if not self.may_continue():
            return

        # 设置默认打开目录的优先级
        if dir_path:
            self.default_open_dir = dir_path
        elif self.last_open_dir and os.path.exists(self.last_open_dir):
            self.default_open_dir = self.last_open_dir
        elif self.file_path and os.path.exists(self.file_path):
            self.default_open_dir = (
                self.file_path if os.path.isdir(self.file_path) else os.path.dirname(self.file_path)
            )
        else:
            self.default_open_dir = '.'

        print("默认打开目录:", self.default_open_dir)

        # 如果不是静默模式，则弹出目录选择对话框
        if not silent:
            # 弹出选择对话框，选择导入方式
            choice_dialog = QMessageBox(self)
            choice_dialog.setWindowTitle("选择导入方式")
            choice_dialog.setText("请选择导入方式:")
            open_video_button = choice_dialog.addButton("Open Video", QMessageBox.ActionRole)
            images_button = choice_dialog.addButton("Images", QMessageBox.ActionRole)
            cancel_button = choice_dialog.addButton(QMessageBox.Cancel)
            choice_dialog.setDefaultButton(images_button)
            choice_dialog.exec_()

            if choice_dialog.clickedButton() == open_video_button:
                # 用户选择了 Open Video
                video_dir_path = self.open_video()  # 假设 open_video 方法返回处理后的图像文件夹路径
                if not video_dir_path or not os.path.exists(video_dir_path):
                    self.show_message("错误", "视频处理失败或返回的目录不存在。")
                    return
                target_dir_path = video_dir_path
            elif choice_dialog.clickedButton() == images_button:
                # 用户选择了 Images，弹出目录选择对话框
                selected_dir_path = QFileDialog.getExistingDirectory(
                    self,
                    f'{__appname__} - Open Directory',
                    self.default_open_dir,
                    QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks
                )

                # 如果用户取消了选择，直接返回
                if not selected_dir_path:
                    self.show_message("提示", "未选择任何目录。")
                    return
                target_dir_path = str(selected_dir_path)
            else:
                # 用户点击了取消按钮
                self.show_message("提示", "操作已取消。")
                return
        else:
            # 静默模式下直接使用默认目录
            target_dir_path = str(self.default_open_dir)

        # 更新上次打开的目录路径
        self.last_open_dir = target_dir_path
        self.default_save_dir = self.last_open_dir

        # 执行导入目录图片并启动文件监视器
        self.import_dir_images(target_dir_path)
        self.start_folder_watcher()

    from PyQt5.QtCore import QCoreApplication

    def open_video(self, dir_path=None):
        # 如果用户未确认继续，则退出
        if not self.may_continue():
            return

        # 1. 选择视频文件
        selected_file, _ = QFileDialog.getOpenFileName(
            self,
            f'{__appname__} - 选择视频文件',
            self.default_open_dir if hasattr(self, 'default_open_dir') else '.',
            "视频文件 (*.mp4 *.avi *.mov *.mkv *.MP4);;所有文件 (*)"
        )
        if not selected_file:
            self.show_message("提示", "未选择任何视频文件。")
            return

        video_path = selected_file
        video_dir = os.path.dirname(video_path)
        print(f"选择的视频文件路径: {video_path}")

        # 2. 先打开视频，获取原始分辨率
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            self.show_message("错误", "无法打开视频文件。")
            return

        original_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        original_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        print(f"视频原始分辨率: {original_width} x {original_height}")

        # 也可以获取总帧数、fps 等信息；此时暂时不关闭 cap，或者先关再重开都行
        # total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        # fps = cap.get(cv2.CAP_PROP_FPS)
        # ...
        # cap.release()  # 如果想重开，可以这里先释放

        # 3. 打开“提取帧设置”对话框（一次性让用户填写）
        #    把刚获取的视频宽高作为对话框的默认宽高
        settings_dialog = FrameExtractSettingsDialog(
            parent=self,
            default_interval=1,  # 默认为每帧提取
            default_width=original_width,
            default_height=original_height,
            default_format="PNG"
        )
        if settings_dialog.exec_() != QDialog.Accepted:
            # 用户按了“取消”
            self.show_message("提示", "已取消操作。")
            return

        # 用户点“确定”后，通过 get_values() 获取设置
        interval, width, height, format_str = settings_dialog.get_values()
        print(f"帧间隔 = {interval}, 图像宽度 = {width}, 高度 = {height}, 格式 = {format_str}")

        # “JPG” -> Pillow 的 “JPEG”
        if format_str == "JPG":
            pil_format = "JPEG"
        else:
            pil_format = format_str

        # 4. 创建保存目录
        video_name = os.path.splitext(os.path.basename(video_path))[0]
        frames_dir = os.path.join(video_dir, f"{video_name}_frames")
        os.makedirs(frames_dir, exist_ok=True)
        print(f"帧将保存到文件夹: {frames_dir}")

        # 这里如果之前调用了 cap.release()，需要重新打开视频
        # 如果还没关就能直接用
        # cap = cv2.VideoCapture(video_path)  # 如果之前释放了 cap，请重新打开

        if not cap.isOpened():
            self.show_message("错误", "无法打开视频文件。")
            return

        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        print(f"总帧数: {total_frames}, FPS: {fps}")

        # 5. 显示进度对话框，开始逐帧读取
        progress = QProgressDialog("正在提取视频帧，请稍候...", "取消", 0, total_frames, self)
        progress.setWindowTitle("提取进度")
        progress.setWindowModality(Qt.WindowModal)
        progress.resize(400, 100)
        progress.show()

        frame_count = 0
        saved_count = 0
        update_interval = max(1, total_frames // 200)

        while True:
            ret, frame = cap.read()
            if not ret:
                print("视频读取结束或读取失败。")
                break

            if frame_count % interval == 0:
                # 缩放
                resized_frame = frame
                if width > 0 and height > 0:
                    resized_frame = cv2.resize(
                        frame, (width, height), interpolation=cv2.INTER_AREA
                    )

                # 保存
                frame_ext = pil_format.lower()  # png, jpeg, bmp
                frame_filename = os.path.join(
                    frames_dir, f"frame_{frame_count:06d}.{frame_ext}"
                )
                try:
                    rgb_frame = cv2.cvtColor(resized_frame, cv2.COLOR_BGR2RGB)
                    img = Image.fromarray(rgb_frame)
                    img.save(frame_filename, pil_format)
                    saved_count += 1
                    print(f"保存帧: {frame_filename}")
                except Exception as e:
                    print(f"保存帧失败: {frame_filename}, 错误: {e}")

            if frame_count % update_interval == 0:
                progress.setValue(frame_count)
                QCoreApplication.processEvents()
                if progress.wasCanceled():
                    print("用户取消了操作。")
                    break

            frame_count += 1

        # 完成
        progress.setValue(total_frames)
        cap.release()
        progress.close()

        self.show_message("完成", f"已成功提取 {saved_count} 帧，保存在 {frames_dir}。")
        print(f"提取完成，保存了 {saved_count} 帧。")
        return frames_dir

    def start_folder_watcher(self):
        if self.last_open_dir:
            event_handler = MyHandler(self)  # FileEventHandler(self, self.last_open_dir)
            self.observer = Observer()
            self.observer.schedule(event_handler, path=self.last_open_dir, recursive=True)
            self.observer.start()

    def stop_folder_watcher(self):
        if self.observer is not None:
            self.observer.stop()
            self.observer.join()

    def insert_images(self, files):
        t = time.time()
        # logger.debug(f'insert images')
        if files:
            for file in files:
                if os.path.exists(file):
                    item = QListWidgetItem(file)
                    self.file_list_widget.addItem(item)
            self.m_img_list = [self.file_list_widget.item(i).text() for i in range(self.file_list_widget.count())]
            logger.debug(
                f'END insert images {len(files)}, total={self.file_list_widget.count()}, using {(time.time() - t) * 1000} ms')

    def delete_images(self, files):
        logger.debug(f'delete images')
        if files:
            for file in files:
                for i in range(self.file_list_widget.count()):
                    if file == self.file_list_widget.item(i).text():
                        self.file_list_widget.takeItem(i)
                        break
            self.m_img_list = [self.file_list_widget.item(i).text() for i in range(self.file_list_widget.count())]
            logger.debug(f'END delete images {len(files)}  total={self.file_list_widget.count()}')

    def closeEvent(self, event):
        self.stop_folder_watcher()
        event.accept()

    def label(self):
        pass

    def stop_auto_label(self):
        self.stop_signal.emit()

    def load_file_with_annotation(self, filename):
        if filename:
            if os.path.exists(filename):
                self.load_file(filename)

    def auto_label(self):

        # 检查是否设置了目录路径
        if not self.default_save_dir:
            self.show_message("Error", "选择查看中的自动保存，然后在文件菜单中更改文本结果存放路径")
            return
        if not os.path.exists(self.default_save_dir):
            self.show_message("Error", "选择查看中的自动保存，然后在文件菜单中更改文本结果存放路径")
            return
        if self.isOutputJson:
            if not self.desp_path:
                self.show_message("Error", "请先在文件菜单中设置json文件存放目录")
                return
            # 检查目录路径是否存在
            if not os.path.exists(self.desp_path):
                state = init_json(self.desp_path, self.label_hist)
                self.show_message("Info", "已初始化desp.json文件.")

        logger.debug('开始标注')

        selected_model_name = self.model_combobox.currentText()
        # 检查是否选择了算法
        if selected_model_name == "":
            self.show_message("Error", "请先选择算法。")
            return
        logger.debug(f"当前模型{selected_model_name}")
        if selected_model_name.startswith('pytracking'):
            config_loader = LoadConfig()
            config_data = config_loader.load_model_config(selected_model_name)
            model_name = config_data.get("algo_name")
            model_param = config_data.get("algo_param")
            logger.debug(f'model name = {model_name}, model param = {model_param}')
            self.callapi = Callapi(self, model_name=model_name, model_param=model_param, remote=True,
                                   config=config_data, speed_track=self.speed_track)
            self.stop_signal.connect(self.callapi.stop)
            # self.callapi.load_file_signal.connect(self.load_file_with_annotation)
            self.callapi.save_file_signal.connect(self.my_save_labels)
            self.callapi.show_message_signal.connect(self.show_message)
            time.sleep(1)
            self.callapi.start()
        elif selected_model_name.startswith('inner'):
            self.callapi = Callapi(self, remote=False, model_name=selected_model_name, speed_track=self.speed_track)
            self.stop_signal.connect(self.callapi.stop)

            self.callapi.load_file_signal.connect(self.load_file_with_annotation)
            self.callapi.save_file_signal.connect(self.my_save_labels)
            logger.debug('auto_label_call_local_api')
            time.sleep(1)
            self.callapi.start()

    def auto_label(self):
        # 检查是否设置了目录路径
        if not self.default_save_dir:
            self.show_message("Error", "选择查看中的自动保存，然后在文件菜单中更改文本结果存放路径")
            return
        if not os.path.exists(self.default_save_dir):
            self.show_message("Error", "选择查看中的自动保存，然后在文件菜单中更改文本结果存放路径")
            return
        if self.isOutputJson:
            if not self.desp_path:
                self.show_message("Error", "请先在文件菜单中设置json文件存放目录")
                return
            # 检查目录路径是否存在
            if not os.path.exists(self.desp_path):
                state = init_json(self.desp_path, self.label_hist)
                self.show_message("Info", "已初始化desp.json文件.")

        logger.debug('开始标注')

        selected_model_name = self.model_combobox.currentText()
        # 检查是否选择了算法
        if selected_model_name == "":
            self.show_message("Error", "请先选择算法。")
            return
        logger.debug(f"当前模型{selected_model_name}")

        # 根据模型名称确定模式
        if selected_model_name.startswith('pytracking'):
            # 远程跟踪模式
            config_loader = LoadConfig()
            config_data = config_loader.load_model_config(selected_model_name)
            model_name = config_data.get("algo_name")
            model_param = config_data.get("algo_param")
            logger.debug(f'model name = {model_name}, model param = {model_param}')
            self.callapi = Callapi(self, model_name=model_name, model_param=model_param, remote=True,
                                   config=config_data, speed_track=self.speed_track)
            self.stop_signal.connect(self.callapi.stop)
            # self.callapi.load_file_signal.connect(self.load_file_with_annotation)
            self.callapi.save_file_signal.connect(self.my_save_labels)
            self.callapi.show_message_signal.connect(self.show_message)
            time.sleep(1)
            self.callapi.start()

        elif selected_model_name.startswith('inner'):
            # 本地跟踪模式
            self.callapi = Callapi(self, remote=False, model_name=selected_model_name, speed_track=self.speed_track)
            self.stop_signal.connect(self.callapi.stop)

            self.callapi.load_file_signal.connect(self.load_file_with_annotation)
            self.callapi.save_file_signal.connect(self.my_save_labels)
            logger.debug('auto_label_call_local_api')
            time.sleep(1)
            self.callapi.start()

        elif selected_model_name.startswith('detect'):
            # 检测模式
            logger.debug('auto_label_call_detect_api')

            # 获取配置（确保 get_config 方法返回了必要的配置）
            config_loader = LoadConfig()
            config_data = config_loader.load_model_config(selected_model_name)
            model_name = config_data.get("algo_name")
            model_param = config_data.get("algo_param")
            logger.debug(f'model name = {model_name}, model param = {model_param}')

            # 创建 Callapi 线程，指定为 'detect' 模式
            self.callapi = Callapi(self, model_name=model_name, model_param=model_param, remote=True,
                                   config=config_data, speed_track=self.speed_track)
            self.stop_signal.connect(self.callapi.stop)

            # 连接信号
            self.callapi.save_file_signal.connect(self.my_save_labels)
            self.callapi.show_message_signal.connect(self.show_message)
            time.sleep(1)
            self.callapi.start()

        else:
            # 未知模式
            self.show_message("Error", f"未知的模型名称: {selected_model_name}")
            logger.error(f"未知的模型名称: {selected_model_name}")
            return

    def show_message(self, title, message):
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Information)
        msg.setWindowTitle(title)
        msg.setText(message)
        msg.exec_()

    def import_dir_images(self, dir_path):
        """
        导入指定文件夹中的图像，并更新界面列表。如果文件夹中没有图像，弹出提示窗口。

        Args:
            dir_path (str): 要导入的文件夹路径。

        Returns:
            None
        """
        if not self.may_continue() or not dir_path:
            return

        self.last_open_dir = dir_path
        self.dir_name = dir_path
        self.file_path = None
        self.file_list_widget.clear()
        self.m_img_list = self.scan_all_images(dir_path)
        self.img_count = len(self.m_img_list)

        if self.img_count == 0:
            # 文件夹中没有图像文件，弹出提示窗口
            self.show_message("提示", "所选文件夹中没有图像文件。")
            return

        self.open_next_image()
        for imgPath in self.m_img_list:
            item = QListWidgetItem(imgPath)
            self.file_list_widget.addItem(item)

    def verify_image(self, _value=False):
        # Proceeding next image without dialog if having any label
        if self.file_path is not None:
            try:
                self.label_file.toggle_verify()
            except AttributeError:
                # If the labelling file does not exist yet, create if and
                # re-save it with the verified attribute.
                self.save_file()
                if self.label_file is not None:
                    self.label_file.toggle_verify()
                else:
                    return

            self.canvas.verified = self.label_file.verified
            self.paint_canvas()
            self.save_file()

    def open_file(self, _value=False):
        if not self.may_continue():
            return
        path = os.path.dirname(ustr(self.file_path)) if self.file_path else '.'
        formats = ['*.%s' % fmt.data().decode("ascii").lower() for fmt in QImageReader.supportedImageFormats()]
        filters = "Image & Label files (%s)" % ' '.join(formats + ['*%s' % LabelFile.suffix])

        # 获取文件名和选中的过滤器
        filename, _ = QFileDialog.getOpenFileName(
            self,
            '%s - Choose Image or Label file' % __appname__,
            path,
            filters
        )

        # 检查文件名是否为空
        if filename:
            self.cur_img_idx = 0
            self.img_count = 1
            self.load_file(filename)
        else:
            # 用户取消选择文件，不执行任何操作
            return

    def save_file(self, _value=False):
        try:
            # 检查默认保存目录是否有效
            if self.default_save_dir is not None and len(ustr(self.default_save_dir)):
                if self.file_path:
                    image_file_name = os.path.basename(self.file_path)
                    saved_file_name = os.path.splitext(image_file_name)[0]
                    saved_path = os.path.join(ustr(self.default_save_dir), saved_file_name)

                    # 确保路径有效且可以写入
                    if not os.path.exists(self.default_save_dir):
                        raise FileNotFoundError(f"保存目录不存在: {self.default_save_dir}")
                    if not os.access(self.default_save_dir, os.W_OK):
                        raise PermissionError(f"没有写入权限: {self.default_save_dir}")

                    # 仅在内容非空时保存文件
                    if self._save_file(saved_path):
                        self.canvas_to_mem(self.file_path)
                        self.dump_json()
                    else:
                        # 如果内容为空，则删除文件
                        self._delete_file_if_empty(saved_path)

            else:
                image_file_dir = os.path.dirname(self.file_path)
                image_file_name = os.path.basename(self.file_path)
                saved_file_name = os.path.splitext(image_file_name)[0]
                saved_path = os.path.join(image_file_dir, saved_file_name)

                # 如果自定义的保存路径无效，则使用保存对话框
                if not self.save_file_dialog(remove_ext=False):
                    raise ValueError("未选择有效的保存路径")

                # 确保路径有效且可以写入
                if not os.access(image_file_dir, os.W_OK):
                    raise PermissionError(f"没有写入权限: {image_file_dir}")

                # 仅在内容非空时保存文件
                if self._save_file(saved_path if self.label_file else self.save_file_dialog(remove_ext=False)):
                    self.canvas_to_mem(self.file_path)
                    self.dump_json()
                else:
                    # 如果内容为空，则删除文件
                    self._delete_file_if_empty(saved_path)

        except FileNotFoundError as e:
            print(f"文件错误: {e}")
        except PermissionError as e:
            print(f"权限错误: {e}")
        except ValueError as e:
            print(f"值错误: {e}")
        except Exception as e:
            print(f"未知错误: {e}")

    def _delete_file_if_empty(self, file_path):
        # 检查文件是否存在且内容为空，然后删除文件
        if os.path.exists(file_path + '.txt') and os.path.getsize(file_path + '.txt') == 0:
            os.remove(file_path + '.txt')

    def save_file_as(self, _value=False):
        assert not self.image.isNull(), "cannot save empty image"
        self._save_file(self.save_file_dialog())

    def save_file_dialog(self, remove_ext=True):
        caption = '%s - Choose File' % __appname__
        filters = 'File (*%s)' % LabelFile.suffix
        open_dialog_path = self.current_path()
        dlg = QFileDialog(self, caption, open_dialog_path, filters)
        dlg.setDefaultSuffix(LabelFile.suffix[1:])
        dlg.setAcceptMode(QFileDialog.AcceptSave)
        filename_without_extension = os.path.splitext(self.file_path)[0]
        dlg.selectFile(filename_without_extension)
        dlg.setOption(QFileDialog.DontUseNativeDialog, False)
        if dlg.exec_():
            full_file_path = ustr(dlg.selectedFiles()[0])
            if remove_ext:
                return os.path.splitext(full_file_path)[0]  # Return file path without the extension.
            else:
                return full_file_path
        return ''

    def _save_file(self, annotation_file_path):
        if annotation_file_path and self.save_labels(annotation_file_path):
            self.set_clean()
            # self.statusBar().showMessage('Saved to  %s' % annotation_file_path)
            # self.statusBar().show()

    def close_file(self, _value=False):
        if not self.may_continue():
            return
        self.reset_state()
        self.set_clean()
        self.toggle_actions(False)
        self.canvas.setEnabled(False)
        self.actions.saveAs.setEnabled(False)

    def delete_image(self):
        delete_path = self.file_path
        if delete_path is not None:
            self.open_next_image()
            self.cur_img_idx -= 1
            self.img_count -= 1
            if os.path.exists(delete_path):
                os.remove(delete_path)
            self.import_dir_images(self.last_open_dir)

    def reset_all(self):
        pass
        # self.settings.reset()
        # self.close()
        # process = QProcess()
        # process.startDetached(os.path.abspath(__file__))

    def may_continue(self):
        if not self.dirty:
            return True
        else:
            discard_changes = self.discard_changes_dialog()
            if discard_changes == QMessageBox.No:
                return True
            elif discard_changes == QMessageBox.Yes:
                self.save_file()
                return True
            else:
                return False

    def discard_changes_dialog(self):
        yes, no, cancel = QMessageBox.Yes, QMessageBox.No, QMessageBox.Cancel
        msg = u'You have unsaved changes, would you like to save them and proceed?\nClick "No" to undo all changes.'
        return QMessageBox.warning(self, u'Attention', msg, yes | no | cancel)

    def error_message(self, title, message):
        return QMessageBox.critical(self, title,
                                    '<p><b>%s</b></p>%s' % (title, message))

    def current_path(self):
        return os.path.dirname(self.file_path) if self.file_path else '.'

    def choose_color1(self):
        color = self.color_dialog.getColor(self.line_color, u'Choose line color',
                                           default=DEFAULT_LINE_COLOR)
        if color:
            self.line_color = color
            Shape.line_color = color
            self.canvas.set_drawing_color(color)
            self.canvas.update()
            self.set_dirty()

    def delete_selected_shape(self):
        """删除当前选中的标注，并将其保存到撤销栈中"""
        deleted_shape = self.canvas.delete_selected()
        if deleted_shape:
            self.undo_stack.append(deleted_shape)
            self.remove_label(deleted_shape)
            print("删除")
            self.set_dirty()
            if self.no_shapes():
                for action in self.actions_onShapesPresent():
                    action.setEnabled(False)
        else:
            print("没有选中任何标注框")

    # def delete_selected_shape(self):
    #     self.remove_label(self.canvas.delete_selected())
    #     self.set_dirty()
    #     if self.no_shapes():
    #         for action in self.actions.onShapesPresent:
    #             action.setEnabled(False)
    def undo_delete(self):
        """撤销上一步删除操作"""
        if self.undo_stack:
            shape = self.undo_stack.pop()
            # 使用深拷贝，确保恢复的对象状态正常
            restored_shape = shape.copy()
            # 如果需要显示标签，确保 paint_label 为 True
            # restored_shape.paint_label = True
            self.canvas.restore_shape(restored_shape)
            print("撤销删除")
            self.set_dirty()
            # self.add_label(self.canvas.selected_shape)

            # 如果你不使用 actions_onShapesPresent，可将此部分注释掉
            # for action in self.actions_onShapesPresent():
            #     action.setEnabled(True)
        else:
            print("没有可以撤销的操作")

    def choose_shape_line_color(self):
        color = self.color_dialog.getColor(self.line_color, u'Choose Line Color',
                                           default=DEFAULT_LINE_COLOR)
        if color:
            self.canvas.selected_shape.line_color = color
            self.canvas.update()
            self.set_dirty()

    def choose_shape_fill_color(self):
        color = self.color_dialog.getColor(self.fill_color, u'Choose Fill Color',
                                           default=DEFAULT_FILL_COLOR)
        if color:
            self.canvas.selected_shape.fill_color = color
            self.canvas.update()
            self.set_dirty()

    def copy_shape(self):
        self.canvas.end_move(copy=True)
        self.add_label(self.canvas.selected_shape)
        self.set_dirty()

    def move_shape(self):
        self.canvas.end_move(copy=False)
        self.set_dirty()

    def load_predefined_classes(self, predef_classes_file):
        if os.path.exists(predef_classes_file):
            self.label_hist = None
            with codecs.open(predef_classes_file, 'r', 'utf8') as f:
                for line in f:
                    line = line.strip()
                    if self.label_hist is None:
                        self.label_hist = [line]
                    else:
                        self.label_hist.append(line)

    def load_pascal_xml_by_filename(self, xml_path):
        if self.file_path is None:
            return
        if os.path.isfile(xml_path) is False:
            return

        self.set_format(FORMAT_PASCALVOC)

        t_voc_parse_reader = PascalVocReader(xml_path)
        shapes = t_voc_parse_reader.get_shapes()
        self.load_labels(shapes)
        self.canvas.verified = t_voc_parse_reader.verified

    def load_yolo_txt_by_filename(self, txt_path):
        if self.file_path is None:
            return
        if os.path.isfile(txt_path) is False:
            return

        self.set_format(FORMAT_YOLO)
        t_yolo_parse_reader = YoloReader(txt_path, self.image)
        shapes = t_yolo_parse_reader.get_shapes()
        print("shape:", shapes)
        self.load_labels(shapes)
        self.canvas.verified = t_yolo_parse_reader.verified

        # 检查每个边界框是否在图像边缘
        if self.are_shapes_within_image_dimensions(shapes):
            print("shape:", shapes)
            # self.load_labels(shapes)
            # self.canvas.verified = t_yolo_parse_reader.verified
        else:
            # 如果有边界框超出边缘，弹出询问窗口

            # 停止标注
            # self.stop_auto_label()
            # print("停止标注")
            print("shape:", shapes)

    def are_shapes_within_image_dimensions(self, shapes):
        # 用实际的获取图像尺寸的方法替代
        global width, height
        filename = self.m_img_list[self.cur_img_idx]

        if os.path.exists(filename):
            image = Image.open(filename)
            # 获取图片的宽度和高度
            width, height = image.size
            image.close()

        for _, points, _, _, _ in shapes:
            for x, y in points:
                image_width, image_height = width, height
                if not (2 <= x < image_width and 2 <= y < image_height):  # or (image_width <= x or image_height <= y)):
                    return False
        return True

        # for shape_name, points, _, _, _ in shapes:
        #     x_min, y_min = points[0]
        #     x_max, y_max = points[2]
        #
        #     # 检查框是否靠近图像的左边缘、右边缘、上边缘或下边缘
        #     image_width, image_height = width, height
        #     is_near_left_edge = x_min <= 2
        #     is_near_right_edge = x_max >= image_width - 2
        #     is_near_top_edge = y_min <= 2
        #     is_near_bottom_edge = y_max >= image_height - 2
        #
        #     # 如果任意一个框在图像的边缘，返回False
        #     if is_near_left_edge or is_near_right_edge or is_near_top_edge or is_near_bottom_edge:
        #         return False
        #
        #     # 所有框都不在图像的边缘
        # return True

    def load_create_ml_json_by_filename(self, json_path, file_path):
        if self.file_path is None:
            return
        if os.path.isfile(json_path) is False:
            return

        self.set_format(FORMAT_CREATEML)

        create_ml_parse_reader = CreateMLReader(json_path, file_path)
        shapes = create_ml_parse_reader.get_shapes()
        self.load_labels(shapes)
        self.canvas.verified = create_ml_parse_reader.verified

    def copy_previous_bounding_boxes(self):
        # 检查是否已加载图片
        if self.file_path is None:
            self.show_message("提示", "没有加载图片，无法执行复制操作。")
            return

        # 获取当前图像在图像列表中的索引
        current_index = self.m_img_list.index(self.file_path)

        # 判断是否存在上一张图像（索引不为0及以上）
        if current_index - 1 >= 0:
            # 获取上一张图像的文件路径
            prev_file_path = self.m_img_list[current_index - 1]
            try:
                self.show_bounding_box_from_annotation_file(prev_file_path)
                # 保存当前图像的标注
                self.save_file()
            except Exception as e:
                logger.debug(str(e))
                return
        else:
            self.show_message("提示", "没有上一张图像，无法复制。")

    def toggle_paint_labels_option(self):
        for shape in self.canvas.shapes:
            shape.paint_label = self.display_label_option.isChecked()

    def toggle_draw_square(self):
        self.canvas.set_drawing_shape_to_square(self.draw_squares_option.isChecked())

    def docker_manager(self):
        self.new_windows = DockerManagerApp()
        self.new_windows_exists = True
        self.new_windows.show()
        # docker_manager_window = show_docker_manager_window(app)
        # docker_manager_window.show()

    def data_process(self):
        self.new_windows = DataMainWindow()
        self.new_windows_exists = True
        self.new_windows.show()


def inverted(color):
    return QColor(*[255 - v for v in color.getRgb()])


def read(filename, default=None):
    try:
        reader = QImageReader(filename)
        reader.setAutoTransform(True)
        return reader.read()
    except:
        return default


def get_main_app(argv=None):
    """
    Standard boilerplate Qt application code.
    Do everything but app.exec_() -- so that we can test the application in one thread
    """
    if argv is None:
        argv = []
    app = QApplication(argv)
    app.setApplicationName(__appname__)
    # app.setWindowIcon(new_icon("app"))
    # Tzutalin 201705+: Accept extra agruments to change predefined class file
    argparser = argparse.ArgumentParser()
    argparser.add_argument("image_dir", nargs="?")
    argparser.add_argument("class_file",
                           default=os.path.join(os.path.dirname(__file__), "data", "predefined_classes.txt"),
                           nargs="?")
    argparser.add_argument("save_dir", nargs="?")
    args = argparser.parse_args(argv[1:])

    args.image_dir = args.image_dir and os.path.normpath(args.image_dir)
    args.class_file = args.class_file and os.path.normpath(args.class_file)
    args.save_dir = args.save_dir and os.path.normpath(args.save_dir)

    # Usage : labelImg.py image classFile saveDir
    win = MainWindow(args.image_dir,
                     args.class_file,
                     args.save_dir)
    win.show()
    return app, win


# docker管理


def main():
    """construct main app and run it"""
    app, _win = get_main_app(sys.argv)
    # setup stylesheet
    # app.setStyleSheet(qdarkstyle.load_stylesheet_pyqt5())
    return app.exec_()


if __name__ == '__main__':
    # cProfile.run('main()', './profile')
    sys.exit(main())

import sys
import os
import cv2
import numpy as np
import random
from PyQt5.QtWidgets import QApplication, QWidget, QLabel, QPushButton, QVBoxLayout, QFileDialog, QLineEdit, QComboBox, \
    QProgressBar, QMessageBox, QTabWidget, QMainWindow, QHBoxLayout
from PyQt5.QtCore import Qt, QThread, pyqtSignal


class VideoFrameExtractor(QWidget):
    def __init__(self):
        super().__init__()
        self.initUI()
        self.video_path = None
        self.output_folder = None

    def initUI(self):
        self.interval_label = QLabel('帧提取间隔:')
        self.interval_input = QLineEdit()

        self.format_label = QLabel('图像格式:')
        self.format_combo = QComboBox()
        self.format_combo.addItems(['jpg', 'png'])

        self.resolution_label = QLabel('分辨率:')
        self.width_input = QLineEdit()
        self.x_label = QLabel('x')
        self.height_input = QLineEdit()

        self.video_btn = QPushButton('打开视频')
        self.video_btn.clicked.connect(self.openVideo)

        self.output_btn = QPushButton('选择输出文件夹')
        self.output_btn.clicked.connect(self.setOutputFolder)

        self.extract_btn = QPushButton('开始提取帧')
        self.extract_btn.clicked.connect(self.startExtraction)

        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setAlignment(Qt.AlignCenter)

        layout = QVBoxLayout()

        interval_layout = QHBoxLayout()
        interval_layout.addWidget(self.interval_label)
        interval_layout.addWidget(self.interval_input)
        layout.addLayout(interval_layout)

        format_layout = QHBoxLayout()
        format_layout.addWidget(self.format_label)
        format_layout.addWidget(self.format_combo)
        layout.addLayout(format_layout)

        resolution_layout = QHBoxLayout()
        resolution_layout.addWidget(self.resolution_label)
        resolution_layout.addWidget(self.width_input)
        resolution_layout.addWidget(self.x_label)
        resolution_layout.addWidget(self.height_input)
        layout.addLayout(resolution_layout)

        layout.addWidget(self.video_btn)
        layout.addWidget(self.output_btn)
        layout.addWidget(self.extract_btn)
        layout.addWidget(self.progress_bar)

        self.setLayout(layout)

    def openVideo(self):
        video_path, _ = QFileDialog.getOpenFileName(
            self, '打开视频文件', '', 'Video Files (*.mp4 *.MP4 *.avi *.AVI *.mov *.MOV *.mkv *.MKV)')
        if video_path:
            self.video_path = video_path
            cap = cv2.VideoCapture(self.video_path)
            if not cap.isOpened():
                QMessageBox.warning(self, '警告', '无法打开视频文件。请确认视频格式受支持，或安装必要的编解码器。')
                return
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            self.width_input.setText(str(width))
            self.height_input.setText(str(height))
            cap.release()

    def setOutputFolder(self):
        output_folder = QFileDialog.getExistingDirectory(self, '选择输出文件夹')
        if output_folder:
            self.output_folder = output_folder

    def startExtraction(self):
        if not hasattr(self, 'video_path') or not self.video_path:
            QMessageBox.warning(self, '警告', '请先选择视频文件。')
            return
        if not hasattr(self, 'output_folder') or not self.output_folder:
            QMessageBox.warning(self, '警告', '请先选择输出文件夹。')
            return
        if not self.interval_input.text().isdigit():
            QMessageBox.warning(self, '警告', '请输入有效的帧提取间隔。')
            return
        if not self.width_input.text().isdigit() or not self.height_input.text().isdigit():
            QMessageBox.warning(self, '警告', '请输入有效的分辨率。')
            return

        interval = int(self.interval_input.text())
        image_format = self.format_combo.currentText()
        resolution = f"{self.width_input.text()}x{self.height_input.text()}"

        self.thread = FrameExtractionThread(self.video_path, self.output_folder, interval, image_format, resolution)
        self.thread.progress.connect(self.progress_bar.setValue)
        self.thread.finished.connect(self.extractionFinished)
        self.thread.start()

    def extractionFinished(self):
        QMessageBox.information(self, '信息', '帧提取完成！')
        self.progress_bar.setValue(0)


class FrameExtractionThread(QThread):
    progress = pyqtSignal(int)
    finished = pyqtSignal()

    def __init__(self, video_path, output_folder, interval, image_format, resolution):
        super().__init__()
        self.video_path = video_path
        self.output_folder = output_folder
        self.interval = interval
        self.format = image_format
        self.resolution = resolution

    def run(self):
        width, height = map(int, self.resolution.split('x'))
        cap = cv2.VideoCapture(self.video_path)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        frame_count = 1

        # 获取视频文件名（不含扩展名）
        video_name = os.path.splitext(os.path.basename(self.video_path))[0]

        while True:
            ret, frame = cap.read()
            if not ret:
                break
            if frame_count % self.interval == 0:
                frame = cv2.resize(frame, (width, height))
                # 使用视频名和帧号命名文件
                frame_path = os.path.join(self.output_folder, f"{video_name}_{frame_count}.{self.format}")
                cv2.imwrite(frame_path, frame)
            progress_value = int((frame_count / total_frames) * 100)
            self.progress.emit(progress_value)
            frame_count += 1

        cap.release()
        self.finished.emit()


class ImageCropper(QWidget):
    def __init__(self):
        super().__init__()
        self.initUI()
        self.src_im_fold = None
        self.src_lb_fold = None
        self.dst_im_fold = None

    def initUI(self):
        self.src_im_fold_label = QLabel('源图像文件夹:')
        self.src_im_fold_btn = QPushButton('选择')
        self.src_im_fold_btn.clicked.connect(self.selectSrcImFold)

        self.src_lb_fold_label = QLabel('源标签文件夹:')
        self.src_lb_fold_btn = QPushButton('选择')
        self.src_lb_fold_btn.clicked.connect(self.selectSrcLbFold)

        self.dst_im_fold_label = QLabel('目标图像文件夹:')
        self.dst_im_fold_btn = QPushButton('选择')
        self.dst_im_fold_btn.clicked.connect(self.selectDstImFold)

        self.pixel_input = QLineEdit(self)
        self.pixel_input.setPlaceholderText("输入像素值（如：30表示扩张，-20表示收缩）")

        self.crop_btn = QPushButton('开始裁剪')
        self.crop_btn.clicked.connect(self.startCropping)

        self.progress_bar = QProgressBar(self)
        self.progress_bar.setMaximum(100)

        layout = QVBoxLayout()
        layout.addWidget(self.src_im_fold_label)
        layout.addWidget(self.src_im_fold_btn)
        layout.addWidget(self.src_lb_fold_label)
        layout.addWidget(self.src_lb_fold_btn)
        layout.addWidget(self.dst_im_fold_label)
        layout.addWidget(self.dst_im_fold_btn)
        layout.addWidget(self.pixel_input)
        layout.addWidget(self.crop_btn)
        layout.addWidget(self.progress_bar)

        self.setLayout(layout)

    def selectSrcImFold(self):
        self.src_im_fold = QFileDialog.getExistingDirectory(self, '选择源图像文件夹')
        if self.src_im_fold:
            self.src_im_fold_label.setText(f"源图像文件夹: {self.src_im_fold}")

    def selectSrcLbFold(self):
        self.src_lb_fold = QFileDialog.getExistingDirectory(self, '选择源标签文件夹')
        if self.src_lb_fold:
            self.src_lb_fold_label.setText(f"源标签文件夹: {self.src_lb_fold}")

    def selectDstImFold(self):
        self.dst_im_fold = QFileDialog.getExistingDirectory(self, '选择目标图像文件夹')
        if self.dst_im_fold:
            self.dst_im_fold_label.setText(f"目标图像文件夹: {self.dst_im_fold}")

    def startCropping(self):
        if not self.src_im_fold or not self.src_lb_fold or not self.dst_im_fold:
            QMessageBox.warning(self, '警告', '请先选择所有必要的文件夹。')
            return

        try:
            pixel_adjustment = int(self.pixel_input.text()) if self.pixel_input.text() else 0
        except ValueError:
            QMessageBox.warning(self, '警告', '请输入有效的像素值。')
            return

        self.crop_thread = CropThread(self.src_im_fold, self.src_lb_fold, self.dst_im_fold, pixel_adjustment)
        self.crop_thread.progress.connect(self.progress_bar.setValue)
        self.crop_thread.finished.connect(self.onCroppingFinished)
        self.crop_thread.start()

    def onCroppingFinished(self):
        QMessageBox.information(self, '信息', '裁剪完成！')


class CropThread(QThread):
    finished = pyqtSignal()
    progress = pyqtSignal(int)

    def __init__(self, src_im_fold, src_lb_fold, dst_im_fold, pixel_adjustment):
        super().__init__()
        self.src_im_fold = src_im_fold
        self.src_lb_fold = src_lb_fold
        self.dst_im_fold = dst_im_fold
        self.pixel_adjustment = pixel_adjustment

    def run(self):
        if not os.path.exists(self.dst_im_fold):
            os.makedirs(self.dst_im_fold)

        valid_extensions = (".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".gif")
        f_list = [fn for fn in os.listdir(self.src_im_fold) if fn.lower().endswith(valid_extensions)]
        f_num = len(f_list)
        for idx, img_fn in enumerate(f_list):
            progress_percent = int((idx + 1) / f_num * 100)
            self.progress.emit(progress_percent)

            src_im_path = os.path.join(self.src_im_fold, img_fn)
            src_lb_path = os.path.join(self.src_lb_fold, img_fn.rsplit('.', 1)[0] + ".txt")
            if os.path.exists(src_lb_path):
                self.crop_image(src_im_path, src_lb_path, self.dst_im_fold, img_fn.rsplit('.', 1)[0])

        self.finished.emit()

    def crop_image(self, src_im_path, src_lb_path, dst_im_fold, idx):
        with open(src_lb_path, 'r') as f:
            annotations = f.readlines()

        img = cv2.imread(src_im_path)
        im_h, im_w, _ = img.shape

        for annotation_idx, annotation in enumerate(annotations):
            obj_class, cx_r_str, cy_r_str, w_r_str, h_r_str = annotation.split()

            roi_cx_f = float(cx_r_str)
            roi_cy_f = float(cy_r_str)
            roi_w_f = float(w_r_str)
            roi_h_f = float(h_r_str)

            roi_cx_new = int(roi_cx_f * im_w)
            roi_cy_new = int(roi_cy_f * im_h)
            roi_w_new = int(roi_w_f * im_w) + 2 * self.pixel_adjustment  # Adjust width
            roi_h_new = int(roi_h_f * im_h) + 2 * self.pixel_adjustment  # Adjust height

            # Calculate new x, y and ensure they are within image boundaries
            x = max(0, roi_cx_new - int(0.5 * roi_w_new))
            y = max(0, roi_cy_new - int(0.5 * roi_h_new))
            x_end = min(im_w, x + roi_w_new)
            y_end = min(im_h, y + roi_h_new)

            # Ensure x_end > x and y_end > y
            if x_end <= x or y_end <= y:
                continue  # Skip invalid regions

            img_crop = img[y:y_end, x:x_end]

            class_folder = os.path.join(dst_im_fold, str(obj_class))
            if not os.path.exists(class_folder):
                os.makedirs(class_folder)

            filename = os.path.join(class_folder, f"{idx}_{annotation_idx}.jpg")
            cv2.imwrite(filename, img_crop)


class BackgroundExtractor(QWidget):
    def __init__(self):
        super().__init__()
        self.initUI()
        self.src_im_fold = None
        self.src_lb_fold = None
        self.dst_im_fold = None

    def initUI(self):
        layout = QVBoxLayout()

        self.src_im_fold_label = QLabel('源图像文件夹:')
        self.src_im_fold_btn = QPushButton('选择')
        self.src_im_fold_btn.clicked.connect(self.selectSrcImFold)
        layout.addWidget(self.src_im_fold_label)
        layout.addWidget(self.src_im_fold_btn)

        self.src_lb_fold_label = QLabel('源标签文件夹:')
        self.src_lb_fold_btn = QPushButton('选择')
        self.src_lb_fold_btn.clicked.connect(self.selectSrcLbFold)
        layout.addWidget(self.src_lb_fold_label)
        layout.addWidget(self.src_lb_fold_btn)

        self.dst_im_fold_label = QLabel('目标图像文件夹:')
        self.dst_im_fold_btn = QPushButton('选择')
        self.dst_im_fold_btn.clicked.connect(self.selectDstImFold)
        layout.addWidget(self.dst_im_fold_label)
        layout.addWidget(self.dst_im_fold_btn)

        self.custom_name_input = QLineEdit()
        self.custom_name_input.setPlaceholderText("输入输出文件的自定义名称")
        layout.addWidget(self.custom_name_input)

        self.total_crops_input = QLineEdit()
        self.total_crops_input.setPlaceholderText("输入裁剪总数（如：4500）")
        layout.addWidget(self.total_crops_input)

        self.crops_per_image_input = QLineEdit()
        self.crops_per_image_input.setPlaceholderText("输入每张图片裁剪数量（如：1）")
        layout.addWidget(self.crops_per_image_input)

        self.crop_size_range_input = QLineEdit()
        self.crop_size_range_input.setPlaceholderText("输入裁剪尺寸范围（如：60,110）")
        layout.addWidget(self.crop_size_range_input)

        self.start_crop_btn = QPushButton("开始裁剪")
        self.start_crop_btn.clicked.connect(self.startCropping)
        layout.addWidget(self.start_crop_btn)

        self.progress_bar = QProgressBar()
        layout.addWidget(self.progress_bar)

        self.setLayout(layout)

    def selectSrcImFold(self):
        self.src_im_fold = QFileDialog.getExistingDirectory(self, '选择源图像文件夹')
        if self.src_im_fold:
            self.src_im_fold_label.setText(f"源图像文件夹: {self.src_im_fold}")

    def selectSrcLbFold(self):
        self.src_lb_fold = QFileDialog.getExistingDirectory(self, '选择源标签文件夹')
        if self.src_lb_fold:
            self.src_lb_fold_label.setText(f"源标签文件夹: {self.src_lb_fold}")

    def selectDstImFold(self):
        self.dst_im_fold = QFileDialog.getExistingDirectory(self, '选择目标图像文件夹')
        if self.dst_im_fold:
            self.dst_im_fold_label.setText(f"目标图像文件夹: {self.dst_im_fold}")

    def startCropping(self):
        if not self.src_im_fold or not self.src_lb_fold or not self.dst_im_fold:
            QMessageBox.warning(self, '警告', '请先选择所有必要的文件夹。')
            return

        try:
            custom_name = self.custom_name_input.text()
            total_crops = int(self.total_crops_input.text())
            crops_per_image = int(self.crops_per_image_input.text())
            crop_size_range = tuple(map(int, self.crop_size_range_input.text().split(',')))

            self.crop_thread = CropBackgroundThread(
                self.src_im_fold,
                self.src_lb_fold,
                self.dst_im_fold,
                custom_name,
                total_crops,
                crops_per_image,
                crop_size_range
            )
            self.crop_thread.progress.connect(self.progress_bar.setValue)
            self.crop_thread.finished.connect(self.onCroppingFinished)
            self.crop_thread.start()
        except ValueError:
            QMessageBox.warning(self, '警告', '请输入有效的裁剪设置。')

    def onCroppingFinished(self):
        QMessageBox.information(self, '信息', '背景裁剪完成！')


class CropBackgroundThread(QThread):
    finished = pyqtSignal()
    progress = pyqtSignal(int)

    def __init__(self, src_im_fold, src_lb_fold, dst_im_fold, custom_name, total_crops, crops_per_image,
                 crop_size_range):
        super().__init__()
        self.src_im_fold = src_im_fold
        self.src_lb_fold = src_lb_fold
        self.dst_im_fold = dst_im_fold
        self.custom_name = custom_name
        self.total_crops = total_crops
        self.crops_per_image = crops_per_image
        self.crop_size_range = crop_size_range

    def run(self):
        self.process_folder(
            self.src_im_fold,
            self.src_lb_fold,
            self.dst_im_fold,
            self.custom_name,
            self.total_crops,
            self.crops_per_image,
            self.crop_size_range
        )
        self.finished.emit()

    def load_annotations(self, annotation_path):
        with open(annotation_path, 'r') as file:
            lines = file.readlines()
            annotations = [line.strip().split() for line in lines]
        return annotations

    def get_random_crop_size(self, min_size, max_size):
        return random.randint(min_size, max_size), random.randint(min_size, max_size)

    def get_non_object_areas(self, image, annotations, num_crops, crop_size_range=(30, 90)):
        mask = np.ones(image.shape[:2], dtype=bool)
        height, width = image.shape[:2]

        for annotation in annotations:
            _, x_center, y_center, w, h = map(float, annotation)
            x_center, y_center, w, h = x_center * width, y_center * height, w * width, h * height
            x1, y1 = int(x_center - w / 2), int(y_center - h / 2)
            x2, y2 = int(x_center + w / 2), int(y_center + h / 2)
            x1, x2 = max(0, x1), min(width, x2)
            y1, y2 = max(0, y1), min(height, y2)
            mask[y1:y2, x1:x2] = False

        crops = []
        attempts = 0
        max_attempts = num_crops * 100  # 防止无限循环

        while len(crops) < num_crops and attempts < max_attempts:
            crop_size = self.get_random_crop_size(*crop_size_range)
            x = random.randint(0, width - crop_size[1])
            y = random.randint(0, height - crop_size[0])
            x2 = x + crop_size[1]
            y2 = y + crop_size[0]

            if mask[y:y2, x:x2].all():  # 检查裁剪区域是否完全避开目标框
                crop = image[y:y2, x:x2]
                crops.append(crop)
            attempts += 1

        return crops

    def process_folder(self, images_dir, annotations_dir, output_dir, custom_name, total_crops,
                       num_crops_per_image=5, crop_size_range=(30, 90)):
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        file_count = 1  # 用于文件命名的计数器
        image_files = os.listdir(images_dir)
        random.shuffle(image_files)  # 随机排序图片

        for filename in image_files:
            if file_count > total_crops:
                break  # 如果已经达到总裁剪数量，停止处理
            if filename.lower().endswith(('.png', '.jpg', '.jpeg')):
                image_path = os.path.join(images_dir, filename)
                annotation_path = os.path.join(annotations_dir, filename.rsplit('.', 1)[0] + '.txt')

                if os.path.exists(annotation_path):
                    image = cv2.imread(image_path)
                    annotations = self.load_annotations(annotation_path)
                    # 控制每张图片上的裁剪数量，同时确保不超出总裁剪数
                    num_crops = min(num_crops_per_image, total_crops - file_count + 1)
                    backgrounds = self.get_non_object_areas(image, annotations, num_crops, crop_size_range)

                    for background in backgrounds:
                        if file_count > total_crops:
                            break  # 检查是否达到总裁剪数量
                        output_image_path = os.path.join(output_dir, f'{custom_name}_{file_count}.png')
                        cv2.imwrite(output_image_path, background)
                        file_count += 1

                        # 更新进度条
                        progress_value = int((file_count / total_crops) * 100)
                        self.progress.emit(progress_value)


class DataMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('图像处理工具')
        self.setGeometry(100, 100, 850, 650)
        self.tab_widget = QTabWidget()
        self.setCentralWidget(self.tab_widget)

        self.video_frame_extractor = VideoFrameExtractor()
        self.tab_widget.addTab(self.video_frame_extractor, "视频帧提取")

        self.image_cropper = ImageCropper()
        self.tab_widget.addTab(self.image_cropper, "目标提取")

        self.image_background_extractor = BackgroundExtractor()
        self.tab_widget.addTab(self.image_background_extractor, "背景提取")


if __name__ == '__main__':
    app = QApplication(sys.argv)
    main_window = DataMainWindow()
    main_window.show()
    sys.exit(app.exec_())

#!/usr/bin/env python3
"""PyQt GUI for reviewing PF/SAM conflicts and rerunning SAM2 from a trusted box."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from urllib import request

from PyQt5.QtCore import QPointF, QRectF, Qt, QThread, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QImage, QPainter, QPen, QPixmap
from PyQt5.QtWidgets import (
    QApplication,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSlider,
    QSpinBox,
    QSplitter,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.generate_sam2_review_pack import select_sam_result
from tools.rerun_sam2_with_human_anchor import rerun_with_human_anchor


COLORS = {
    "pf": QColor(0, 210, 0),
    "sam": QColor(30, 90, 255),
    "draft": QColor(255, 150, 0),
}

STATUS_LABELS = {
    "reanchor_required": "需要重画锚点",
    "sam_candidate_preferred": "优先确认 SAM",
    "pending_anchor_review": "待确认锚点",
    "rerun_complete": "已重跑，待复查",
    "resolved": "已完成",
}


def normalized_pf_box(reference: dict, width: int, height: int):
    box = reference.get("box")
    if box is None:
        return None
    return [
        box[0] * width / 1000,
        box[1] * height / 1000,
        box[2] * width / 1000,
        box[3] * height / 1000,
    ]


def shape_box(box):
    if box is None:
        return None
    x1, y1, x2, y2 = (float(value) for value in box)
    return [min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)]


class BBoxCanvas(QWidget):
    box_changed = pyqtSignal(object)

    def __init__(self):
        super().__init__()
        self.setMinimumSize(720, 480)
        self.setMouseTracking(True)
        self._pixmap = QPixmap()
        self._image_size = None
        self._boxes = {"pf": None, "sam": None}
        self._draft_box = None
        self._drawing = False
        self._start = None
        self._display_rect = QRectF()

    def load(self, image_path: Path, pf_box, sam_box, draft_box=None):
        image = QImage(str(image_path))
        if image.isNull():
            raise ValueError(f"failed to load image: {image_path}")
        self._pixmap = QPixmap.fromImage(image)
        self._image_size = image.size()
        self._boxes = {"pf": shape_box(pf_box), "sam": shape_box(sam_box)}
        self._draft_box = shape_box(draft_box)
        self._drawing = False
        self.update()

    def image_size(self):
        return self._image_size

    def set_draft_box(self, box):
        self._draft_box = shape_box(box)
        self.box_changed.emit(self._draft_box)
        self.update()

    def draft_box(self):
        return self._draft_box

    def start_drawing(self):
        self._draft_box = None
        self._drawing = True
        self._start = None
        self.setCursor(Qt.CrossCursor)
        self.update()

    def _fit_rect(self):
        if self._pixmap.isNull():
            return QRectF()
        scale = min(
            self.width() / self._pixmap.width(),
            self.height() / self._pixmap.height(),
        )
        width = self._pixmap.width() * scale
        height = self._pixmap.height() * scale
        return QRectF((self.width() - width) / 2, (self.height() - height) / 2, width, height)

    def _to_image(self, point):
        rect = self._display_rect
        if rect.isEmpty() or not rect.contains(point):
            return None
        x = (point.x() - rect.left()) * self._pixmap.width() / rect.width()
        y = (point.y() - rect.top()) * self._pixmap.height() / rect.height()
        return QPointF(x, y)

    def _to_widget_rect(self, box):
        if box is None or self._display_rect.isEmpty():
            return QRectF()
        rect = self._display_rect
        sx = rect.width() / self._pixmap.width()
        sy = rect.height() / self._pixmap.height()
        return QRectF(
            rect.left() + box[0] * sx,
            rect.top() + box[1] * sy,
            (box[2] - box[0]) * sx,
            (box[3] - box[1]) * sy,
        )

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(32, 32, 32))
        if self._pixmap.isNull():
            return
        self._display_rect = self._fit_rect()
        painter.drawPixmap(self._display_rect, self._pixmap, QRectF(self._pixmap.rect()))
        for name in ("pf", "sam"):
            self._draw_box(painter, self._boxes[name], COLORS[name], name.upper())
        self._draw_box(painter, self._draft_box, COLORS["draft"], "SELECTED")

    def _draw_box(self, painter, box, color, label):
        if box is None:
            return
        rect = self._to_widget_rect(box)
        painter.setPen(QPen(color, 4))
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(rect)
        painter.setFont(QFont("Arial", 11, QFont.Bold))
        text_rect = QRectF(painter.fontMetrics().boundingRect(label)).adjusted(-4, -2, 4, 2)
        text_rect.moveBottomLeft(rect.topLeft())
        painter.fillRect(text_rect, color)
        painter.setPen(Qt.black)
        painter.drawText(text_rect, Qt.AlignCenter, label)

    def mousePressEvent(self, event):
        if not self._drawing or event.button() != Qt.LeftButton:
            return
        point = self._to_image(event.pos())
        if point is not None:
            self._start = point
            self._draft_box = [point.x(), point.y(), point.x(), point.y()]

    def mouseMoveEvent(self, event):
        if not self._drawing or self._start is None:
            return
        point = self._to_image(event.pos())
        if point is None:
            return
        self._draft_box = shape_box([self._start.x(), self._start.y(), point.x(), point.y()])
        self.update()

    def mouseReleaseEvent(self, event):
        if not self._drawing or self._start is None or event.button() != Qt.LeftButton:
            return
        point = self._to_image(event.pos())
        if point is not None:
            box = shape_box([self._start.x(), self._start.y(), point.x(), point.y()])
            if box[2] - box[0] >= 2 and box[3] - box[1] >= 2:
                self._draft_box = box
                self.box_changed.emit(box)
        self._drawing = False
        self._start = None
        self.unsetCursor()
        self.update()


class RerunWorker(QThread):
    succeeded = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, kwargs):
        super().__init__()
        self.kwargs = kwargs

    def run(self):
        try:
            output = rerun_with_human_anchor(**self.kwargs)
        except Exception as exc:  # Qt worker boundary: surface the complete failure to the operator.
            self.failed.emit(str(exc))
        else:
            self.succeeded.emit(str(output))


class ReviewWindow(QMainWindow):
    def __init__(self, args, queue):
        super().__init__()
        self.args = args
        self.queue = queue
        self.items = queue["items"]
        self.current_entry = None
        self.current_frame = None
        self.current_source = None
        self.references = []
        self.sam_frames = []
        self.frame_paths = []
        self.worker = None
        self.setWindowTitle("PF / SAM 包裹框复查")
        self.resize(1500, 900)
        self._build_ui()
        self._populate_queue()
        if self.items:
            self.queue_list.setCurrentRow(0)

    def _build_ui(self):
        splitter = QSplitter(Qt.Horizontal)
        self.queue_list = QListWidget()
        self.queue_list.setMinimumWidth(420)
        self.queue_list.setWordWrap(True)
        self.queue_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.queue_list.currentRowChanged.connect(self.load_queue_item)
        splitter.addWidget(self.queue_list)

        center = QWidget()
        center_layout = QVBoxLayout(center)
        navigation = QHBoxLayout()
        previous = QPushButton("上一帧")
        previous.clicked.connect(lambda: self.frame_spin.setValue(self.frame_spin.value() - 1))
        next_frame = QPushButton("下一帧")
        next_frame.clicked.connect(lambda: self.frame_spin.setValue(self.frame_spin.value() + 1))
        self.frame_spin = QSpinBox()
        self.frame_spin.valueChanged.connect(self._frame_changed)
        navigation.addWidget(previous)
        navigation.addWidget(QLabel("Frame"))
        navigation.addWidget(self.frame_spin)
        navigation.addWidget(next_frame)
        center_layout.addLayout(navigation)
        timeline = QHBoxLayout()
        timeline.addWidget(QLabel("1"))
        self.frame_slider = QSlider(Qt.Horizontal)
        self.frame_slider.setTracking(True)
        self.frame_slider.setPageStep(5)
        self.frame_slider.valueChanged.connect(self.frame_spin.setValue)
        timeline.addWidget(self.frame_slider, 1)
        self.frame_end_label = QLabel("1")
        timeline.addWidget(self.frame_end_label)
        center_layout.addLayout(timeline)
        self.canvas = BBoxCanvas()
        self.canvas.box_changed.connect(self._draft_changed)
        center_layout.addWidget(self.canvas, 1)
        self.legend = QLabel("绿色 PF ｜ 蓝色 SAM ｜ 橙色人工确认框")
        center_layout.addWidget(self.legend)
        splitter.addWidget(center)

        controls = QWidget()
        controls.setMinimumWidth(350)
        controls_layout = QVBoxLayout(controls)
        self.clip_info = QLabel()
        self.clip_info.setWordWrap(True)
        controls_layout.addWidget(self.clip_info)
        quick = QHBoxLayout()
        for label, key in (
            ("锚点", "anchor_frame"),
            ("最低 IoU", "lowest_iou_frame"),
            ("分歧起点", "divergence_start_frame"),
        ):
            button = QPushButton(label)
            button.clicked.connect(lambda _checked=False, name=key: self.jump_to(name))
            quick.addWidget(button)
        controls_layout.addLayout(quick)

        use_pf = QPushButton("采用当前 PF 框")
        use_pf.clicked.connect(lambda: self.use_box("pf"))
        use_sam = QPushButton("采用当前 SAM 框")
        use_sam.clicked.connect(lambda: self.use_box("sam"))
        draw = QPushButton("人工重画 bbox")
        draw.clicked.connect(self.start_drawing)
        controls_layout.addWidget(use_pf)
        controls_layout.addWidget(use_sam)
        controls_layout.addWidget(draw)

        form = QFormLayout()
        self.attribution = QComboBox()
        self.attribution.addItems(
            [
                "ambiguous", "pf_wrong_smooth", "pf_wrong_jump", "sam_wrong_anchor",
                "sam_identity_switch", "both_wrong",
            ]
        )
        self.error_content = QComboBox()
        self.error_content.addItems(
            [
                "other", "none", "parcel_pile", "robot_arm", "adjacent_parcel",
                "oversized_region", "conveyor_background", "mixed_target",
            ]
        )
        self.multi_parcel = QComboBox()
        self.multi_parcel.addItems(["unknown", "true", "false"])
        self.reviewer = QLineEdit(self.args.reviewed_by)
        self.box_value = QLineEdit()
        self.box_value.setReadOnly(True)
        form.addRow("归因", self.attribution)
        form.addRow("错误内容", self.error_content)
        form.addRow("多包裹", self.multi_parcel)
        form.addRow("标注人", self.reviewer)
        form.addRow("选中 bbox", self.box_value)
        controls_layout.addLayout(form)

        health = QPushButton("检查 SAM 服务")
        health.clicked.connect(self.check_service)
        self.rerun_button = QPushButton("以橙色框重新传播 SAM")
        self.rerun_button.clicked.connect(self.rerun_sam)
        controls_layout.addWidget(health)
        controls_layout.addWidget(self.rerun_button)
        controls_layout.addStretch(1)
        splitter.addWidget(controls)
        splitter.setStretchFactor(1, 1)
        self.setCentralWidget(splitter)
        self.setStatusBar(QStatusBar())

    def _populate_queue(self):
        self.queue_list.clear()
        for entry in self.items:
            label = STATUS_LABELS.get(entry["status"], entry["status"])
            item = QListWidgetItem(
                f"{label}\n{entry['episode']}/{entry['clip']}  "
                f"低IoU={entry['low_iou_ratio']:.1%}  帧={entry['review_candidate_count']}"
            )
            if entry["status"] == "reanchor_required":
                item.setBackground(QColor(255, 205, 205))
            elif entry["status"] == "sam_candidate_preferred":
                item.setBackground(QColor(205, 225, 255))
            elif entry["status"] == "rerun_complete":
                item.setBackground(QColor(220, 255, 220))
            self.queue_list.addItem(item)

    def load_queue_item(self, row):
        if row < 0 or row >= len(self.items):
            return
        self.current_entry = self.items[row]
        episode = self.current_entry["episode"]
        clip = self.current_entry["clip"]
        clip_dir = self.args.dataset_root / episode / clip
        self.frame_paths = sorted((clip_dir / "frames").glob("frame_*.jpg"))
        self.references = sorted(
            json.loads((clip_dir / "calibrated" / "results.json").read_text()),
            key=lambda item: int(item["frame_index"]),
        )
        result_dir = self.args.result_root / episode
        raw = json.loads(select_sam_result(result_dir, clip).read_text())
        self.sam_frames = raw["frames"]
        if not len(self.frame_paths) == len(self.references) == len(self.sam_frames):
            raise ValueError(f"frame count mismatch: {episode}/{clip}")
        self.frame_spin.blockSignals(True)
        self.frame_slider.blockSignals(True)
        self.frame_spin.setRange(1, len(self.frame_paths))
        self.frame_spin.setValue(self.current_entry["anchor_frame"])
        self.frame_slider.setRange(1, len(self.frame_paths))
        self.frame_slider.setValue(self.current_entry["anchor_frame"])
        self.frame_end_label.setText(str(len(self.frame_paths)))
        self.frame_spin.blockSignals(False)
        self.frame_slider.blockSignals(False)
        self._set_default_attribution()
        self.load_frame(self.frame_spin.value())

    def _frame_changed(self, frame_number):
        self.frame_slider.blockSignals(True)
        self.frame_slider.setValue(frame_number)
        self.frame_slider.blockSignals(False)
        self.load_frame(frame_number)

    def _set_default_attribution(self):
        status = self.current_entry["status"]
        value = "sam_wrong_anchor" if status == "reanchor_required" else (
            "pf_wrong_smooth" if status == "sam_candidate_preferred" else "ambiguous"
        )
        self.attribution.setCurrentText(value)

    def load_frame(self, frame_number):
        if self.current_entry is None:
            return
        self.current_frame = frame_number
        image = QImage(str(self.frame_paths[frame_number - 1]))
        if image.isNull():
            raise ValueError(f"failed to load {self.frame_paths[frame_number - 1]}")
        pf_box = normalized_pf_box(self.references[frame_number - 1], image.width(), image.height())
        sam_box = self.sam_frames[frame_number - 1].get("box_xyxy_pixels")
        self.current_source = None
        self.canvas.load(self.frame_paths[frame_number - 1], pf_box, sam_box)
        self.box_value.clear()
        entry = self.current_entry
        self.clip_info.setText(
            f"<b>{entry['episode']}/{entry['clip']}</b><br>"
            f"状态：{STATUS_LABELS.get(entry['status'], entry['status'])}<br>"
            f"候选帧：{entry['review_candidate_count']}；低 IoU 比例：{entry['low_iou_ratio']:.1%}<br>"
            f"最长区间：{entry['longest_low_iou_run']}；面积比：{entry['area_ratio_median']:.2f}<br>"
            f"备注：{entry.get('notes') or '无'}"
        )
        self.statusBar().showMessage(f"frame {frame_number}/{len(self.frame_paths)}")

    def jump_to(self, key):
        if self.current_entry and self.current_entry.get(key):
            self.frame_spin.setValue(int(self.current_entry[key]))

    def use_box(self, source):
        box = self.canvas._boxes[source]
        if box is None:
            QMessageBox.warning(self, "没有 bbox", f"当前帧没有 {source.upper()} bbox")
            return
        self.current_source = source
        self.canvas.set_draft_box(box)

    def start_drawing(self):
        self.current_source = "human"
        self.canvas.start_drawing()
        self.statusBar().showMessage("在图像上按住左键拖动，画一个紧贴目标包裹的框")

    def _draft_changed(self, box):
        if box is None:
            self.box_value.clear()
            return
        self.box_value.setText(", ".join(f"{value:.1f}" for value in box))

    def check_service(self):
        try:
            with request.urlopen(f"{self.args.sam2_url.rstrip('/')}/healthz", timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            QMessageBox.critical(self, "SAM 服务不可用", str(exc))
            return
        QMessageBox.information(
            self,
            "SAM 服务正常",
            f"model={payload.get('model')}\ndevice={payload.get('device')}\nstatus={payload.get('status')}",
        )

    def rerun_sam(self):
        box = self.canvas.draft_box()
        if box is None:
            QMessageBox.warning(self, "未选择 bbox", "先采用 PF/SAM 框，或人工重画一个框。")
            return
        reviewer = self.reviewer.text().strip()
        if not reviewer:
            QMessageBox.warning(self, "缺少标注人", "请填写标注人。")
            return
        episode = self.current_entry["episode"]
        clip = self.current_entry["clip"]
        result_dir = self.args.result_root / episode
        existing = result_dir / f"{clip}_sam2.1_tiny_human_raw.json"
        force = False
        if existing.exists():
            answer = QMessageBox.question(
                self, "覆盖已有结果", f"{existing.name} 已存在，是否覆盖？"
            )
            if answer != QMessageBox.Yes:
                return
            force = True
        service_frames = None
        if self.args.service_dataset_root is not None:
            service_frames = self.args.service_dataset_root / episode / clip / "frames"
        original_anchor = self.current_entry["anchor_frame"]
        review_result = (
            "anchor_confirmed"
            if self.current_source == "pf" and self.current_frame == original_anchor
            else "anchor_corrected"
        )
        kwargs = {
            "clip_dir": self.args.dataset_root / episode / clip,
            "result_dir": result_dir,
            "anchor_frame": self.current_frame,
            "box_xyxy_pixels": box,
            "sam_url": self.args.sam2_url,
            "timeout": self.args.timeout,
            "force": force,
            "anchor_review_result": review_result,
            "attribution": self.attribution.currentText(),
            "error_content": self.error_content.currentText(),
            "multi_parcel": self.multi_parcel.currentText(),
            "reviewed_by": reviewer,
            "service_frames_dir": service_frames,
        }
        self.rerun_button.setEnabled(False)
        self.statusBar().showMessage("SAM 正在重新传播，请等待…")
        self.worker = RerunWorker(kwargs)
        self.worker.succeeded.connect(self._rerun_succeeded)
        self.worker.failed.connect(self._rerun_failed)
        self.worker.start()

    def _rerun_succeeded(self, output):
        self.rerun_button.setEnabled(True)
        self.current_entry["status"] = "rerun_complete"
        self.current_entry["recommended_action"] = "review_human_anchor_propagation"
        self.current_entry["last_rerun_result"] = output
        self.current_entry["last_rerun_at"] = datetime.now(timezone.utc).isoformat()
        self._write_queue()
        row = self.queue_list.currentRow()
        self._populate_queue()
        self.queue_list.setCurrentRow(row)
        QMessageBox.information(self, "SAM 重跑完成", output)

    def _rerun_failed(self, message):
        self.rerun_button.setEnabled(True)
        self.statusBar().showMessage("SAM 重跑失败")
        QMessageBox.critical(self, "SAM 重跑失败", message)

    def _write_queue(self):
        counts = {status: 0 for status in STATUS_LABELS}
        for entry in self.items:
            counts[entry["status"]] = counts.get(entry["status"], 0) + 1
        self.queue["summary"]["status_counts"] = counts
        temporary = self.args.queue.with_suffix(self.args.queue.suffix + ".tmp")
        temporary.write_text(
            json.dumps(self.queue, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        temporary.replace(self.args.queue)


def validate_inputs(args, queue):
    if not args.dataset_root.is_dir():
        raise ValueError(f"dataset root does not exist: {args.dataset_root}")
    if not args.result_root.is_dir():
        raise ValueError(f"result root does not exist: {args.result_root}")
    if not args.review_root.is_dir():
        raise ValueError(f"review root does not exist: {args.review_root}")
    missing = []
    for item in queue["items"]:
        clip_dir = args.dataset_root / item["episode"] / item["clip"]
        result_dir = args.result_root / item["episode"]
        if not clip_dir.is_dir() or not result_dir.is_dir():
            missing.append(item["key"])
    if missing:
        raise ValueError(f"missing dataset/result directories for: {', '.join(missing)}")


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--result-root", type=Path, required=True)
    parser.add_argument("--review-root", type=Path, required=True)
    parser.add_argument("--queue", type=Path, required=True)
    parser.add_argument("--service-dataset-root", type=Path)
    parser.add_argument("--sam2-url", default="http://127.0.0.1:5001")
    parser.add_argument("--reviewed-by", default="zhangyurui")
    parser.add_argument("--timeout", type=float, default=600.0)
    parser.add_argument("--check", action="store_true", help="validate inputs and exit without opening Qt")
    return parser.parse_args()


def main():
    args = parse_args()
    queue = json.loads(args.queue.read_text(encoding="utf-8"))
    validate_inputs(args, queue)
    if args.check:
        print(
            json.dumps(
                {
                    "status": "ok",
                    "queue_items": len(queue["items"]),
                    "dataset_root": str(args.dataset_root),
                    "result_root": str(args.result_root),
                    "sam2_url": args.sam2_url,
                },
                ensure_ascii=False,
            )
        )
        return
    application = QApplication(sys.argv)
    window = ReviewWindow(args, queue)
    window.show()
    sys.exit(application.exec_())


if __name__ == "__main__":
    main()

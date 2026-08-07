"""Validate PerceptFlow boxes against a track anchored near the end of a clip."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any
import json

import cv2
import numpy as np


NormalizedBox = Sequence[float]
TrackerFactory = Callable[[], Any]


def box_iou(left: Sequence[float], right: Sequence[float]) -> float:
    """Return IoU for two ``[x1, y1, x2, y2]`` boxes."""
    intersection_width = max(0.0, min(left[2], right[2]) - max(left[0], right[0]))
    intersection_height = max(0.0, min(left[3], right[3]) - max(left[1], right[1]))
    intersection = intersection_width * intersection_height
    left_area = max(0.0, left[2] - left[0]) * max(0.0, left[3] - left[1])
    right_area = max(0.0, right[2] - right[0]) * max(0.0, right[3] - right[1])
    union = left_area + right_area - intersection
    return 0.0 if union <= 0 else intersection / union


def validate_boxes_from_anchor(
    images: Sequence[np.ndarray],
    proposed_boxes: Sequence[NormalizedBox | None],
    *,
    tracker_factory: TrackerFactory,
    anchor_fraction: float = 0.75,
    iou_threshold: float = 0.5,
) -> dict[str, Any]:
    """Track backward and forward from one trusted anchor and flag disagreements.

    PerceptFlow boxes use normalized ``[x1, y1, x2, y2]`` coordinates in
    ``[0, 1000]``. OpenCV trackers use pixel ``[x, y, width, height]`` boxes.
    The anchor box is treated as trusted and is never evaluated independently.
    """
    if not images:
        raise ValueError("images cannot be empty")
    if len(images) != len(proposed_boxes):
        raise ValueError("images and proposed_boxes must have the same length")
    if not 0 <= anchor_fraction <= 1:
        raise ValueError("anchor_fraction must be between 0 and 1")
    if not 0 <= iou_threshold <= 1:
        raise ValueError("iou_threshold must be between 0 and 1")

    anchor_index = int((len(images) - 1) * anchor_fraction)
    anchor_box = proposed_boxes[anchor_index]
    if anchor_box is None:
        raise ValueError("the selected anchor frame has no proposed box")
    _validate_normalized_box(anchor_box)

    height, width = images[anchor_index].shape[:2]
    anchor_xywh = _normalized_xyxy_to_pixel_xywh(anchor_box, width, height)
    tracked_by_index: dict[int, tuple[float, float, float, float] | None] = {
        anchor_index: _pixel_xywh_to_xyxy(anchor_xywh)
    }
    direction_by_index = {anchor_index: "anchor"}

    _track_branch(
        images,
        anchor_index,
        range(anchor_index - 1, -1, -1),
        anchor_xywh,
        tracker_factory,
        tracked_by_index,
        direction_by_index,
        direction="backward",
    )
    _track_branch(
        images,
        anchor_index,
        range(anchor_index + 1, len(images)),
        anchor_xywh,
        tracker_factory,
        tracked_by_index,
        direction_by_index,
        direction="forward_tail",
    )

    frames = []
    review_frames = []
    for index, (image, proposed_box) in enumerate(zip(images, proposed_boxes)):
        image_height, image_width = image.shape[:2]
        tracked_pixel_box = tracked_by_index.get(index)
        tracked_normalized_box = (
            None
            if tracked_pixel_box is None
            else _pixel_xyxy_to_normalized(tracked_pixel_box, image_width, image_height)
        )
        if index == anchor_index:
            status = "anchor"
            iou = 1.0
        elif proposed_box is None:
            status = "review"
            iou = None
        elif tracked_pixel_box is None:
            status = "tracking_failed"
            iou = None
        else:
            _validate_normalized_box(proposed_box)
            proposed_pixel_box = _normalized_xyxy_to_pixel_xyxy(
                proposed_box, image_width, image_height
            )
            iou = box_iou(proposed_pixel_box, tracked_pixel_box)
            status = "pass" if iou >= iou_threshold else "review"

        frame_result = {
            "frame_index": index + 1,
            "direction": direction_by_index.get(index),
            "status": status,
            "iou": None if iou is None else round(iou, 6),
            "proposed_box": None if proposed_box is None else list(proposed_box),
            "tracker_box": tracked_normalized_box,
        }
        frames.append(frame_result)
        if status in {"review", "tracking_failed"}:
            review_frames.append(index + 1)

    return {
        "anchor_frame": anchor_index + 1,
        "anchor_fraction": anchor_fraction,
        "iou_threshold": iou_threshold,
        "total_frames": len(images),
        "review_frames": review_frames,
        "review_count": len(review_frames),
        "frames": frames,
    }


def validate_perceptflow_clip(
    frames_dir: str | Path,
    results_path: str | Path,
    *,
    tracker_name: str = "CSRT",
    anchor_fraction: float = 0.75,
    iou_threshold: float = 0.5,
) -> dict[str, Any]:
    """Load one PerceptFlow clip and return a reverse-tracker review report."""
    frame_paths = sorted(Path(frames_dir).glob("frame_*.jpg"))
    if not frame_paths:
        raise ValueError(f"no frame_*.jpg files found in {frames_dir}")
    images = [_read_image(path) for path in frame_paths]

    payload = json.loads(Path(results_path).read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("PerceptFlow results must be a JSON array")
    ordered_results = sorted(payload, key=lambda item: int(item["frame_index"]))
    expected_indices = list(range(1, len(frame_paths) + 1))
    actual_indices = [int(item["frame_index"]) for item in ordered_results]
    if actual_indices != expected_indices:
        raise ValueError("PerceptFlow frame_index values must be consecutive and match the frames")

    report = validate_boxes_from_anchor(
        images,
        [item.get("box") for item in ordered_results],
        tracker_factory=lambda: _create_tracker(tracker_name),
        anchor_fraction=anchor_fraction,
        iou_threshold=iou_threshold,
    )
    report.update(
        {
            "tracker": tracker_name.upper(),
            "frames_dir": str(Path(frames_dir)),
            "results_path": str(Path(results_path)),
            "coordinate_space": "normalized_xyxy_0_1000",
        }
    )
    return report


def _track_branch(
    images: Sequence[np.ndarray],
    anchor_index: int,
    indices: range,
    anchor_xywh: tuple[float, float, float, float],
    tracker_factory: TrackerFactory,
    tracked_by_index: dict[int, tuple[float, float, float, float] | None],
    direction_by_index: dict[int, str],
    *,
    direction: str,
) -> None:
    tracker = tracker_factory()
    initialized = tracker.init(images[anchor_index], anchor_xywh)
    if initialized is False:
        raise RuntimeError(f"tracker initialization failed for {direction} branch")
    failed = False
    for index in indices:
        direction_by_index[index] = direction
        if failed:
            tracked_by_index[index] = None
            continue
        success, tracked_xywh = tracker.update(images[index])
        if not success:
            tracked_by_index[index] = None
            failed = True
            continue
        tracked_by_index[index] = _pixel_xywh_to_xyxy(tracked_xywh)


def _create_tracker(tracker_name: str) -> Any:
    normalized_name = tracker_name.strip().upper()
    legacy = getattr(cv2, "legacy", None)
    factory = getattr(legacy, f"Tracker{normalized_name}_create", None) if legacy else None
    if factory is None:
        raise ValueError(f"OpenCV tracker is unavailable: {tracker_name}")
    return factory()


def _read_image(path: Path) -> np.ndarray:
    image = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"failed to read frame: {path}")
    return image


def _validate_normalized_box(box: NormalizedBox) -> None:
    if len(box) != 4:
        raise ValueError("box must contain four coordinates")
    x1, y1, x2, y2 = (float(value) for value in box)
    if not (0 <= x1 < x2 <= 1000 and 0 <= y1 < y2 <= 1000):
        raise ValueError(f"invalid normalized xyxy box: {box}")


def _normalized_xyxy_to_pixel_xywh(
    box: NormalizedBox, width: int, height: int
) -> tuple[float, float, float, float]:
    x1, y1, x2, y2 = (float(value) for value in box)
    return (
        x1 * width / 1000,
        y1 * height / 1000,
        (x2 - x1) * width / 1000,
        (y2 - y1) * height / 1000,
    )


def _normalized_xyxy_to_pixel_xyxy(
    box: NormalizedBox, width: int, height: int
) -> tuple[float, float, float, float]:
    x1, y1, x2, y2 = (float(value) for value in box)
    return x1 * width / 1000, y1 * height / 1000, x2 * width / 1000, y2 * height / 1000


def _pixel_xywh_to_xyxy(box: Sequence[float]) -> tuple[float, float, float, float]:
    x, y, width, height = (float(value) for value in box)
    return x, y, x + width, y + height


def _pixel_xyxy_to_normalized(
    box: Sequence[float], width: int, height: int
) -> list[float]:
    return [
        round(float(box[0]) * 1000 / width, 3),
        round(float(box[1]) * 1000 / height, 3),
        round(float(box[2]) * 1000 / width, 3),
        round(float(box[3]) * 1000 / height, 3),
    ]

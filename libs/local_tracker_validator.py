"""Check PerceptFlow boxes with freshly initialized adjacent-frame trackers."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence
import json
import statistics

import numpy as np

from libs.reverse_tracker_validator import (
    NormalizedBox,
    TrackerFactory,
    _create_tracker,
    _normalized_xyxy_to_pixel_xywh,
    _normalized_xyxy_to_pixel_xyxy,
    _pixel_xywh_to_xyxy,
    _pixel_xyxy_to_normalized,
    _read_image,
    _validate_normalized_box,
    box_iou,
)


def validate_adjacent_boxes(
    images: Sequence[np.ndarray],
    proposed_boxes: Sequence[NormalizedBox | None],
    *,
    tracker_factory: TrackerFactory,
    iou_threshold: float = 0.5,
) -> dict[str, Any]:
    """Reinitialize on every box and check both directions of adjacent pairs."""
    if not images:
        raise ValueError("images cannot be empty")
    if len(images) != len(proposed_boxes):
        raise ValueError("images and proposed_boxes must have the same length")

    scores: list[list[float]] = [[] for _ in images]
    failures = [0 for _ in images]
    incoming_boxes: list[list[list[float]]] = [[] for _ in images]

    for left_index in range(len(images) - 1):
        right_index = left_index + 1
        for source_index, target_index in (
            (left_index, right_index),
            (right_index, left_index),
        ):
            source_box = proposed_boxes[source_index]
            target_box = proposed_boxes[target_index]
            if source_box is None or target_box is None:
                failures[source_index] += 1
                failures[target_index] += 1
                continue

            tracked_box = _track_once(
                images[source_index],
                images[target_index],
                source_box,
                tracker_factory,
            )
            if tracked_box is None:
                failures[source_index] += 1
                failures[target_index] += 1
                continue

            target_height, target_width = images[target_index].shape[:2]
            proposed_pixel_box = _normalized_xyxy_to_pixel_xyxy(
                target_box, target_width, target_height
            )
            iou = box_iou(tracked_box, proposed_pixel_box)
            scores[source_index].append(iou)
            scores[target_index].append(iou)
            incoming_boxes[target_index].append(
                _pixel_xyxy_to_normalized(tracked_box, target_width, target_height)
            )

    frames = []
    supported_count = 0
    for index, proposed_box in enumerate(proposed_boxes):
        local_iou = statistics.median(scores[index]) if scores[index] else None
        if local_iou is None:
            status = "tracking_failed"
        elif local_iou >= iou_threshold:
            status = "pass"
            supported_count += 1
        else:
            status = "review"
        tracker_box = _median_box(incoming_boxes[index])
        frames.append(
            {
                "frame_index": index + 1,
                "direction": "adjacent_bidirectional",
                "status": status,
                "iou": None if local_iou is None else round(local_iou, 6),
                "proposed_box": None if proposed_box is None else list(proposed_box),
                "tracker_box": tracker_box,
                "evidence_count": len(scores[index]),
                "tracking_failure_count": failures[index],
            }
        )

    return {
        "anchor_frame": "every_frame",
        "method": "fresh_tracker_for_each_adjacent_pair",
        "iou_threshold": iou_threshold,
        "total_frames": len(images),
        "supported_count": supported_count,
        "disagreement_count": len(images) - supported_count,
        "frames": frames,
        "decision_note": "disagreement is weak evidence and does not prove the PerceptFlow box is wrong",
    }


def validate_perceptflow_clip_locally(
    frames_dir: str | Path,
    results_path: str | Path,
    *,
    tracker_name: str = "CSRT",
    iou_threshold: float = 0.5,
) -> dict[str, Any]:
    frame_paths = sorted(Path(frames_dir).glob("frame_*.jpg"))
    if not frame_paths:
        raise ValueError(f"no frame_*.jpg files found in {frames_dir}")
    images = [_read_image(path) for path in frame_paths]
    payload = json.loads(Path(results_path).read_text(encoding="utf-8"))
    ordered_results = sorted(payload, key=lambda item: int(item["frame_index"]))
    expected_indices = list(range(1, len(frame_paths) + 1))
    if [int(item["frame_index"]) for item in ordered_results] != expected_indices:
        raise ValueError("PerceptFlow frame_index values must be consecutive and match the frames")

    report = validate_adjacent_boxes(
        images,
        [item.get("box") for item in ordered_results],
        tracker_factory=lambda: _create_tracker(tracker_name),
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


def _track_once(
    source_image: np.ndarray,
    target_image: np.ndarray,
    source_box: NormalizedBox,
    tracker_factory: TrackerFactory,
):
    _validate_normalized_box(source_box)
    height, width = source_image.shape[:2]
    tracker = tracker_factory()
    initialized = tracker.init(
        source_image,
        _normalized_xyxy_to_pixel_xywh(source_box, width, height),
    )
    if initialized is False:
        return None
    success, tracked_xywh = tracker.update(target_image)
    return _pixel_xywh_to_xyxy(tracked_xywh) if success else None


def _median_box(boxes: Sequence[Sequence[float]]) -> list[float] | None:
    if not boxes:
        return None
    return [round(statistics.median(box[index] for box in boxes), 3) for index in range(4)]

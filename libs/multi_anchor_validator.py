"""Detect PerceptFlow drift with cycle-consistent multi-anchor tracks."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence
import json
import statistics

import numpy as np

from libs.local_tracker_validator import validate_adjacent_boxes
from libs.reverse_tracker_validator import (
    NormalizedBox,
    TrackerFactory,
    _create_tracker,
    _normalized_xyxy_to_pixel_xywh,
    _normalized_xyxy_to_pixel_xyxy,
    _pixel_xywh_to_xyxy,
    _pixel_xyxy_to_normalized,
    _read_image,
    box_iou,
)


def validate_with_multi_anchors(
    images: Sequence[np.ndarray],
    proposed_boxes: Sequence[NormalizedBox],
    *,
    tracker_factory: TrackerFactory,
    anchor_count: int = 3,
    cycle_iou_threshold: float = 0.5,
    consensus_iou_threshold: float = 0.5,
    deviation_iou_threshold: float = 0.5,
) -> dict[str, Any]:
    """Return strong drift candidates only when independent tracks are reliable."""
    if len(images) != len(proposed_boxes) or not images:
        raise ValueError("images and proposed_boxes must have the same non-zero length")
    if anchor_count < 2:
        raise ValueError("anchor_count must be at least two")

    local_report = validate_adjacent_boxes(
        images,
        proposed_boxes,
        tracker_factory=tracker_factory,
        iou_threshold=deviation_iou_threshold,
    )
    anchor_indices = select_stable_anchors(local_report["frames"], anchor_count)
    anchor_cycle_scores = _measure_anchor_cycles(
        images,
        proposed_boxes,
        anchor_indices,
        tracker_factory,
    )
    anchor_tracks = {
        anchor_index: _track_all_from_anchor(
            images,
            proposed_boxes[anchor_index],
            anchor_index,
            tracker_factory,
        )
        for anchor_index in anchor_indices
    }
    frames = []
    suspected_frames = []

    for target_index, proposed_box in enumerate(proposed_boxes):
        evidence = []
        for anchor_index in anchor_indices:
            if anchor_index == target_index:
                continue
            cycle_iou = anchor_cycle_scores[anchor_index]
            predicted_box = anchor_tracks[anchor_index].get(target_index)
            reliable = (
                predicted_box is not None
                and cycle_iou is not None
                and cycle_iou >= cycle_iou_threshold
            )
            evidence.append(
                _evidence(
                    anchor_index,
                    predicted_box,
                    cycle_iou,
                    reliable,
                    "ok" if reliable else "anchor_cycle_or_track_unreliable",
                )
            )

        reliable = [item for item in evidence if item["reliable"]]
        predicted_boxes = [item["predicted_box"] for item in reliable]
        consensus_box = _median_box(predicted_boxes)
        consensus_iou = _median_pairwise_iou(predicted_boxes)
        perceptflow_iou = (
            None if consensus_box is None else box_iou(proposed_box, consensus_box)
        )
        status = classify_evidence(
            len(reliable),
            consensus_iou,
            perceptflow_iou,
            consensus_iou_threshold=consensus_iou_threshold,
            deviation_iou_threshold=deviation_iou_threshold,
        )
        if status == "suspected_perceptflow_drift":
            suspected_frames.append(target_index + 1)

        frames.append(
            {
                "frame_index": target_index + 1,
                "status": status,
                "perceptflow_box": list(proposed_box),
                "consensus_box": consensus_box,
                "perceptflow_consensus_iou": _round(perceptflow_iou),
                "tracker_consensus_iou": _round(consensus_iou),
                "reliable_anchor_count": len(reliable),
                "local_iou": local_report["frames"][target_index]["iou"],
                "anchor_evidence": evidence,
            }
        )

    return {
        "method": "multi_anchor_cycle_consistency",
        "total_frames": len(images),
        "anchor_frames": [index + 1 for index in anchor_indices],
        "anchor_cycle_ious": {
            str(index + 1): _round(anchor_cycle_scores[index]) for index in anchor_indices
        },
        "cycle_iou_threshold": cycle_iou_threshold,
        "consensus_iou_threshold": consensus_iou_threshold,
        "deviation_iou_threshold": deviation_iou_threshold,
        "suspected_frames": suspected_frames,
        "suspected_count": len(suspected_frames),
        "supported_count": sum(frame["status"] == "supported" for frame in frames),
        "tracker_unreliable_count": sum(
            frame["status"] == "tracker_unreliable" for frame in frames
        ),
        "frames": frames,
    }


def select_stable_anchors(frame_results: Sequence[dict[str, Any]], anchor_count: int) -> list[int]:
    """Select the strongest local-consistency frame from each temporal segment."""
    if anchor_count > len(frame_results):
        raise ValueError("anchor_count cannot exceed frame count")
    anchors = []
    for segment in range(anchor_count):
        start = len(frame_results) * segment // anchor_count
        end = len(frame_results) * (segment + 1) // anchor_count
        best = max(
            range(start, end),
            key=lambda index: (
                -1.0 if frame_results[index]["iou"] is None else frame_results[index]["iou"],
                -abs(index - (start + end - 1) / 2),
            ),
        )
        anchors.append(best)
    return anchors


def classify_evidence(
    reliable_anchor_count: int,
    consensus_iou: float | None,
    perceptflow_iou: float | None,
    *,
    consensus_iou_threshold: float,
    deviation_iou_threshold: float,
) -> str:
    if (
        reliable_anchor_count < 2
        or consensus_iou is None
        or consensus_iou < consensus_iou_threshold
    ):
        return "tracker_unreliable"
    if perceptflow_iou is not None and perceptflow_iou < deviation_iou_threshold:
        return "suspected_perceptflow_drift"
    return "supported"


def validate_perceptflow_clip_with_multi_anchors(
    frames_dir: str | Path,
    results_path: str | Path,
    *,
    tracker_name: str = "CSRT",
    anchor_count: int = 3,
    cycle_iou_threshold: float = 0.5,
    consensus_iou_threshold: float = 0.5,
    deviation_iou_threshold: float = 0.5,
) -> dict[str, Any]:
    frame_paths = sorted(Path(frames_dir).glob("frame_*.jpg"))
    images = [_read_image(path) for path in frame_paths]
    payload = json.loads(Path(results_path).read_text(encoding="utf-8"))
    ordered = sorted(payload, key=lambda item: int(item["frame_index"]))
    if [int(item["frame_index"]) for item in ordered] != list(range(1, len(images) + 1)):
        raise ValueError("PerceptFlow frame indices must match clip frames")

    report = validate_with_multi_anchors(
        images,
        [item["box"] for item in ordered],
        tracker_factory=lambda: _create_tracker(tracker_name),
        anchor_count=anchor_count,
        cycle_iou_threshold=cycle_iou_threshold,
        consensus_iou_threshold=consensus_iou_threshold,
        deviation_iou_threshold=deviation_iou_threshold,
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


def _measure_anchor_cycles(
    images,
    proposed_boxes,
    anchor_indices,
    tracker_factory,
):
    values = {anchor_index: [] for anchor_index in anchor_indices}
    for anchor_index in anchor_indices:
        anchor_height, anchor_width = images[anchor_index].shape[:2]
        anchor_xywh = _normalized_xyxy_to_pixel_xywh(
            proposed_boxes[anchor_index], anchor_width, anchor_height
        )
        anchor_pixel_box = _normalized_xyxy_to_pixel_xyxy(
            proposed_boxes[anchor_index], anchor_width, anchor_height
        )
        for target_index in anchor_indices:
            if target_index == anchor_index:
                continue
            predicted = _track_path(
                images, anchor_index, target_index, anchor_xywh, tracker_factory
            )
            if predicted is None:
                continue
            target_height, target_width = images[target_index].shape[:2]
            clipped = _clip_xyxy(predicted, target_width, target_height)
            if clipped is None:
                continue
            returned = _track_path(
                images,
                target_index,
                anchor_index,
                _xyxy_to_xywh(clipped),
                tracker_factory,
            )
            if returned is not None:
                values[anchor_index].append(box_iou(anchor_pixel_box, returned))
    return {
        anchor_index: statistics.median(scores) if scores else None
        for anchor_index, scores in values.items()
    }


def _track_all_from_anchor(
    images,
    anchor_box,
    anchor_index,
    tracker_factory,
):
    anchor_height, anchor_width = images[anchor_index].shape[:2]
    anchor_xywh = _normalized_xyxy_to_pixel_xywh(
        anchor_box, anchor_width, anchor_height
    )
    predictions = {anchor_index: list(anchor_box)}
    for indices in (
        range(anchor_index + 1, len(images)),
        range(anchor_index - 1, -1, -1),
    ):
        tracker = tracker_factory()
        initialized = tracker.init(images[anchor_index], anchor_xywh)
        if initialized is False:
            continue
        for index in indices:
            success, tracked_xywh = tracker.update(images[index])
            if not success:
                break
            height, width = images[index].shape[:2]
            clipped = _clip_xyxy(_pixel_xywh_to_xyxy(tracked_xywh), width, height)
            if clipped is None:
                break
            predictions[index] = _pixel_xyxy_to_normalized(clipped, width, height)
    return predictions


def _track_path(images, source_index, target_index, initial_xywh, tracker_factory):
    tracker = tracker_factory()
    initialized = tracker.init(images[source_index], initial_xywh)
    if initialized is False:
        return None
    step = 1 if target_index > source_index else -1
    tracked_xywh = initial_xywh
    for index in range(source_index + step, target_index + step, step):
        success, tracked_xywh = tracker.update(images[index])
        if not success:
            return None
    return _pixel_xywh_to_xyxy(tracked_xywh)


def _median_pairwise_iou(boxes: Sequence[Sequence[float]]) -> float | None:
    values = [
        box_iou(boxes[left], boxes[right])
        for left in range(len(boxes))
        for right in range(left + 1, len(boxes))
    ]
    return statistics.median(values) if values else None


def _median_box(boxes: Sequence[Sequence[float]]) -> list[float] | None:
    if not boxes:
        return None
    return [round(statistics.median(box[index] for box in boxes), 3) for index in range(4)]


def _clip_xyxy(box, width, height):
    x1 = max(0.0, min(float(width - 1), float(box[0])))
    y1 = max(0.0, min(float(height - 1), float(box[1])))
    x2 = max(0.0, min(float(width), float(box[2])))
    y2 = max(0.0, min(float(height), float(box[3])))
    return None if x2 <= x1 or y2 <= y1 else (x1, y1, x2, y2)


def _xyxy_to_xywh(box):
    return box[0], box[1], box[2] - box[0], box[3] - box[1]


def _evidence(anchor_index, predicted_box, cycle_iou, reliable, reason):
    return {
        "anchor_frame": anchor_index + 1,
        "predicted_box": predicted_box,
        "cycle_iou": _round(cycle_iou),
        "reliable": reliable,
        "reason": reason,
    }


def _round(value):
    return None if value is None else round(value, 6)

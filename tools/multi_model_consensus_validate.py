#!/usr/bin/env python3
"""Find suspicious PerceptFlow boxes without replacing them.

The experiment combines short multi-anchor tracks from two remote models with
fresh adjacent-frame CSRT checks. Tracker outputs are evidence only; the source
PerceptFlow boxes are never modified.
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import time

import cv2

from remote_rest_reverse_validate import (
    MODELS,
    RestTracker,
    box_iou,
    load_clip,
    normalized_to_pixels,
    normalized_xyxy_to_pixel_xywh,
    pixel_xywh_to_normalized_xyxy,
)


def select_medoid(predictions):
    """Return the most central box and mean pairwise IoU."""
    boxes = [item["box"] for item in predictions]
    if not boxes:
        return None, None
    if len(boxes) == 1:
        return boxes[0], None

    pairwise = []
    scores = []
    for left_index, left in enumerate(boxes):
        values = []
        for right_index, right in enumerate(boxes):
            if left_index == right_index:
                continue
            value = box_iou(left, right)
            values.append(value)
            if left_index < right_index:
                pairwise.append(value)
        scores.append(sum(values) / len(values))
    best_index = max(range(len(scores)), key=scores.__getitem__)
    return boxes[best_index], sum(pairwise) / len(pairwise)


def classify_frame(
    *,
    model_reliable,
    remote_model_iou,
    perceptflow_ious,
    local_reliable,
    local_iou,
    remote_consensus_threshold,
    remote_conflict_threshold,
    perceptflow_support_threshold,
    local_support_threshold,
):
    if not model_reliable:
        return "tracker_unreliable"
    if remote_model_iou < remote_consensus_threshold:
        return "remote_model_disagreement"

    remote_conflict = all(value < remote_conflict_threshold for value in perceptflow_ious)
    if remote_conflict:
        if local_reliable and local_iou < local_support_threshold:
            return "perceptflow_suspect"
        if local_iou is not None and local_iou < local_support_threshold:
            return "review_candidate"
        return "remote_conflict_only"

    if all(value >= perceptflow_support_threshold for value in perceptflow_ious):
        return "perceptflow_supported"
    return "mixed_evidence"


def collect_remote_predictions(
    images,
    boxes,
    *,
    base_url,
    model,
    anchor_stride,
    window,
    timeout,
):
    anchors = sorted(set(range(0, len(images), anchor_stride)) | {len(images) - 1})
    predictions = {index: [] for index in range(len(images))}
    failures = []
    for anchor_index in anchors:
        anchor_height, anchor_width = images[anchor_index].shape[:2]
        anchor_box = normalized_xyxy_to_pixel_xywh(
            boxes[anchor_index], anchor_width, anchor_height
        )
        for direction in (-1, 1):
            target_indices = list(
                range(
                    anchor_index + direction,
                    anchor_index + direction * (window + 1),
                    direction,
                )
            )
            target_indices = [
                index for index in target_indices if 0 <= index < len(images)
            ]
            if not target_indices:
                continue

            tracker = RestTracker(base_url, *MODELS[model], timeout)
            try:
                tracker.initialize(images[anchor_index], anchor_box)
                for target_index in target_indices:
                    started = time.perf_counter()
                    tracked_xywh = tracker.track(images[target_index])
                    elapsed = time.perf_counter() - started
                    height, width = images[target_index].shape[:2]
                    predictions[target_index].append(
                        {
                            "anchor_frame": anchor_index + 1,
                            "direction": "forward" if direction > 0 else "backward",
                            "distance_frames": abs(target_index - anchor_index),
                            "box": pixel_xywh_to_normalized_xyxy(
                                tracked_xywh, width, height
                            ),
                            "elapsed_seconds": round(elapsed, 6),
                        }
                    )
            except Exception as exc:
                failures.append(
                    {
                        "model": model,
                        "anchor_frame": anchor_index + 1,
                        "direction": direction,
                        "error": str(exc),
                    }
                )
    return predictions, failures


def load_local_continuity(report_path, expected_frames):
    payload = json.loads(report_path.read_text())
    frames = sorted(payload["frames"], key=lambda item: int(item["frame_index"]))
    if len(frames) != expected_frames:
        raise ValueError(f"local evidence frame count mismatch: {report_path}")
    return frames


def validate_clip(
    clip_dir,
    output_dir,
    *,
    local_evidence_dir,
    base_url,
    models,
    anchor_stride,
    window,
    timeout,
    model_anchor_threshold,
    remote_consensus_threshold,
    remote_conflict_threshold,
    perceptflow_support_threshold,
    local_support_threshold,
):
    images, boxes = load_clip(clip_dir)
    remote_by_model = {}
    failures = []
    for model in models:
        predictions, model_failures = collect_remote_predictions(
            images,
            boxes,
            base_url=base_url,
            model=model,
            anchor_stride=anchor_stride,
            window=window,
            timeout=timeout,
        )
        remote_by_model[model] = predictions
        failures.extend(model_failures)

    local_evidence = load_local_continuity(
        local_evidence_dir / f"{clip_dir.name}_report.json", len(images)
    )
    frames = []
    for frame_index, perceptflow_box in enumerate(boxes):
        aggregates = {}
        reliable = True
        for model in models:
            predictions = remote_by_model[model][frame_index]
            medoid, anchor_consensus_iou = select_medoid(predictions)
            model_reliable = (
                len(predictions) >= 2
                and anchor_consensus_iou is not None
                and anchor_consensus_iou >= model_anchor_threshold
            )
            reliable = reliable and model_reliable
            aggregates[model] = {
                "prediction_count": len(predictions),
                "anchor_consensus_iou": None
                if anchor_consensus_iou is None
                else round(anchor_consensus_iou, 6),
                "reliable": model_reliable,
                "medoid_box": medoid,
                "iou_with_perceptflow": None
                if medoid is None
                else round(box_iou(medoid, perceptflow_box), 6),
                "predictions": predictions,
            }

        left_model = aggregates[models[0]]["medoid_box"]
        right_model = aggregates[models[1]]["medoid_box"]
        remote_model_iou = (
            None
            if left_model is None or right_model is None
            else box_iou(left_model, right_model)
        )
        perceptflow_ious = [
            aggregates[model]["iou_with_perceptflow"]
            for model in models
            if aggregates[model]["iou_with_perceptflow"] is not None
        ]
        local_frame = local_evidence[frame_index]
        local_iou = local_frame.get("iou")
        local_reliable = (
            local_iou is not None
            and int(local_frame.get("evidence_count", 0)) >= 2
            and int(local_frame.get("tracking_failure_count", 0)) == 0
        )
        if remote_model_iou is None or len(perceptflow_ious) != len(models):
            status = "tracker_unreliable"
        else:
            status = classify_frame(
                model_reliable=reliable,
                remote_model_iou=remote_model_iou,
                perceptflow_ious=perceptflow_ious,
                local_reliable=local_reliable,
                local_iou=local_iou,
                remote_consensus_threshold=remote_consensus_threshold,
                remote_conflict_threshold=remote_conflict_threshold,
                perceptflow_support_threshold=perceptflow_support_threshold,
                local_support_threshold=local_support_threshold,
            )

        frames.append(
            {
                "frame_index": frame_index + 1,
                "status": status,
                "perceptflow_box": perceptflow_box,
                "remote_model_iou": None
                if remote_model_iou is None
                else round(remote_model_iou, 6),
                "remote": aggregates,
                "local_csrt": local_frame,
            }
        )

    status_counts = dict(Counter(frame["status"] for frame in frames))
    report = {
        "clip": clip_dir.name,
        "method": "short_multi_anchor_remote_consensus_plus_adjacent_csrt",
        "models": models,
        "anchor_stride_frames": anchor_stride,
        "tracking_window_frames": window,
        "thresholds": {
            "model_anchor_consensus_iou": model_anchor_threshold,
            "remote_model_consensus_iou": remote_consensus_threshold,
            "remote_conflict_with_perceptflow_iou": remote_conflict_threshold,
            "perceptflow_support_iou": perceptflow_support_threshold,
            "local_csrt_support_iou": local_support_threshold,
        },
        "source_boxes_modified": False,
        "status_counts": status_counts,
        "perceptflow_suspect_frames": [
            frame["frame_index"]
            for frame in frames
            if frame["status"] == "perceptflow_suspect"
        ],
        "review_candidate_frames": [
            frame["frame_index"]
            for frame in frames
            if frame["status"] == "review_candidate"
        ],
        "remote_failures": failures,
        "frames": frames,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / f"{clip_dir.name}_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    render_video(
        images,
        frames,
        output_dir / f"{clip_dir.name}_consensus.mp4",
        models,
    )
    return report


def render_video(images, frames, output_path, models):
    height, width = images[0].shape[:2]
    writer = cv2.VideoWriter(
        str(output_path), cv2.VideoWriter_fourcc(*"mp4v"), 5.0, (width, height)
    )
    if not writer.isOpened():
        raise RuntimeError(f"failed to create {output_path}")
    colors = {models[0]: (0, 0, 255), models[1]: (255, 0, 255)}
    status_colors = {
        "perceptflow_suspect": (0, 0, 255),
        "review_candidate": (0, 128, 255),
        "perceptflow_supported": (0, 255, 0),
        "tracker_unreliable": (128, 128, 128),
    }
    for image, result in zip(images, frames):
        canvas = image.copy()
        x1, y1, x2, y2 = normalized_to_pixels(
            result["perceptflow_box"], width, height
        )
        cv2.rectangle(canvas, (x1, y1), (x2, y2), (0, 255, 0), 3)
        for model in models:
            box = result["remote"][model]["medoid_box"]
            if box is None:
                continue
            x1, y1, x2, y2 = normalized_to_pixels(box, width, height)
            cv2.rectangle(canvas, (x1, y1), (x2, y2), colors[model], 2)
        color = status_colors.get(result["status"], (255, 255, 0))
        label = (
            f"frame={result['frame_index']} status={result['status']} "
            f"remote_iou={result['remote_model_iou']}"
        )
        cv2.putText(
            canvas, label, (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2
        )
        cv2.putText(
            canvas,
            f"green=PerceptFlow red={models[0]} magenta={models[1]}",
            (20, 75),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (255, 255, 0),
            2,
        )
        writer.write(canvas)
    writer.release()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset_dir", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--local-evidence-dir", type=Path, required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:5000")
    parser.add_argument("--models", default="tomp50,prdimp50")
    parser.add_argument("--anchor-stride", type=int, default=3)
    parser.add_argument("--window", type=int, default=3)
    parser.add_argument("--timeout", type=float, default=300.0)
    parser.add_argument("--model-anchor-threshold", type=float, default=0.5)
    parser.add_argument("--remote-consensus-threshold", type=float, default=0.6)
    parser.add_argument("--remote-conflict-threshold", type=float, default=0.3)
    parser.add_argument("--perceptflow-support-threshold", type=float, default=0.5)
    parser.add_argument("--local-support-threshold", type=float, default=0.5)
    args = parser.parse_args()

    models = [value.strip() for value in args.models.split(",") if value.strip()]
    if len(models) != 2 or any(model not in MODELS for model in models):
        raise ValueError("exactly two configured remote models are required")
    if args.anchor_stride < 1 or args.window < 1:
        raise ValueError("anchor-stride and window must be positive")

    clips = sorted(args.dataset_dir.glob("clip_[0-9][0-9][0-9]"))
    if not clips:
        raise ValueError(f"no clips found in {args.dataset_dir}")
    reports = []
    for clip_dir in clips:
        print(f"running {clip_dir.name}", flush=True)
        report = validate_clip(
            clip_dir,
            args.output_dir,
            local_evidence_dir=args.local_evidence_dir,
            base_url=args.base_url,
            models=models,
            anchor_stride=args.anchor_stride,
            window=args.window,
            timeout=args.timeout,
            model_anchor_threshold=args.model_anchor_threshold,
            remote_consensus_threshold=args.remote_consensus_threshold,
            remote_conflict_threshold=args.remote_conflict_threshold,
            perceptflow_support_threshold=args.perceptflow_support_threshold,
            local_support_threshold=args.local_support_threshold,
        )
        reports.append(report)
        print(
            f"completed {clip_dir.name} suspects={report['perceptflow_suspect_frames']} "
            f"review={report['review_candidate_frames']}",
            flush=True,
        )
    summary = {
        "method": "short_multi_anchor_remote_consensus_plus_adjacent_csrt",
        "source_boxes_modified": False,
        "clips": [
            {
                "clip": report["clip"],
                "status_counts": report["status_counts"],
                "perceptflow_suspect_frames": report["perceptflow_suspect_frames"],
                "review_candidate_frames": report["review_candidate_frames"],
                "remote_failure_count": len(report["remote_failures"]),
            }
            for report in reports
        ],
    }
    (args.output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n"
    )


if __name__ == "__main__":
    main()

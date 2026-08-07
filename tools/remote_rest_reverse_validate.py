#!/usr/bin/env python3
"""Compare PerceptFlow boxes with a remote PyTracking REST tracker."""

from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path
import statistics
import time
from urllib import request

import cv2


MODELS = {
    "dimp18": ("dimp", "dimp18"),
    "dimp50": ("dimp", "dimp50"),
    "prdimp18": ("dimp", "prdimp18"),
    "prdimp50": ("dimp", "prdimp50"),
    "super_dimp": ("dimp", "super_dimp"),
    "keep_track": ("keep_track", "default"),
    "kys": ("kys", "default"),
    "tomp50": ("tomp", "tomp50"),
}


def post_json_string(url: str, payload: dict, timeout: float) -> dict:
    # The deployed v1 API expects a JSON string nested in a JSON request body.
    body = json.dumps(json.dumps(payload)).encode("utf-8")
    http_request = request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(http_request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def encode_image(image) -> str:
    ok, encoded = cv2.imencode(".jpg", image)
    if not ok:
        raise RuntimeError("failed to encode image")
    return base64.urlsafe_b64encode(encoded.tobytes()).decode("ascii")


def normalized_xyxy_to_pixel_xywh(box, width: int, height: int):
    x1, y1, x2, y2 = (float(value) for value in box)
    return [
        x1 * width / 1000,
        y1 * height / 1000,
        (x2 - x1) * width / 1000,
        (y2 - y1) * height / 1000,
    ]


def pixel_xywh_to_normalized_xyxy(box, width: int, height: int):
    x, y, box_width, box_height = (float(value) for value in box)
    return [
        x * 1000 / width,
        y * 1000 / height,
        (x + box_width) * 1000 / width,
        (y + box_height) * 1000 / height,
    ]


def box_iou(left, right) -> float:
    intersection_width = max(0.0, min(left[2], right[2]) - max(left[0], right[0]))
    intersection_height = max(0.0, min(left[3], right[3]) - max(left[1], right[1]))
    intersection = intersection_width * intersection_height
    left_area = max(0.0, left[2] - left[0]) * max(0.0, left[3] - left[1])
    right_area = max(0.0, right[2] - right[0]) * max(0.0, right[3] - right[1])
    union = left_area + right_area - intersection
    return 0.0 if union <= 0 else intersection / union


class RestTracker:
    def __init__(self, base_url: str, algo_name: str, algo_param: str, timeout: float):
        self.base_url = base_url.rstrip("/")
        self.algo_name = algo_name
        self.algo_param = algo_param
        self.timeout = timeout
        self.request_id = None

    def initialize(self, image, box_xywh):
        height, width = image.shape[:2]
        payload = {
            "bboxes": [
                {"x": box_xywh[0], "y": box_xywh[1], "w": box_xywh[2], "h": box_xywh[3]}
            ],
            "request_id": "client-generated-unused",
            "image_width": width,
            "image_height": height,
            "image_data": encode_image(image),
            "algo_name": self.algo_name,
            "algo_param": self.algo_param,
        }
        result = post_json_string(
            f"{self.base_url}/api/v1/mot/pytracking/launch_tracking",
            payload,
            self.timeout,
        )
        if str(result.get("status")) != "200":
            raise RuntimeError(result.get("message") or "tracker initialization failed")
        self.request_id = result["request_id"]

    def track(self, image):
        result = post_json_string(
            f"{self.base_url}/api/v1/mot/pytracking/track_next",
            {"request_id": self.request_id, "image_data": encode_image(image)},
            self.timeout,
        )
        if str(result.get("status")) != "200" or not result.get("bboxes"):
            raise RuntimeError(result.get("message") or "tracker update failed")
        box = result["bboxes"][0]
        return [box["x"], box["y"], box["w"], box["h"]]


def load_clip(clip_dir: Path):
    frame_paths = sorted((clip_dir / "frames").glob("frame_*.jpg"))
    images = [cv2.imread(str(path)) for path in frame_paths]
    if not images or any(image is None for image in images):
        raise ValueError(f"failed to load frames from {clip_dir}")
    payload = json.loads((clip_dir / "calibrated" / "results.json").read_text())
    ordered = sorted(payload, key=lambda item: int(item["frame_index"]))
    if len(images) != len(ordered):
        raise ValueError(f"frame/result count mismatch in {clip_dir}")
    return images, [item["box"] for item in ordered]


def validate_clip(
    clip_dir,
    output_dir,
    model,
    model_config,
    base_url,
    anchor_fraction,
    threshold,
    timeout,
    frame_stride,
    source_fps,
):
    images, proposed_boxes = load_clip(clip_dir)
    anchor_index = int((len(images) - 1) * anchor_fraction)
    height, width = images[anchor_index].shape[:2]
    tracker = RestTracker(base_url, *model_config, timeout)
    tracker.initialize(
        images[anchor_index],
        normalized_xyxy_to_pixel_xywh(proposed_boxes[anchor_index], width, height),
    )

    tracked = {anchor_index: proposed_boxes[anchor_index]}
    update_times = []
    error = None
    sampled_indices = set(range(anchor_index, -1, -frame_stride))
    for index in range(anchor_index - frame_stride, -1, -frame_stride):
        try:
            started = time.perf_counter()
            tracked_xywh = tracker.track(images[index])
            update_times.append(time.perf_counter() - started)
            frame_height, frame_width = images[index].shape[:2]
            tracked[index] = pixel_xywh_to_normalized_xyxy(
                tracked_xywh, frame_width, frame_height
            )
        except Exception as exc:
            error = f"frame {index + 1}: {exc}"
            break

    frames = []
    ious = []
    for index in range(len(images)):
        tracker_box = tracked.get(index)
        iou = None if tracker_box is None else box_iou(proposed_boxes[index], tracker_box)
        if iou is not None and index != anchor_index:
            ious.append(iou)
        frames.append(
            {
                "frame_index": index + 1,
                "status": "not_tested_after_anchor" if index > anchor_index else (
                    "skipped_by_stride" if index not in sampled_indices else (
                    "tracking_failed" if tracker_box is None else (
                        "anchor" if index == anchor_index else ("pass" if iou >= threshold else "review")
                    ))
                ),
                "iou": None if iou is None else round(iou, 6),
                "perceptflow_box": proposed_boxes[index],
                "tracker_box": tracker_box,
            }
        )

    report = {
        "clip": clip_dir.name,
        "model": model,
        "algo_name": model_config[0],
        "algo_param": model_config[1],
        "anchor_frame": anchor_index + 1,
        "anchor_fraction": anchor_fraction,
        "source_fps": source_fps,
        "frame_stride": frame_stride,
        "effective_fps": source_fps / frame_stride,
        "iou_threshold": threshold,
        "tested_frames": len(ious),
        "pass_count": sum(value >= threshold for value in ious),
        "pass_rate": round(sum(value >= threshold for value in ious) / len(ious), 6) if ious else None,
        "mean_iou": round(sum(ious) / len(ious), 6) if ious else None,
        "median_iou": round(statistics.median(ious), 6) if ious else None,
        "mean_update_seconds": round(sum(update_times) / len(update_times), 6) if update_times else None,
        "error": error,
        "frames": frames,
    }
    model_dir = output_dir / model
    model_dir.mkdir(parents=True, exist_ok=True)
    (model_dir / f"{clip_dir.name}_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    )
    render_video(
        images,
        frames,
        model_dir / f"{clip_dir.name}_reverse.mp4",
        model,
        anchor_index,
        frame_stride,
        source_fps / frame_stride,
    )
    return report


def normalized_to_pixels(box, width, height):
    return tuple(
        int(round(value))
        for value in (
            box[0] * width / 1000,
            box[1] * height / 1000,
            box[2] * width / 1000,
            box[3] * height / 1000,
        )
    )


def render_video(images, frames, output_path, model, anchor_index, frame_stride, output_fps):
    height, width = images[0].shape[:2]
    writer = cv2.VideoWriter(
        str(output_path), cv2.VideoWriter_fourcc(*"mp4v"), output_fps, (width, height)
    )
    if not writer.isOpened():
        raise RuntimeError(f"failed to create {output_path}")
    render_indices = (
        range(len(images))
        if frame_stride == 1
        else sorted(range(anchor_index, -1, -frame_stride))
    )
    for index in render_indices:
        image = images[index]
        result = frames[index]
        canvas = image.copy()
        px1, py1, px2, py2 = normalized_to_pixels(result["perceptflow_box"], width, height)
        cv2.rectangle(canvas, (px1, py1), (px2, py2), (0, 255, 0), 3)
        if result["tracker_box"] is not None:
            tx1, ty1, tx2, ty2 = normalized_to_pixels(result["tracker_box"], width, height)
            cv2.rectangle(canvas, (tx1, ty1), (tx2, ty2), (0, 0, 255), 3)
        label = f"{model} frame={index + 1} anchor={anchor_index + 1} status={result['status']} iou={result['iou']}"
        cv2.putText(canvas, label, (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (255, 255, 0), 2)
        cv2.putText(canvas, "green=PerceptFlow red=REST tracker", (20, 75), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (255, 255, 0), 2)
        writer.write(canvas)
    writer.release()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset_dir", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--base-url", default="http://127.0.0.1:5000")
    parser.add_argument("--models", default=",".join(MODELS))
    parser.add_argument("--anchor-fraction", type=float, default=0.75)
    parser.add_argument("--iou-threshold", type=float, default=0.5)
    parser.add_argument("--frame-stride", type=int, default=1)
    parser.add_argument("--source-fps", type=float, default=5.0)
    parser.add_argument("--timeout", type=float, default=180.0)
    args = parser.parse_args()

    if args.frame_stride < 1:
        raise ValueError("frame-stride must be at least 1")
    if args.source_fps <= 0:
        raise ValueError("source-fps must be positive")

    selected_models = [value.strip() for value in args.models.split(",") if value.strip()]
    unknown = [value for value in selected_models if value not in MODELS]
    if unknown:
        raise ValueError(f"unknown models: {unknown}")
    clips = sorted(args.dataset_dir.glob("clip_[0-9][0-9][0-9]"))
    if not clips:
        raise ValueError(f"no clips found in {args.dataset_dir}")

    reports = []
    failures = []
    for model in selected_models:
        for clip_dir in clips:
            print(f"running model={model} clip={clip_dir.name}", flush=True)
            try:
                report = validate_clip(
                    clip_dir,
                    args.output_dir,
                    model,
                    MODELS[model],
                    args.base_url,
                    args.anchor_fraction,
                    args.iou_threshold,
                    args.timeout,
                    args.frame_stride,
                    args.source_fps,
                )
                reports.append(report)
                print(
                    f"completed model={model} clip={clip_dir.name} "
                    f"pass_rate={report['pass_rate']} mean_iou={report['mean_iou']} error={report['error']}",
                    flush=True,
                )
            except Exception as exc:
                failures.append({"model": model, "clip": clip_dir.name, "error": str(exc)})
                print(f"failed model={model} clip={clip_dir.name}: {exc}", flush=True)

    summary = {"reports": reports, "failures": failures}
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "benchmark_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n"
    )
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

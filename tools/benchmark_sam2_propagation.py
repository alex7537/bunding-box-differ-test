#!/usr/bin/env python3
"""Compare SAM2.1 Tiny, ToMP50, and CSRT on PerceptFlow parcel clips."""

from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path
import statistics
import time
from urllib import request

import cv2
import numpy as np


def box_iou(left, right) -> float:
    if left is None or right is None:
        return 0.0
    intersection_width = max(0.0, min(left[2], right[2]) - max(left[0], right[0]))
    intersection_height = max(0.0, min(left[3], right[3]) - max(left[1], right[1]))
    intersection = intersection_width * intersection_height
    left_area = max(0.0, left[2] - left[0]) * max(0.0, left[3] - left[1])
    right_area = max(0.0, right[2] - right[0]) * max(0.0, right[3] - right[1])
    union = left_area + right_area - intersection
    return 0.0 if union <= 0 else intersection / union


def _post_json(url: str, payload: dict, timeout: float, nested: bool = False) -> dict:
    body = json.dumps(json.dumps(payload) if nested else payload).encode("utf-8")
    http_request = request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(http_request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _encode_image(image: np.ndarray) -> str:
    ok, encoded = cv2.imencode(".jpg", image)
    if not ok:
        raise RuntimeError("failed to encode frame")
    return base64.urlsafe_b64encode(encoded.tobytes()).decode("ascii")


def normalized_to_pixel_xywh(box, width: int, height: int):
    return [
        box[0] * width / 1000,
        box[1] * height / 1000,
        (box[2] - box[0]) * width / 1000,
        (box[3] - box[1]) * height / 1000,
    ]


def pixel_xywh_to_normalized(box, width: int, height: int):
    x, y, box_width, box_height = box
    return [
        x * 1000 / width,
        y * 1000 / height,
        (x + box_width) * 1000 / width,
        (y + box_height) * 1000 / height,
    ]


def pixel_xyxy_to_normalized(box, width: int, height: int):
    if box is None:
        return None
    return [
        box[0] * 1000 / width,
        box[1] * 1000 / height,
        box[2] * 1000 / width,
        box[3] * 1000 / height,
    ]


def load_clip(clip_dir: Path):
    frame_paths = sorted((clip_dir / "frames").glob("frame_*.jpg"))
    images = [cv2.imread(str(path)) for path in frame_paths]
    if not images or any(image is None for image in images):
        raise ValueError(f"failed to load frames from {clip_dir}")
    payload = json.loads((clip_dir / "calibrated" / "results.json").read_text())
    ordered = sorted(payload, key=lambda item: int(item["frame_index"]))
    if [int(item["frame_index"]) for item in ordered] != list(range(1, len(images) + 1)):
        raise ValueError(f"frame/result mismatch in {clip_dir}")
    return frame_paths, images, [item["box"] for item in ordered]


def run_sam2(frames_dir, images, anchor_index, anchor_box, base_url, timeout):
    height, width = images[0].shape[:2]
    x, y, box_width, box_height = normalized_to_pixel_xywh(anchor_box, width, height)
    result = _post_json(
        f"{base_url.rstrip('/')}/api/v1/mot/sam2/propagate",
        {
            "frames_dir": str(frames_dir),
            "anchor_frame": anchor_index + 1,
            "anchor_source": "pf",
            "box_xyxy_pixels": [x, y, x + box_width, y + box_height],
        },
        timeout,
    )
    if str(result.get("status")) != "200":
        raise RuntimeError(result.get("message") or "SAM2 request failed")
    boxes = []
    for image, frame in zip(images, result["frames"]):
        frame_height, frame_width = image.shape[:2]
        boxes.append(pixel_xyxy_to_normalized(frame["box_xyxy_pixels"], frame_width, frame_height))
    return boxes, float(result["elapsed_seconds"]), result


def _run_tomp_branch(images, anchor_index, anchor_box, indices, base_url, timeout):
    height, width = images[anchor_index].shape[:2]
    initial = normalized_to_pixel_xywh(anchor_box, width, height)
    launch = _post_json(
        f"{base_url.rstrip('/')}/api/v1/mot/pytracking/launch_tracking",
        {
            "bboxes": [{"x": initial[0], "y": initial[1], "w": initial[2], "h": initial[3]}],
            "request_id": "",
            "image_width": width,
            "image_height": height,
            "image_data": _encode_image(images[anchor_index]),
            "algo_name": "tomp",
            "algo_param": "tomp50",
        },
        timeout,
        nested=True,
    )
    if str(launch.get("status")) != "200":
        raise RuntimeError(launch.get("message") or "ToMP initialization failed")
    request_id = launch["request_id"]
    boxes = {}
    for index in indices:
        result = _post_json(
            f"{base_url.rstrip('/')}/api/v1/mot/pytracking/track_next",
            {"request_id": request_id, "image_data": _encode_image(images[index])},
            timeout,
            nested=True,
        )
        if str(result.get("status")) != "200" or len(result.get("bboxes", [])) != 1:
            raise RuntimeError(result.get("message") or f"ToMP failed at frame {index + 1}")
        bbox = result["bboxes"][0]
        frame_height, frame_width = images[index].shape[:2]
        boxes[index] = pixel_xywh_to_normalized(
            [bbox["x"], bbox["y"], bbox["w"], bbox["h"]], frame_width, frame_height
        )
    return boxes


def run_tomp(images, anchor_index, anchor_box, base_url, timeout):
    started = time.perf_counter()
    boxes = {anchor_index: list(anchor_box)}
    boxes.update(_run_tomp_branch(images, anchor_index, anchor_box, range(anchor_index - 1, -1, -1), base_url, timeout))
    boxes.update(_run_tomp_branch(images, anchor_index, anchor_box, range(anchor_index + 1, len(images)), base_url, timeout))
    return [boxes.get(index) for index in range(len(images))], time.perf_counter() - started, {}


def _create_csrt():
    legacy = getattr(cv2, "legacy", None)
    factory = getattr(legacy, "TrackerCSRT_create", None) if legacy else None
    factory = factory or getattr(cv2, "TrackerCSRT_create", None)
    if factory is None:
        raise RuntimeError("OpenCV CSRT tracker is unavailable")
    return factory()


def _run_csrt_branch(images, anchor_index, anchor_box, indices):
    height, width = images[anchor_index].shape[:2]
    tracker = _create_csrt()
    initialized = tracker.init(images[anchor_index], tuple(normalized_to_pixel_xywh(anchor_box, width, height)))
    if initialized is False:
        raise RuntimeError("CSRT initialization failed")
    boxes = {}
    for index in indices:
        success, bbox = tracker.update(images[index])
        if not success:
            boxes[index] = None
            break
        frame_height, frame_width = images[index].shape[:2]
        boxes[index] = pixel_xywh_to_normalized(bbox, frame_width, frame_height)
    return boxes


def run_csrt(images, anchor_index, anchor_box, _base_url, _timeout):
    started = time.perf_counter()
    boxes = {anchor_index: list(anchor_box)}
    boxes.update(_run_csrt_branch(images, anchor_index, anchor_box, range(anchor_index - 1, -1, -1)))
    boxes.update(_run_csrt_branch(images, anchor_index, anchor_box, range(anchor_index + 1, len(images))))
    return [boxes.get(index) for index in range(len(images))], time.perf_counter() - started, {}


def summarize(reference_boxes, boxes, anchor_index, elapsed_seconds):
    evaluated = [index for index in range(len(boxes)) if index != anchor_index]
    ious = [box_iou(reference_boxes[index], boxes[index]) for index in evaluated]
    adjacent_ious = [box_iou(boxes[index - 1], boxes[index]) for index in range(1, len(boxes))]
    return {
        "frame_count": len(boxes),
        "evaluated_frame_count": len(evaluated),
        "missing_box_count": sum(box is None for box in boxes),
        "perceptflow_agreement_iou_mean": round(statistics.mean(ious), 6),
        "perceptflow_agreement_iou_median": round(statistics.median(ious), 6),
        "perceptflow_agreement_rate_at_0_5": round(sum(value >= 0.5 for value in ious) / len(ious), 6),
        "temporal_adjacent_iou_mean": round(statistics.mean(adjacent_ious), 6),
        "temporal_jump_count_below_0_3": sum(value < 0.3 for value in adjacent_ious),
        "elapsed_seconds": round(elapsed_seconds, 6),
        "throughput_fps": round(len(boxes) / elapsed_seconds, 6),
    }


def _pixels(box, width, height):
    if box is None:
        return None
    return tuple(int(round(value)) for value in (
        box[0] * width / 1000, box[1] * height / 1000,
        box[2] * width / 1000, box[3] * height / 1000,
    ))


def render_comparison(images, reference, outputs, output_path, anchor_index, fps=5.0):
    height, width = images[0].shape[:2]
    writer = cv2.VideoWriter(str(output_path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))
    if not writer.isOpened():
        raise RuntimeError(f"failed to create {output_path}")
    colors = {"sam2.1_tiny": (0, 0, 255), "tomp50": (255, 0, 0), "csrt": (0, 255, 255)}
    for index, image in enumerate(images):
        canvas = image.copy()
        ref = _pixels(reference[index], width, height)
        cv2.rectangle(canvas, ref[:2], ref[2:], (0, 255, 0), 2)
        for backend, boxes in outputs.items():
            box = _pixels(boxes[index], width, height)
            if box is not None:
                cv2.rectangle(canvas, box[:2], box[2:], colors[backend], 2)
        cv2.putText(canvas, f"frame={index + 1} anchor={anchor_index + 1}", (15, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        labels = {"sam2.1_tiny": "red=SAM2", "tomp50": "blue=ToMP", "csrt": "yellow=CSRT"}
        legend = "green=PF " + " ".join(labels[name] for name in outputs)
        cv2.putText(canvas, legend, (15, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        writer.write(canvas)
    writer.release()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset_dir", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--sam2-url", default="http://127.0.0.1:5001")
    parser.add_argument("--pytracking-url", default="http://127.0.0.1:5000")
    parser.add_argument("--anchor-fraction", type=float, default=0.75)
    parser.add_argument("--timeout", type=float, default=600.0)
    parser.add_argument(
        "--backends",
        nargs="+",
        choices=("sam2.1_tiny", "tomp50", "csrt"),
        default=("sam2.1_tiny", "tomp50", "csrt"),
    )
    args = parser.parse_args()
    if not 0 <= args.anchor_fraction <= 1:
        raise ValueError("anchor-fraction must be between zero and one")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    backend_registry = {"sam2.1_tiny": run_sam2, "tomp50": run_tomp, "csrt": run_csrt}
    backends = {name: backend_registry[name] for name in args.backends}
    report = {"method": "single_anchor_bidirectional_propagation", "anchor_fraction": args.anchor_fraction, "clips": []}
    for clip_dir in sorted(args.dataset_dir.glob("clip_[0-9][0-9][0-9]")):
        frame_paths, images, reference_boxes = load_clip(clip_dir)
        anchor_index = int((len(images) - 1) * args.anchor_fraction)
        outputs = {}
        clip_result = {"clip": clip_dir.name, "anchor_frame": anchor_index + 1, "frame_count": len(images), "backends": {}}
        for name, runner in backends.items():
            try:
                frames_dir = clip_dir / "frames" if name == "sam2.1_tiny" else images
                boxes, elapsed, raw = runner(
                    frames_dir,
                    images,
                    anchor_index,
                    reference_boxes[anchor_index],
                    args.sam2_url,
                    args.timeout,
                ) if name == "sam2.1_tiny" else runner(
                    images, anchor_index, reference_boxes[anchor_index], args.pytracking_url, args.timeout
                )
                outputs[name] = boxes
                clip_result["backends"][name] = {"status": "succeeded", **summarize(reference_boxes, boxes, anchor_index, elapsed)}
                if raw:
                    (args.output_dir / f"{clip_dir.name}_{name}_raw.json").write_text(json.dumps(raw, indent=2) + "\n")
            except Exception as exc:
                clip_result["backends"][name] = {"status": "failed", "error": str(exc)}
        if len(outputs) == len(backends):
            metadata_path = clip_dir / "clip.json"
            fps = float(json.loads(metadata_path.read_text()).get("fps", 5.0)) if metadata_path.exists() else 5.0
            render_comparison(
                images,
                reference_boxes,
                outputs,
                args.output_dir / f"{clip_dir.name}_comparison.mp4",
                anchor_index,
                fps=fps,
            )
        report["clips"].append(clip_result)
        print(json.dumps(clip_result, ensure_ascii=False), flush=True)
    if len(report["clips"]) != 3:
        raise ValueError(f"expected three clips, found {len(report['clips'])}")
    (args.output_dir / "benchmark_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()

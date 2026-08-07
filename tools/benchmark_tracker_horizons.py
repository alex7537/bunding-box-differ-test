#!/usr/bin/env python3
"""Measure tracker agreement after different temporal horizons."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import statistics
import sys
import time

import cv2


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from libs.reverse_tracker_validator import (  # noqa: E402
    _create_tracker,
    _normalized_xyxy_to_pixel_xywh,
    _normalized_xyxy_to_pixel_xyxy,
    _pixel_xywh_to_xyxy,
    _read_image,
    box_iou,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset_dir", type=Path)
    parser.add_argument("output_json", type=Path)
    parser.add_argument("--trackers", default="CSRT,KCF,MIL,MOSSE,TLD")
    parser.add_argument("--horizons", default="1,3,5,15,25")
    parser.add_argument("--fps", type=float, default=5.0)
    parser.add_argument("--iou-threshold", type=float, default=0.5)
    args = parser.parse_args()

    trackers = [value.strip().upper() for value in args.trackers.split(",") if value.strip()]
    horizons = [int(value) for value in args.horizons.split(",") if value.strip()]
    clips = [_load_clip(path) for path in sorted(args.dataset_dir.glob("clip_[0-9][0-9][0-9]"))]
    if not clips:
        raise ValueError(f"no clip_NNN directories found in {args.dataset_dir}")

    results = []
    for tracker_name in trackers:
        for horizon in horizons:
            result = _benchmark(tracker_name, horizon, clips, args.iou_threshold)
            result["seconds"] = round(horizon / args.fps, 3)
            results.append(result)
            print(
                f"{tracker_name} horizon={horizon} frames ({result['seconds']}s) "
                f"pass_rate={result['pass_rate']} failure_rate={result['failure_rate']} "
                f"mean_iou_all={result['mean_iou_all_tracks']}"
            )

    payload = {
        "video_fps": args.fps,
        "iou_threshold": args.iou_threshold,
        "results": results,
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"wrote {args.output_json}")


def _load_clip(clip_dir: Path):
    frame_paths = sorted((clip_dir / "frames").glob("frame_*.jpg"))
    images = [_read_image(path) for path in frame_paths]
    payload = json.loads((clip_dir / "calibrated" / "results.json").read_text(encoding="utf-8"))
    ordered = sorted(payload, key=lambda item: int(item["frame_index"]))
    return clip_dir.name, images, [item["box"] for item in ordered]


def _benchmark(tracker_name, horizon, clips, threshold):
    ious = []
    failures = 0
    attempted_tracks = 0
    update_calls = 0
    started = time.perf_counter()
    for _, images, boxes in clips:
        if horizon >= len(images):
            continue
        for left_index in range(len(images) - horizon):
            right_index = left_index + horizon
            for source, target, step in (
                (left_index, right_index, 1),
                (right_index, left_index, -1),
            ):
                attempted_tracks += 1
                cv2.setRNGSeed(0)
                tracker = _create_tracker(tracker_name)
                height, width = images[source].shape[:2]
                initialized = tracker.init(
                    images[source],
                    _normalized_xyxy_to_pixel_xywh(boxes[source], width, height),
                )
                if initialized is False:
                    failures += 1
                    continue

                tracked_xywh = None
                success = True
                for frame_index in range(source + step, target + step, step):
                    success, tracked_xywh = tracker.update(images[frame_index])
                    update_calls += 1
                    if not success:
                        break
                if not success:
                    failures += 1
                    continue

                target_height, target_width = images[target].shape[:2]
                tracked_box = _pixel_xywh_to_xyxy(tracked_xywh)
                proposed_box = _normalized_xyxy_to_pixel_xyxy(
                    boxes[target], target_width, target_height
                )
                ious.append(box_iou(tracked_box, proposed_box))

    elapsed = time.perf_counter() - started
    pass_count = sum(iou >= threshold for iou in ious)
    return {
        "tracker": tracker_name,
        "horizon_frames": horizon,
        "attempted_tracks": attempted_tracks,
        "valid_tracks": len(ious),
        "tracking_failures": failures,
        "failure_rate": round(failures / attempted_tracks, 6) if attempted_tracks else None,
        "pass_count": pass_count,
        "pass_rate": round(pass_count / attempted_tracks, 6) if attempted_tracks else None,
        "mean_iou_valid_tracks": round(statistics.fmean(ious), 6) if ious else None,
        "median_iou_valid_tracks": round(statistics.median(ious), 6) if ious else None,
        "mean_iou_all_tracks": round(sum(ious) / attempted_tracks, 6) if attempted_tracks else None,
        "update_calls": update_calls,
        "elapsed_seconds": round(elapsed, 6),
        "update_fps": round(update_calls / elapsed, 3) if elapsed else None,
    }


if __name__ == "__main__":
    main()

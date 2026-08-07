#!/usr/bin/env python3
"""Render a visual comparison of PerceptFlow and reverse-tracker boxes."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np


def _normalized_box_to_pixels(box, width: int, height: int):
    if box is None:
        return None
    x1, y1, x2, y2 = box
    return (
        int(round(x1 * width / 1000.0)),
        int(round(y1 * height / 1000.0)),
        int(round(x2 * width / 1000.0)),
        int(round(y2 * height / 1000.0)),
    )


def _draw_box(image, box, color, label: str, thickness: int = 3):
    if box is None:
        return
    x1, y1, x2, y2 = box
    cv2.rectangle(image, (x1, y1), (x2, y2), color, thickness)
    text_y = max(24, y1 - 8)
    cv2.putText(
        image,
        label,
        (x1, text_y),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.65,
        color,
        2,
        cv2.LINE_AA,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("frames_dir", type=Path)
    parser.add_argument("report_json", type=Path)
    parser.add_argument("output_video", type=Path)
    parser.add_argument("--fps", type=float, default=5.0)
    parser.add_argument("--clip-name", default=None)
    args = parser.parse_args()

    frame_paths = sorted(args.frames_dir.glob("frame_*.jpg"))
    report = json.loads(args.report_json.read_text(encoding="utf-8"))
    results = report["frames"]
    if len(frame_paths) != len(results):
        raise ValueError("frame count does not match validation report")

    first = cv2.imdecode(np.fromfile(frame_paths[0], dtype=np.uint8), cv2.IMREAD_COLOR)
    if first is None:
        raise ValueError(f"failed to read {frame_paths[0]}")
    height, width = first.shape[:2]
    args.output_video.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(
        str(args.output_video),
        cv2.VideoWriter_fourcc(*"mp4v"),
        args.fps,
        (width, height),
    )
    if not writer.isOpened():
        raise RuntimeError(f"failed to open video writer: {args.output_video}")

    clip_name = args.clip_name or args.frames_dir.parent.name
    try:
        for frame_path, result in zip(frame_paths, results):
            image = cv2.imdecode(np.fromfile(frame_path, dtype=np.uint8), cv2.IMREAD_COLOR)
            if image is None:
                raise ValueError(f"failed to read {frame_path}")

            proposed = _normalized_box_to_pixels(result["proposed_box"], width, height)
            tracked = _normalized_box_to_pixels(result["tracker_box"], width, height)
            status = result["status"]
            tracker_color = (0, 255, 255) if status == "anchor" else (
                (255, 160, 0) if status == "pass" else (0, 0, 255)
            )
            _draw_box(image, proposed, (0, 255, 0), "PerceptFlow")
            _draw_box(image, tracked, tracker_color, "Tracker")

            iou_text = "n/a" if result["iou"] is None else f"{result['iou']:.3f}"
            title = (
                f"{clip_name}  frame {result['frame_index']}/{len(results)}  "
                f"anchor={report['anchor_frame']}  direction={result['direction']}"
            )
            verdict = f"status={status}  IoU={iou_text}"
            cv2.rectangle(image, (0, 0), (width, 72), (0, 0, 0), -1)
            cv2.putText(image, title, (18, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.67,
                        (255, 255, 255), 2, cv2.LINE_AA)
            cv2.putText(image, verdict, (18, 59), cv2.FONT_HERSHEY_SIMPLEX, 0.67,
                        tracker_color, 2, cv2.LINE_AA)
            writer.write(image)
    finally:
        writer.release()

    print(f"wrote {args.output_video}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Render all local tracker results as a side-by-side comparison video."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np


TRACKERS = ("CSRT", "KCF", "MIL", "MOSSE", "TLD")
PANEL_SIZE = (640, 360)


def _pixels(box, width: int, height: int):
    if box is None:
        return None
    x1, y1, x2, y2 = box
    return tuple(
        map(
            int,
            (
                x1 * width / 1000,
                y1 * height / 1000,
                x2 * width / 1000,
                y2 * height / 1000,
            ),
        )
    )


def _draw_box(image, box, color, label):
    if box is None:
        return
    x1, y1, x2, y2 = box
    cv2.rectangle(image, (x1, y1), (x2, y2), color, 4)
    cv2.putText(image, label, (x1, max(30, y1 - 8)), cv2.FONT_HERSHEY_SIMPLEX,
                0.8, color, 2, cv2.LINE_AA)


def _panel(source, frame_result, tracker: str, clip_name: str, anchor_frame: int):
    image = source.copy()
    height, width = image.shape[:2]
    status = frame_result["status"]
    color = (0, 255, 255) if status == "anchor" else (
        (255, 160, 0) if status == "pass" else (0, 0, 255)
    )
    _draw_box(image, _pixels(frame_result["proposed_box"], width, height),
              (0, 255, 0), "PerceptFlow")
    _draw_box(image, _pixels(frame_result["tracker_box"], width, height), color, tracker)
    image = cv2.resize(image, PANEL_SIZE)
    cv2.rectangle(image, (0, 0), (PANEL_SIZE[0], 58), (0, 0, 0), -1)
    iou = "n/a" if frame_result["iou"] is None else f"{frame_result['iou']:.3f}"
    cv2.putText(image, f"{tracker}  {status}  IoU={iou}", (12, 25),
                cv2.FONT_HERSHEY_SIMPLEX, 0.64, color, 2, cv2.LINE_AA)
    cv2.putText(
        image,
        f"{clip_name} frame={frame_result['frame_index']} anchor={anchor_frame}",
        (12, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1, cv2.LINE_AA,
    )
    return image


def _baseline_panel(source, frame_result, clip_name: str):
    image = source.copy()
    height, width = image.shape[:2]
    _draw_box(image, _pixels(frame_result["proposed_box"], width, height),
              (0, 255, 0), "PerceptFlow")
    image = cv2.resize(image, PANEL_SIZE)
    cv2.rectangle(image, (0, 0), (PANEL_SIZE[0], 78), (0, 0, 0), -1)
    lines = (
        "REFERENCE: PerceptFlow bbox",
        f"{clip_name} frame={frame_result['frame_index']}",
        "Blue=pass  Red=review/failure",
    )
    for index, line in enumerate(lines):
        cv2.putText(image, line, (12, 23 + index * 24), cv2.FONT_HERSHEY_SIMPLEX,
                    0.55, (0, 255, 0) if index == 0 else (255, 255, 255),
                    1, cv2.LINE_AA)
    return image


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset_dir", type=Path)
    parser.add_argument("benchmark_dir", type=Path)
    parser.add_argument("output_video", type=Path)
    parser.add_argument("--fps", type=float, default=5.0)
    args = parser.parse_args()

    args.output_video.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(str(args.output_video), cv2.VideoWriter_fourcc(*"mp4v"),
                             args.fps, (PANEL_SIZE[0] * 3, PANEL_SIZE[1] * 2))
    if not writer.isOpened():
        raise RuntimeError(f"failed to open {args.output_video}")

    try:
        for clip_dir in sorted(args.dataset_dir.glob("clip_[0-9][0-9][0-9]")):
            reports = {
                tracker: json.loads(
                    (args.benchmark_dir / f"{clip_dir.name}_{tracker.lower()}_report.json")
                    .read_text(encoding="utf-8")
                )
                for tracker in TRACKERS
            }
            frame_paths = sorted((clip_dir / "frames").glob("frame_*.jpg"))
            for index, frame_path in enumerate(frame_paths):
                source = cv2.imdecode(np.fromfile(frame_path, dtype=np.uint8), cv2.IMREAD_COLOR)
                panels = [
                    _panel(source, reports[tracker]["frames"][index], tracker, clip_dir.name,
                           reports[tracker]["anchor_frame"])
                    for tracker in TRACKERS
                ]
                panels.append(_baseline_panel(source, reports["CSRT"]["frames"][index], clip_dir.name))
                writer.write(np.vstack((np.hstack(panels[:3]), np.hstack(panels[3:]))))
    finally:
        writer.release()
    print(f"wrote {args.output_video}")


if __name__ == "__main__":
    main()

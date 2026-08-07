#!/usr/bin/env python3
"""Render PerceptFlow boxes and independent multi-anchor tracker evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np


ANCHOR_COLORS = ((255, 160, 0), (255, 0, 255), (0, 165, 255), (255, 255, 0), (180, 80, 255))


def _pixels(box, width, height):
    if box is None:
        return None
    return tuple(
        int(round(value * scale / 1000.0))
        for value, scale in zip(box, (width, height, width, height))
    )


def _draw_box(image, box, color, label, thickness=2):
    if box is None:
        return
    x1, y1, x2, y2 = box
    cv2.rectangle(image, (x1, y1), (x2, y2), color, thickness)
    cv2.putText(image, label, (x1, max(88, y1 - 6)), cv2.FONT_HERSHEY_SIMPLEX,
                0.52, color, 2, cv2.LINE_AA)


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
    first = cv2.imdecode(np.fromfile(frame_paths[0], dtype=np.uint8), cv2.IMREAD_COLOR)
    height, width = first.shape[:2]
    args.output_video.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(str(args.output_video), cv2.VideoWriter_fourcc(*"mp4v"),
                             args.fps, (width, height))
    if not writer.isOpened():
        raise RuntimeError(f"failed to open {args.output_video}")

    clip_name = args.clip_name or args.frames_dir.parent.name
    try:
        for frame_path, result in zip(frame_paths, report["frames"]):
            image = cv2.imdecode(np.fromfile(frame_path, dtype=np.uint8), cv2.IMREAD_COLOR)
            status = result["status"]
            status_color = {
                "supported": (255, 160, 0),
                "suspected_perceptflow_drift": (0, 0, 255),
                "tracker_unreliable": (0, 255, 255),
            }[status]
            _draw_box(
                image,
                _pixels(result["perceptflow_box"], width, height),
                (0, 255, 0),
                "PerceptFlow",
                4,
            )
            for index, evidence in enumerate(result["anchor_evidence"]):
                color = ANCHOR_COLORS[index % len(ANCHOR_COLORS)]
                label = f"A{evidence['anchor_frame']} c={evidence['cycle_iou']}"
                _draw_box(
                    image,
                    _pixels(evidence["predicted_box"], width, height),
                    color,
                    label,
                )

            cv2.rectangle(image, (0, 0), (width, 78), (0, 0, 0), -1)
            cv2.putText(
                image,
                f"{clip_name} frame={result['frame_index']} anchors={report['anchor_frames']}",
                (16, 27), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2, cv2.LINE_AA,
            )
            cv2.putText(
                image,
                f"{status} reliable={result['reliable_anchor_count']} "
                f"tracker_consensus={result['tracker_consensus_iou']} "
                f"PF_consensus={result['perceptflow_consensus_iou']} local={result['local_iou']}",
                (16, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.58, status_color, 2, cv2.LINE_AA,
            )
            writer.write(image)
    finally:
        writer.release()
    print(f"wrote {args.output_video}")


if __name__ == "__main__":
    main()

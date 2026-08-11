#!/usr/bin/env python3
"""Render original PF/SAM beside PF/human-rerun SAM for every corrected clip."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import statistics

import cv2
import numpy as np


def box_iou(left, right):
    if left is None or right is None:
        return 0.0
    intersection_width = max(0.0, min(left[2], right[2]) - max(left[0], right[0]))
    intersection_height = max(0.0, min(left[3], right[3]) - max(left[1], right[1]))
    intersection = intersection_width * intersection_height
    left_area = max(0.0, left[2] - left[0]) * max(0.0, left[3] - left[1])
    right_area = max(0.0, right[2] - right[0]) * max(0.0, right[3] - right[1])
    union = left_area + right_area - intersection
    return 0.0 if union <= 0 else intersection / union


def pf_box_pixels(reference, width, height):
    box = reference.get("box")
    if box is None:
        return None
    return [
        float(box[0]) * width / 1000,
        float(box[1]) * height / 1000,
        float(box[2]) * width / 1000,
        float(box[3]) * height / 1000,
    ]


def draw_box(image, box, color, label, thickness=3):
    if box is None:
        return
    x1, y1, x2, y2 = (int(round(value)) for value in box)
    cv2.rectangle(image, (x1, y1), (x2, y2), color, thickness)
    cv2.putText(
        image,
        label,
        (x1, max(82, y1 - 6)),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.58,
        color,
        2,
        cv2.LINE_AA,
    )


def add_header(image, title, detail):
    cv2.rectangle(image, (0, 0), (image.shape[1], 68), (0, 0, 0), -1)
    cv2.putText(
        image, title, (12, 27), cv2.FONT_HERSHEY_SIMPLEX, 0.7,
        (255, 255, 255), 2, cv2.LINE_AA,
    )
    cv2.putText(
        image, detail, (12, 55), cv2.FONT_HERSHEY_SIMPLEX, 0.58,
        (255, 255, 255), 2, cv2.LINE_AA,
    )


def title_frames(width, height, key, frame_count, fps):
    image = np.zeros((height, width * 2, 3), dtype=np.uint8)
    cv2.putText(
        image, key, (80, height // 2 - 20), cv2.FONT_HERSHEY_SIMPLEX, 1.5,
        (255, 255, 255), 3, cv2.LINE_AA,
    )
    cv2.putText(
        image,
        f"{frame_count} frames | left: original PF/SAM | right: human-rerun SAM",
        (80, height // 2 + 35),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (210, 210, 210),
        2,
        cv2.LINE_AA,
    )
    return [image] * max(1, int(round(fps)))


def render_clip(dataset_root, result_root, output_dir, episode, clip, combined_writer):
    clip_dir = dataset_root / episode / clip
    result_dir = result_root / episode
    frame_paths = sorted((clip_dir / "frames").glob("frame_*.jpg"))
    references = sorted(
        json.loads((clip_dir / "calibrated" / "results.json").read_text()),
        key=lambda item: int(item["frame_index"]),
    )
    original_payload = json.loads(
        (result_dir / f"{clip}_sam2.1_tiny_raw.json").read_text()
    )
    human_payload = json.loads(
        (result_dir / f"{clip}_sam2.1_tiny_human_raw.json").read_text()
    )
    anchor = json.loads((result_dir / f"{clip}_human_anchor.json").read_text())
    original_frames = original_payload["frames"]
    human_frames = human_payload["frames"]
    if not len(frame_paths) == len(references) == len(original_frames) == len(human_frames):
        raise ValueError(f"frame count mismatch: {episode}/{clip}")

    first = cv2.imread(str(frame_paths[0]))
    height, width = first.shape[:2]
    metadata_path = clip_dir / "clip.json"
    fps = float(json.loads(metadata_path.read_text()).get("fps", 5.0)) if metadata_path.exists() else 5.0
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / f"{episode}_{clip}_before_after.mp4"
    writer = cv2.VideoWriter(
        str(output), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width * 2, height)
    )
    if not writer.isOpened():
        raise RuntimeError(f"failed to create {output}")

    for title in title_frames(width, height, f"{episode}/{clip}", len(frame_paths), fps):
        combined_writer.write(title)

    original_pf_ious = []
    human_pf_ious = []
    original_human_ious = []
    for index, frame_path in enumerate(frame_paths):
        image = cv2.imread(str(frame_path))
        pf_box = pf_box_pixels(references[index], width, height)
        original_box = original_frames[index].get("box_xyxy_pixels")
        human_box = human_frames[index].get("box_xyxy_pixels")
        original_pf_iou = box_iou(pf_box, original_box)
        human_pf_iou = box_iou(pf_box, human_box)
        original_human_iou = box_iou(original_box, human_box)
        original_pf_ious.append(original_pf_iou)
        human_pf_ious.append(human_pf_iou)
        original_human_ious.append(original_human_iou)

        left = image.copy()
        right = image.copy()
        draw_box(left, pf_box, (0, 220, 0), "PF")
        draw_box(left, original_box, (0, 0, 255), "ORIGINAL SAM")
        draw_box(right, pf_box, (0, 220, 0), "PF")
        draw_box(right, human_box, (255, 90, 0), "HUMAN-RERUN SAM")
        if index + 1 == int(anchor["anchor_frame"]):
            draw_box(right, anchor["box_xyxy_pixels"], (0, 165, 255), "HUMAN ANCHOR", 5)
        add_header(
            left,
            f"BEFORE | {episode}/{clip} | frame {index + 1}/{len(frame_paths)}",
            f"green=PF red=SAM from PF anchor {original_payload['anchor_frame']} | IoU={original_pf_iou:.3f}",
        )
        add_header(
            right,
            f"AFTER | human anchor frame {anchor['anchor_frame']}",
            f"green=PF blue=human-rerun SAM | PF IoU={human_pf_iou:.3f} | before/after IoU={original_human_iou:.3f}",
        )
        canvas = np.hstack((left, right))
        writer.write(canvas)
        combined_writer.write(canvas)
    writer.release()
    return {
        "key": f"{episode}/{clip}",
        "frame_count": len(frame_paths),
        "fps": fps,
        "original_anchor_frame": original_payload["anchor_frame"],
        "human_anchor_frame": anchor["anchor_frame"],
        "human_anchor_bbox_xyxy_pixels": anchor["box_xyxy_pixels"],
        "attribution": anchor.get("attribution"),
        "pf_original_sam_iou_mean": round(statistics.mean(original_pf_ious), 6),
        "pf_human_rerun_sam_iou_mean": round(statistics.mean(human_pf_ious), 6),
        "original_vs_human_rerun_sam_iou_mean": round(
            statistics.mean(original_human_ious), 6
        ),
        "video": str(output),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--result-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    records = sorted(args.result_root.glob("*/clip_*_human_anchor.json"))
    if not records:
        raise ValueError("no human anchor records found")
    first_record = json.loads(records[0].read_text())
    first_episode = records[0].parent.name
    first_clip = first_record["clip"]
    first_image = cv2.imread(
        str(sorted((args.dataset_root / first_episode / first_clip / "frames").glob("frame_*.jpg"))[0])
    )
    height, width = first_image.shape[:2]
    first_metadata = args.dataset_root / first_episode / first_clip / "clip.json"
    combined_fps = float(json.loads(first_metadata.read_text()).get("fps", 5.0))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    combined_output = args.output_dir / "all_human_rerun_before_after.mp4"
    combined_writer = cv2.VideoWriter(
        str(combined_output), cv2.VideoWriter_fourcc(*"mp4v"), combined_fps,
        (width * 2, height),
    )
    if not combined_writer.isOpened():
        raise RuntimeError(f"failed to create {combined_output}")

    reports = []
    for record_path in records:
        episode = record_path.parent.name
        clip = json.loads(record_path.read_text())["clip"]
        reports.append(
            render_clip(
                args.dataset_root, args.result_root, args.output_dir,
                episode, clip, combined_writer,
            )
        )
    combined_writer.release()
    summary = {
        "schema_version": 1,
        "clip_count": len(reports),
        "combined_video": str(combined_output),
        "clips": reports,
    }
    (args.output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

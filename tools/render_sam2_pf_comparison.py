#!/usr/bin/env python3
"""Render PerceptFlow annotated frames with SAM2 boxes overlaid."""

import argparse
import json
from pathlib import Path

import cv2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset_dir", type=Path)
    parser.add_argument("result_dir", type=Path)
    args = parser.parse_args()

    report = json.loads((args.result_dir / "benchmark_report.json").read_text())
    for clip in report["clips"]:
        name = clip["clip"]
        anchor = clip["anchor_frame"]
        images = sorted((args.dataset_dir / name / "calibrated").glob("frame_*_annotated.jpg"))
        raw_path = args.result_dir / f"{name}_sam2.1_tiny_raw.json"
        frames = json.loads(raw_path.read_text())["frames"]
        references = json.loads((args.dataset_dir / name / "calibrated" / "results.json").read_text())
        if not len(images) == len(frames) == len(references):
            raise ValueError(
                f"frame count mismatch for {name}: {len(images)}, {len(frames)}, {len(references)}"
            )

        first = cv2.imread(str(images[0]))
        height, width = first.shape[:2]
        metadata = json.loads((args.dataset_dir / name / "clip.json").read_text())
        output = args.result_dir / f"{name}_pf_green_sam_red.mp4"
        writer = cv2.VideoWriter(
            str(output), cv2.VideoWriter_fourcc(*"mp4v"), float(metadata["fps"]), (width, height)
        )
        if not writer.isOpened():
            raise RuntimeError(f"failed to create {output}")

        for index, (image_path, frame, reference) in enumerate(zip(images, frames, references), 1):
            image = cv2.imread(str(image_path))
            px1, py1, px2, py2 = (
                int(round(reference["box"][0] * width / 1000)),
                int(round(reference["box"][1] * height / 1000)),
                int(round(reference["box"][2] * width / 1000)),
                int(round(reference["box"][3] * height / 1000)),
            )
            x1, y1, x2, y2 = frame["box_xyxy_pixels"]
            cv2.rectangle(image, (px1, py1), (px2, py2), (0, 255, 0), 6)
            cv2.rectangle(image, (x1, y1), (x2, y2), (0, 0, 255), 3)
            cv2.rectangle(image, (0, 0), (width, 62), (0, 0, 0), -1)
            cv2.putText(
                image,
                f"{name} frame={index}/{len(images)} anchor={anchor}",
                (12, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2, cv2.LINE_AA,
            )
            cv2.putText(
                image,
                "green=PerceptFlow  red=SAM2.1 Tiny",
                (12, 52), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2, cv2.LINE_AA,
            )
            writer.write(image)
        writer.release()
        print(f"created {output} ({len(images)} frames at {metadata['fps']} fps)")


if __name__ == "__main__":
    main()

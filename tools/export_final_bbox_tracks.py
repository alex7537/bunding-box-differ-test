#!/usr/bin/env python3
"""Export one final PF-or-SAM bbox track for every clip in a dataset."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
from pathlib import Path

from PIL import Image


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def build_pf_track(clip_dir: Path) -> dict:
    frame_paths = sorted((clip_dir / "frames").glob("frame_*.jpg"))
    references = sorted(
        json.loads((clip_dir / "calibrated" / "results.json").read_text(encoding="utf-8")),
        key=lambda item: int(item["frame_index"]),
    )
    if not frame_paths or len(frame_paths) != len(references):
        raise ValueError(f"PF frame count mismatch: {clip_dir}")
    with Image.open(frame_paths[0]) as image:
        width, height = image.size
    frames = []
    for frame_path, reference in zip(frame_paths, references):
        box = reference.get("box")
        box_pixels = None
        if box is not None:
            box_pixels = [
                round(float(box[0]) * width / 1000, 3),
                round(float(box[1]) * height / 1000, 3),
                round(float(box[2]) * width / 1000, 3),
                round(float(box[3]) * height / 1000, 3),
            ]
        frames.append(
            {
                "frame_index": int(reference["frame_index"]),
                "frame_name": frame_path.name,
                "box_xyxy_pixels": box_pixels,
            }
        )
    return {
        "schema_version": 1,
        "episode": clip_dir.parent.name,
        "clip": clip_dir.name,
        "decision_scope": "whole_clip",
        "selected_track": "pf",
        "coordinate_space": "pixels_xyxy",
        "image_size": {"width": width, "height": height},
        "frame_count": len(frames),
        "source_artifact": str(clip_dir / "calibrated" / "results.json"),
        "frames": frames,
    }


def decision_type(selected_track: str, source_artifact: str) -> str:
    if selected_track == "pf":
        return "human_confirmed_pf"
    if "_human_raw.json" in source_artifact:
        return "human_confirmed_sam_after_reanchor"
    return "human_confirmed_sam"


def export_tracks(dataset_root: Path, queue_path: Path, output_root: Path) -> dict:
    queue = json.loads(queue_path.read_text(encoding="utf-8"))
    queue_items = {item["key"]: item for item in queue["items"]}
    records = []
    for clip_dir in sorted(dataset_root.glob("*/clip_*")):
        if not (clip_dir / "calibrated" / "results.json").is_file():
            continue
        key = f"{clip_dir.parent.name}/{clip_dir.name}"
        queue_item = queue_items.get(key)
        selected_track = queue_item.get("final_track_source") if queue_item else None
        if selected_track:
            selected_path = queue_path.parent / queue_item["final_track_file"]
            if not selected_path.is_file():
                raise ValueError(f"selected final track does not exist: {selected_path}")
            payload = json.loads(selected_path.read_text(encoding="utf-8"))
            if payload.get("selected_track") != selected_track:
                raise ValueError(f"selected track mismatch: {key}")
            review_status = "human_confirmed"
            source = decision_type(selected_track, payload.get("source_artifact", ""))
            review_pending = False
        else:
            payload = build_pf_track(clip_dir)
            review_pending = queue_item is not None
            review_status = "review_pending" if review_pending else "not_flagged"
            source = "default_pf_review_pending" if review_pending else "default_pf_no_conflict"
        payload["decision_source"] = source
        payload["review_status"] = review_status
        payload["review_pending"] = review_pending
        missing_bbox_count = sum(
            frame.get("box_xyxy_pixels") is None for frame in payload["frames"]
        )
        payload["missing_bbox_count"] = missing_bbox_count
        output_path = output_root / clip_dir.parent.name / f"{clip_dir.name}.json"
        write_json(output_path, payload)
        records.append(
            {
                "key": key,
                "episode": clip_dir.parent.name,
                "clip": clip_dir.name,
                "selected_track": payload["selected_track"],
                "decision_source": source,
                "review_status": review_status,
                "review_pending": review_pending,
                "frame_count": payload["frame_count"],
                "missing_bbox_count": missing_bbox_count,
                "track_file": str(output_path.relative_to(output_root.parent)),
            }
        )

    counts = {}
    for record in records:
        counts[record["decision_source"]] = counts.get(record["decision_source"], 0) + 1
    manifest = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset_root": str(dataset_root),
        "output_root": str(output_root),
        "clip_count": len(records),
        "decision_counts": counts,
        "review_pending_count": sum(record["review_pending"] for record in records),
        "missing_bbox_count": sum(record["missing_bbox_count"] for record in records),
        "clips": records,
    }
    write_json(output_root.parent / "final_bbox_manifest.json", manifest)
    csv_path = output_root.parent / "final_bbox_manifest.csv"
    with csv_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=records[0].keys() if records else [])
        if records:
            writer.writeheader()
            writer.writerows(records)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset_root", type=Path)
    parser.add_argument("queue", type=Path)
    parser.add_argument("output_root", type=Path)
    args = parser.parse_args()
    manifest = export_tracks(args.dataset_root, args.queue, args.output_root)
    print(
        json.dumps(
            {
                key: manifest[key]
                for key in (
                    "clip_count",
                    "decision_counts",
                    "review_pending_count",
                    "missing_bbox_count",
                )
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

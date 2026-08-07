#!/usr/bin/env python3
"""Compare every available local tracker on PerceptFlow clips."""

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

from libs.reverse_tracker_validator import validate_perceptflow_clip  # noqa: E402


TRACKERS = ("CSRT", "KCF", "MIL", "MOSSE", "TLD", "BOOSTING", "MEDIANFLOW")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset_dir", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--anchor-fraction", type=float, default=0.75)
    parser.add_argument("--iou-threshold", type=float, default=0.5)
    args = parser.parse_args()

    clips = sorted(path for path in args.dataset_dir.glob("clip_[0-9][0-9][0-9]") if path.is_dir())
    if not clips:
        raise ValueError(f"no clip_NNN directories found in {args.dataset_dir}")
    args.output_dir.mkdir(parents=True, exist_ok=True)

    benchmark = {
        "anchor_fraction": args.anchor_fraction,
        "iou_threshold": args.iou_threshold,
        "trackers": [],
    }
    for tracker in TRACKERS:
        tracker_result = _benchmark_tracker(tracker, clips, args)
        benchmark["trackers"].append(tracker_result)
        print(
            f"{tracker}: {tracker_result['status']} "
            f"pass_rate={tracker_result.get('pass_rate')} "
            f"mean_iou={tracker_result.get('mean_iou')} "
            f"fps={tracker_result.get('fps')}"
        )

    output_path = args.output_dir / "benchmark_summary.json"
    output_path.write_text(json.dumps(benchmark, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {output_path}")


def _benchmark_tracker(tracker: str, clips: list[Path], args) -> dict:
    reports = []
    elapsed = 0.0
    for clip in clips:
        cv2.setRNGSeed(0)
        started = time.perf_counter()
        try:
            report = validate_perceptflow_clip(
                clip / "frames",
                clip / "calibrated" / "results.json",
                tracker_name=tracker,
                anchor_fraction=args.anchor_fraction,
                iou_threshold=args.iou_threshold,
            )
        except ValueError as error:
            if "tracker is unavailable" in str(error):
                return {"tracker": tracker, "status": "unavailable", "error": str(error)}
            raise
        elapsed += time.perf_counter() - started
        report_path = args.output_dir / f"{clip.name}_{tracker.lower()}_report.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        reports.append((clip.name, report))

    frames = [frame for _, report in reports for frame in report["frames"] if frame["status"] != "anchor"]
    ious = [frame["iou"] for frame in frames if frame["iou"] is not None]
    pass_count = sum(frame["status"] == "pass" for frame in frames)
    failed_count = sum(frame["status"] == "tracking_failed" for frame in frames)
    return {
        "tracker": tracker,
        "status": "ok",
        "evaluated_frames": len(frames),
        "pass_count": pass_count,
        "pass_rate": round(pass_count / len(frames), 6),
        "review_count": len(frames) - pass_count,
        "tracking_failed_count": failed_count,
        "valid_tracking_count": len(ious),
        "mean_iou": round(statistics.fmean(ious), 6) if ious else None,
        "median_iou": round(statistics.median(ious), 6) if ious else None,
        "mean_iou_all_frames": round(sum(ious) / len(frames), 6),
        "elapsed_seconds": round(elapsed, 6),
        "fps": round(len(frames) / elapsed, 3),
        "clips": [
            {
                "clip": clip_name,
                "anchor_frame": report["anchor_frame"],
                "total_frames": report["total_frames"],
                "pass_count": sum(frame["status"] == "pass" for frame in report["frames"]),
                "review_count": report["review_count"],
                "tracking_failed_count": sum(
                    frame["status"] == "tracking_failed" for frame in report["frames"]
                ),
            }
            for clip_name, report in reports
        ],
    }


if __name__ == "__main__":
    main()

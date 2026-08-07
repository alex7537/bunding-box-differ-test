#!/usr/bin/env python3
"""Validate PerceptFlow boxes with fresh trackers on adjacent frame pairs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from libs.local_tracker_validator import validate_perceptflow_clip_locally  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("frames_dir", type=Path)
    parser.add_argument("results_json", type=Path)
    parser.add_argument("output_json", type=Path)
    parser.add_argument("--tracker", default="CSRT")
    parser.add_argument("--iou-threshold", type=float, default=0.5)
    args = parser.parse_args()

    report = validate_perceptflow_clip_locally(
        args.frames_dir,
        args.results_json,
        tracker_name=args.tracker,
        iou_threshold=args.iou_threshold,
    )
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"total={report['total_frames']} supported={report['supported_count']} "
        f"disagreement={report['disagreement_count']} output={args.output_json}"
    )


if __name__ == "__main__":
    main()

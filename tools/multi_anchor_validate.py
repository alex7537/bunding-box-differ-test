#!/usr/bin/env python3
"""Run multi-anchor cycle-consistency validation on one PerceptFlow clip."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from libs.multi_anchor_validator import (  # noqa: E402
    validate_perceptflow_clip_with_multi_anchors,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("frames_dir", type=Path)
    parser.add_argument("results_json", type=Path)
    parser.add_argument("output_json", type=Path)
    parser.add_argument("--tracker", default="CSRT")
    parser.add_argument("--anchor-count", type=int, default=3)
    parser.add_argument("--cycle-iou-threshold", type=float, default=0.5)
    parser.add_argument("--consensus-iou-threshold", type=float, default=0.5)
    parser.add_argument("--deviation-iou-threshold", type=float, default=0.5)
    args = parser.parse_args()

    report = validate_perceptflow_clip_with_multi_anchors(
        args.frames_dir,
        args.results_json,
        tracker_name=args.tracker,
        anchor_count=args.anchor_count,
        cycle_iou_threshold=args.cycle_iou_threshold,
        consensus_iou_threshold=args.consensus_iou_threshold,
        deviation_iou_threshold=args.deviation_iou_threshold,
    )
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"anchors={report['anchor_frames']} supported={report['supported_count']} "
        f"suspected={report['suspected_count']} "
        f"unreliable={report['tracker_unreliable_count']} output={args.output_json}"
    )


if __name__ == "__main__":
    main()

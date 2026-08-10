#!/usr/bin/env python3
"""Build a clip-level bbox correction queue from SAM2 review manifests."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Dict, Optional


STATUSES = {
    "pending_anchor_review",
    "reanchor_required",
    "sam_candidate_preferred",
    "resolved",
    "rerun_complete",
}

DEFAULT_ACTIONS = {
    "pending_anchor_review": "compare_pf_sam_and_confirm_anchor",
    "reanchor_required": "draw_human_bbox_and_rerun_sam",
    "sam_candidate_preferred": "confirm_sam_or_adjust_bbox",
    "resolved": "none",
    "rerun_complete": "review_human_anchor_propagation",
}


def load_overrides(path: Optional[Path]) -> dict:
    if path is None:
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("overrides must be a JSON object keyed by episode/clip")
    for key, value in payload.items():
        if not isinstance(value, dict):
            raise ValueError(f"override for {key} must be an object")
        status = value.get("status")
        if status not in STATUSES:
            raise ValueError(f"invalid status for {key}: {status}")
    return payload


def build_queue(review_root: Path, overrides: Optional[Dict] = None) -> dict:
    overrides = overrides or {}
    items = []
    for manifest_path in sorted(review_root.glob("*/review_manifest.json")):
        episode = manifest_path.parent.name
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for clip in manifest["clips"]:
            if clip["clip_status"] != "clip_level_conflict":
                continue
            key = f"{episode}/{clip['clip']}"
            override = overrides.get(key, {})
            status = override.get("status", "pending_anchor_review")
            frames = clip.get("conflict_review_frames") or {}
            stats = clip["conflict_stats"]
            item = {
                "key": key,
                "episode": episode,
                "clip": clip["clip"],
                "status": status,
                "recommended_action": override.get(
                    "recommended_action", DEFAULT_ACTIONS[status]
                ),
                "notes": override.get("notes", ""),
                "decision_source": override.get("decision_source", "pipeline_v4"),
                "anchor_frame": clip["anchor_frame"],
                "anchor_source": clip["anchor_source"],
                "lowest_iou_frame": frames.get("lowest_iou"),
                "divergence_start_frame": frames.get("divergence_start"),
                "before_anchor_frame": frames.get("before_anchor"),
                "after_anchor_frame": frames.get("after_anchor"),
                "review_candidate_count": clip["review_candidate_count"],
                "low_iou_ratio": stats["low_iou_ratio"],
                "longest_low_iou_run": stats["longest_low_iou_run"],
                "area_ratio_median": stats["area_ratio_median"],
                "review_manifest": str(manifest_path.relative_to(review_root)),
                "conflict_card": str(
                    (manifest_path.parent / f"{clip['clip']}_clip_conflict_overview.jpg").relative_to(
                        review_root
                    )
                ),
            }
            items.append(item)

    status_order = {
        "reanchor_required": 0,
        "sam_candidate_preferred": 1,
        "pending_anchor_review": 2,
        "rerun_complete": 3,
        "resolved": 4,
    }
    items.sort(
        key=lambda item: (
            status_order[item["status"]],
            -item["low_iou_ratio"],
            -item["review_candidate_count"],
            item["key"],
        )
    )
    counts = {status: 0 for status in sorted(STATUSES)}
    for item in items:
        counts[item["status"]] += 1
    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "review_root": str(review_root),
        "item_paths_relative_to_review_root": True,
        "summary": {"clip_count": len(items), "status_counts": counts},
        "items": items,
    }


def write_csv(queue: dict, path: Path) -> None:
    fieldnames = (
        "key", "episode", "clip", "status", "recommended_action", "decision_source",
        "anchor_frame", "anchor_source", "lowest_iou_frame", "divergence_start_frame",
        "review_candidate_count", "low_iou_ratio", "longest_low_iou_run",
        "area_ratio_median", "notes", "conflict_card", "review_manifest",
    )
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for item in queue["items"]:
            row = {key: item.get(key) for key in fieldnames}
            row["longest_low_iou_run"] = json.dumps(row["longest_low_iou_run"])
            writer.writerow(row)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("review_root", type=Path, help="directory containing episode review_v4 folders")
    parser.add_argument("output_json", type=Path)
    parser.add_argument("--output-csv", type=Path)
    parser.add_argument("--overrides", type=Path)
    args = parser.parse_args()

    queue = build_queue(args.review_root, load_overrides(args.overrides))
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(
        json.dumps(queue, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    output_csv = args.output_csv or args.output_json.with_suffix(".csv")
    write_csv(queue, output_csv)
    print(f"wrote {len(queue['items'])} clip review items to {args.output_json}")


if __name__ == "__main__":
    main()

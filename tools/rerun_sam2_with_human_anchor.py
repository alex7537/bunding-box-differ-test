#!/usr/bin/env python3
"""Rerun one SAM2 clip from a human-confirmed bbox anchor."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
from urllib import request

import cv2


def _post_json(url, payload, timeout):
    body = json.dumps(payload).encode("utf-8")
    http_request = request.Request(
        url, data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    with request.urlopen(http_request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def validate_box(box, width, height):
    if len(box) != 4 or not all(math.isfinite(value) for value in box):
        raise ValueError("bbox must contain four finite pixel values")
    x1, y1, x2, y2 = box
    if not (0 <= x1 < x2 <= width and 0 <= y1 < y2 <= height):
        raise ValueError(f"bbox must satisfy 0 <= x1 < x2 <= {width}, 0 <= y1 < y2 <= {height}")
    return [float(value) for value in box]


def rerun_with_human_anchor(
    clip_dir,
    result_dir,
    anchor_frame,
    box_xyxy_pixels,
    sam_url,
    timeout=600.0,
    force=False,
    anchor_review_result="anchor_corrected",
    attribution="ambiguous",
    error_content="other",
    multi_parcel="unknown",
    reviewed_by="unknown",
):
    if anchor_review_result not in {"anchor_confirmed", "anchor_corrected"}:
        raise ValueError("anchor review result must be anchor_confirmed or anchor_corrected")
    if attribution not in {
        "pf_wrong_smooth", "pf_wrong_jump", "sam_wrong_anchor",
        "sam_identity_switch", "both_wrong", "ambiguous"
    }:
        raise ValueError("invalid attribution")
    if multi_parcel not in {"true", "false", "unknown"}:
        raise ValueError("multi_parcel must be true, false, or unknown")
    frame_paths = sorted((clip_dir / "frames").glob("frame_*.jpg"))
    if not frame_paths:
        raise ValueError(f"no frames found in {clip_dir / 'frames'}")
    if not 1 <= anchor_frame <= len(frame_paths):
        raise ValueError(f"anchor frame must be between 1 and {len(frame_paths)}")
    image = cv2.imread(str(frame_paths[anchor_frame - 1]))
    if image is None:
        raise ValueError(f"failed to read anchor frame {frame_paths[anchor_frame - 1]}")
    height, width = image.shape[:2]
    box = validate_box(box_xyxy_pixels, width, height)
    output_path = result_dir / f"{clip_dir.name}_sam2.1_tiny_human_raw.json"
    if output_path.exists() and not force:
        raise FileExistsError(f"human SAM result already exists: {output_path}; use --force to replace it")

    payload = {
        "frames_dir": str((clip_dir / "frames").resolve()),
        "anchor_frame": anchor_frame,
        "anchor_source": "human",
        "box_xyxy_pixels": box,
    }
    result = _post_json(
        f"{sam_url.rstrip('/')}/api/v1/mot/sam2/propagate", payload, timeout
    )
    if str(result.get("status")) != "200":
        raise RuntimeError(result.get("message") or "SAM2 request failed")
    if result.get("frame_count") != len(frame_paths):
        raise RuntimeError("SAM2 response frame count does not match the clip")
    if result.get("anchor_source") != "human":
        raise RuntimeError("SAM2 response did not preserve anchor_source=human")

    result_dir.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    anchor_record = {
        "clip": clip_dir.name,
        "anchor_frame": anchor_frame,
        "anchor_source": "human",
        "anchor_review_result": anchor_review_result,
        "attribution": attribution,
        "error_content": error_content,
        "multi_parcel": multi_parcel,
        "reviewed_by": reviewed_by,
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
        "box_xyxy_pixels": box,
        "sam_result": output_path.name,
    }
    (result_dir / f"{clip_dir.name}_human_anchor.json").write_text(
        json.dumps(anchor_record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return output_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset_dir", type=Path, help="episode directory containing clip_NNN")
    parser.add_argument("result_dir", type=Path, help="directory containing original SAM raw results")
    parser.add_argument("clip", help="clip name, for example clip_002")
    parser.add_argument("--anchor-frame", type=int, required=True, help="1-based human anchor frame")
    parser.add_argument(
        "--bbox", type=float, nargs=4, required=True, metavar=("X1", "Y1", "X2", "Y2"),
        help="human bbox in pixel xyxy coordinates",
    )
    parser.add_argument("--sam2-url", default="http://127.0.0.1:5001")
    parser.add_argument("--timeout", type=float, default=600.0)
    parser.add_argument(
        "--anchor-review-result", required=True,
        choices=("anchor_confirmed", "anchor_corrected"),
    )
    parser.add_argument(
        "--attribution", required=True,
        choices=(
            "pf_wrong_smooth", "pf_wrong_jump", "sam_wrong_anchor",
            "sam_identity_switch", "both_wrong", "ambiguous",
        ),
    )
    parser.add_argument(
        "--error-content", required=True,
        choices=(
            "parcel_pile", "robot_arm", "adjacent_parcel", "oversized_region",
            "conveyor_background", "mixed_target", "other", "none",
        ),
    )
    parser.add_argument("--multi-parcel", required=True, choices=("true", "false", "unknown"))
    parser.add_argument("--reviewed-by", required=True)
    parser.add_argument("--force", action="store_true", help="replace an existing human-anchor result")
    args = parser.parse_args()

    clip_dir = args.dataset_dir / args.clip
    if not clip_dir.is_dir():
        raise ValueError(f"clip does not exist: {clip_dir}")
    output = rerun_with_human_anchor(
        clip_dir, args.result_dir, args.anchor_frame, args.bbox,
        args.sam2_url, timeout=args.timeout, force=args.force,
        anchor_review_result=args.anchor_review_result, attribution=args.attribution,
        error_content=args.error_content, multi_parcel=args.multi_parcel,
        reviewed_by=args.reviewed_by,
    )
    print(f"wrote human-anchor SAM result: {output}")
    print("rerun generate_sam2_review_pack.py to refresh the review decisions")


if __name__ == "__main__":
    main()

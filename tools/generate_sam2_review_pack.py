#!/usr/bin/env python3
"""Build a human-review image pack from PerceptFlow and SAM2 boxes."""

import argparse
import csv
import json
from pathlib import Path
import statistics

import cv2
import numpy as np


HUMAN_GT_VALUES = ("PF_CORRECT", "SAM_CORRECT", "BOTH_OK", "BOTH_WRONG", "IGNORE")


def box_iou(left, right):
    if left is None or right is None:
        return 0.0
    x1, y1 = max(left[0], right[0]), max(left[1], right[1])
    x2, y2 = min(left[2], right[2]), min(left[3], right[3])
    intersection = max(0, x2 - x1) * max(0, y2 - y1)
    left_area = max(0, left[2] - left[0]) * max(0, left[3] - left[1])
    right_area = max(0, right[2] - right[0]) * max(0, right[3] - right[1])
    union = left_area + right_area - intersection
    return intersection / union if union else 0.0


def contiguous_ranges(indices):
    if not indices:
        return []
    ranges = []
    start = previous = indices[0]
    for index in indices[1:]:
        if index != previous + 1:
            ranges.append((start, previous))
            start = index
        previous = index
    ranges.append((start, previous))
    return ranges


def load_grasp_windows(path):
    if path is None:
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    windows = payload.get("clips", payload)
    if not isinstance(windows, dict):
        raise ValueError("grasp windows must be a clip-to-ranges object")
    for clip, ranges in windows.items():
        if not isinstance(ranges, list):
            raise ValueError(f"grasp windows for {clip} must be a list")
        for value in ranges:
            if not isinstance(value, list) or len(value) != 2 or not 1 <= value[0] <= value[1]:
                raise ValueError(f"invalid grasp window for {clip}: {value}")
    return windows


def frame_in_grasp_window(windows, clip, frame_index):
    if windows is None:
        return None
    return any(start <= frame_index <= end for start, end in windows.get(clip, []))


def draw_box(image, box, color, label, thickness):
    if box is None:
        return
    x1, y1, x2, y2 = (int(round(value)) for value in box)
    cv2.rectangle(image, (x1, y1), (x2, y2), color, thickness)
    text_size, _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.65, 2)
    text_width, text_height = text_size
    top = max(0, y1 - text_height - 10)
    cv2.rectangle(image, (x1, top), (x1 + text_width + 8, y1), color, -1)
    cv2.putText(image, label, (x1 + 4, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2)


def render_frame(image, item):
    canvas = image.copy()
    draw_box(canvas, item["pf_box_xyxy_pixels"], (0, 255, 0), "PF", 7)
    draw_box(canvas, item["sam_box_xyxy_pixels"], (255, 0, 0), "SAM", 4)
    height, width = canvas.shape[:2]
    cv2.rectangle(canvas, (0, 0), (width, 78), (0, 0, 0), -1)
    cv2.putText(
        canvas,
        f'{item["clip"]} frame={item["frame_index"]} IoU={item["pf_sam_iou"]:.3f}',
        (12, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.72, (255, 255, 255), 2, cv2.LINE_AA,
    )
    reasons = ", ".join(item["reasons"])
    cv2.putText(
        canvas,
        f"green=PF blue=SAM | {reasons} | ignore legacy red box",
        (12, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2, cv2.LINE_AA,
    )
    return canvas


def make_sheet(images, output, columns=4, cell_size=(640, 360)):
    if not images:
        return
    cells = [cv2.resize(image, cell_size) for image in images]
    blank = np.zeros_like(cells[0])
    while len(cells) % columns:
        cells.append(blank.copy())
    rows = [np.hstack(cells[index:index + columns]) for index in range(0, len(cells), columns)]
    cv2.imwrite(str(output), np.vstack(rows), [cv2.IMWRITE_JPEG_QUALITY, 92])


def calculate_conflict_stats(
    agreements, pf_boxes, sam_boxes, anchor_frame, in_scope, iou_threshold
):
    eligible_indices = [
        index for index, scoped in enumerate(in_scope)
        if index + 1 != anchor_frame and scoped is not False
    ]
    low_indices = [index for index in eligible_indices if agreements[index] < iou_threshold]
    ratio = 0.0 if not eligible_indices else len(low_indices) / len(eligible_indices)

    runs = []
    current = []
    for index in low_indices:
        frame_number = index + 1
        if current and not (
            frame_number == current[-1] + 1
            or frame_number == current[-1] + 2 == anchor_frame + 1
        ):
            runs.append(current)
            current = []
        current.append(frame_number)
    if current:
        runs.append(current)
    longest = max(runs, key=len, default=[])

    area_ratios = []
    for index in eligible_indices:
        pf_box, sam_box = pf_boxes[index], sam_boxes[index]
        if pf_box is None or sam_box is None:
            continue
        pf_area = max(0.0, pf_box[2] - pf_box[0]) * max(0.0, pf_box[3] - pf_box[1])
        sam_area = max(0.0, sam_box[2] - sam_box[0]) * max(0.0, sam_box[3] - sam_box[1])
        if sam_area:
            area_ratios.append(pf_area / sam_area)
    return {
        "low_iou_ratio": round(ratio, 6),
        "evaluated_frame_count": len(eligible_indices),
        "longest_low_iou_run": [] if not longest else [longest[0], longest[-1]],
        "longest_low_iou_run_length": len(longest),
        "area_ratio_median": (
            None if not area_ratios else round(statistics.median(area_ratios), 6)
        ),
    }


def anchor_disagreement_ratio(agreements, anchor_frame, in_scope, iou_threshold):
    stats = calculate_conflict_stats(
        agreements, [None] * len(agreements), [None] * len(agreements),
        anchor_frame, in_scope, iou_threshold,
    )
    return stats["low_iou_ratio"], stats["evaluated_frame_count"]


def is_clip_level_conflict(stats, ratio_threshold, min_run, min_frames):
    return (
        stats["evaluated_frame_count"] >= min_frames
        and stats["low_iou_ratio"] >= ratio_threshold
    ) or stats["longest_low_iou_run_length"] >= min_run


def select_sam_result(result_dir, clip):
    human_result = result_dir / f"{clip}_sam2.1_tiny_human_raw.json"
    if human_result.exists():
        return human_result
    return result_dir / f"{clip}_sam2.1_tiny_raw.json"


def load_human_anchor_record(result_dir, clip):
    path = result_dir / f"{clip}_human_anchor.json"
    return None if not path.exists() else json.loads(path.read_text(encoding="utf-8"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset_dir", type=Path)
    parser.add_argument("result_dir", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--iou-threshold", type=float, default=0.5)
    parser.add_argument("--clip-conflict-ratio", type=float, default=0.6)
    parser.add_argument("--clip-conflict-min-run", type=int, default=8)
    parser.add_argument("--clip-conflict-min-frames", type=int, default=5)
    parser.add_argument("--grasp-windows", type=Path, default=None)
    parser.add_argument("--multi-parcel-clips", nargs="*", default=())
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    frame_output = args.output_dir / "frames"
    frame_output.mkdir(exist_ok=True)

    grasp_windows = load_grasp_windows(args.grasp_windows)
    multi_parcel_clips = set(args.multi_parcel_clips)
    manifest = {
        "schema_version": 4,
        "iou_threshold": args.iou_threshold,
        "auto_adoption_enabled": False,
        "detector_evidence_available": False,
        "human_gt_values": HUMAN_GT_VALUES,
        "grasp_windows_source": None if args.grasp_windows is None else str(args.grasp_windows),
        "clips": [],
        "frames": [],
    }
    rendered_by_clip = {}
    source_by_key = {}

    for clip_dir in sorted(args.dataset_dir.glob("clip_[0-9][0-9][0-9]")):
        name = clip_dir.name
        frame_paths = sorted((clip_dir / "frames").glob("frame_*.jpg"))
        references = json.loads((clip_dir / "calibrated" / "results.json").read_text())
        sam_result_path = select_sam_result(args.result_dir, name)
        sam_payload = json.loads(sam_result_path.read_text())
        sam_frames = sam_payload["frames"]
        anchor_source = sam_payload.get("anchor_source")
        if anchor_source not in {"pf", "human", "redetection"}:
            raise ValueError(f"missing or invalid anchor_source in SAM result for {name}")
        propagation_source = f"sam_from_{anchor_source}_anchor"
        multi_parcel = name in multi_parcel_clips
        if not len(frame_paths) == len(references) == len(sam_frames):
            raise ValueError(f"frame count mismatch for {name}")

        height, width = cv2.imread(str(frame_paths[0])).shape[:2]
        pf_boxes = [
            None if item.get("box") is None else [
                item["box"][0] * width / 1000,
                item["box"][1] * height / 1000,
                item["box"][2] * width / 1000,
                item["box"][3] * height / 1000,
            ]
            for item in references
        ]
        sam_boxes = [item["box_xyxy_pixels"] for item in sam_frames]
        agreements = [box_iou(pf, sam) for pf, sam in zip(pf_boxes, sam_boxes)]
        pf_adjacent = [1.0] + [box_iou(pf_boxes[i - 1], pf_boxes[i]) for i in range(1, len(pf_boxes))]
        sam_adjacent = [1.0] + [box_iou(sam_boxes[i - 1], sam_boxes[i]) for i in range(1, len(sam_boxes))]
        in_scope = [
            frame_in_grasp_window(grasp_windows, name, frame_number)
            for frame_number in range(1, len(frame_paths) + 1)
        ]
        conflict_stats = calculate_conflict_stats(
            agreements, pf_boxes, sam_boxes, sam_payload["anchor_frame"],
            in_scope, args.iou_threshold,
        )
        clip_level_conflict = is_clip_level_conflict(
            conflict_stats, args.clip_conflict_ratio,
            args.clip_conflict_min_run, args.clip_conflict_min_frames,
        )
        human_anchor = load_human_anchor_record(args.result_dir, name)
        anchor_review_result = "pending" if human_anchor is None else human_anchor["anchor_review_result"]
        anchor_review = {
            "result": anchor_review_result,
            "reviewed_frame": (
                sam_payload["anchor_frame"] if human_anchor is None else human_anchor["anchor_frame"]
            ),
            "anchor_source_after": (
                "human" if anchor_review_result in {"anchor_confirmed", "anchor_corrected"}
                else None
            ),
            "reviewed_by": None if human_anchor is None else human_anchor.get("reviewed_by"),
            "reviewed_at": None if human_anchor is None else human_anchor.get("reviewed_at"),
        }
        attribution = "pending" if human_anchor is None else human_anchor["attribution"]
        error_content = None if human_anchor is None else human_anchor.get("error_content")
        multi_parcel_review = None if human_anchor is None else human_anchor.get("multi_parcel")

        candidate_indices = []
        all_candidate_indices = []
        excluded_count = 0
        for index in range(len(frame_paths)):
            frame_number = index + 1
            reasons = []
            if pf_boxes[index] is None:
                reasons.append("pf_box_missing")
            if sam_boxes[index] is None:
                reasons.append("sam_box_missing")
            if frame_number != sam_payload["anchor_frame"] and agreements[index] < args.iou_threshold:
                reasons.append("severe_disagreement" if agreements[index] < 0.3 else "low_agreement")
            if index and pf_adjacent[index] < 0.3 and sam_adjacent[index] >= 0.5:
                reasons.append("pf_temporal_jump")
            if index and sam_adjacent[index] < 0.3:
                reasons.append("sam_temporal_jump")
            if not reasons:
                continue

            grasp_active = in_scope[index]
            all_candidate_indices.append(frame_number)
            item = {
                "clip": name,
                "frame_index": frame_number,
                "frame_name": frame_paths[index].name,
                "anchor_frame": sam_payload["anchor_frame"],
                "anchor_source": anchor_source,
                "sam_source": propagation_source,
                "multi_parcel": multi_parcel,
                "grasp_active": grasp_active,
                "pf_sam_iou": round(agreements[index], 6),
                "pf_adjacent_iou": round(pf_adjacent[index], 6),
                "sam_adjacent_iou": round(sam_adjacent[index], 6),
                "pf_box_xyxy_pixels": (
                    None if pf_boxes[index] is None else
                    [round(value, 2) for value in pf_boxes[index]]
                ),
                "sam_box_xyxy_pixels": sam_boxes[index],
                "det_box_xyxy_pixels": None,
                "det_iou_pf": None,
                "det_iou_sam": None,
                "reasons": reasons,
                "decision": (
                    "excluded_by_grasp_window" if grasp_active is False else
                    "anchor_confirmation_required" if (
                        clip_level_conflict and anchor_review["result"] == "pending"
                    ) else "reanchor_required" if (
                        clip_level_conflict and anchor_review["result"] == "anchor_rejected"
                    ) else
                    "pending_human_review"
                ),
                "human_gt": "",
                "target_identity_clear": None,
                "notes": "",
            }
            manifest["frames"].append(item)
            if grasp_active is False:
                excluded_count += 1
                continue

            candidate_indices.append(frame_number)
            source = cv2.imread(str(frame_paths[index]))
            rendered = render_frame(source, item)
            output_name = f"{name}_frame_{frame_number:06d}_iou_{agreements[index]:.3f}.jpg"
            cv2.imwrite(str(frame_output / output_name), rendered, [cv2.IMWRITE_JPEG_QUALITY, 94])
            rendered_by_clip.setdefault(name, []).append(rendered)
            source_by_key[(name, frame_number)] = rendered

        ranges = contiguous_ranges(candidate_indices)
        conflict_review_frames = None
        if clip_level_conflict:
            scoped_indices = [
                index for index, scoped in enumerate(in_scope)
                if index + 1 != sam_payload["anchor_frame"] and scoped is not False
            ]
            lowest_index = min(scoped_indices, key=lambda index: agreements[index])
            anchor_index = sam_payload["anchor_frame"] - 1
            divergence_start = conflict_stats["longest_low_iou_run"][0]
            conflict_review_frames = {
                "anchor": anchor_index + 1,
                "lowest_iou": lowest_index + 1,
                "before_anchor": max(1, anchor_index),
                "after_anchor": min(len(frame_paths), anchor_index + 2),
                "divergence_start": divergence_start,
            }
            context_images = []
            for role, frame_number in conflict_review_frames.items():
                index = frame_number - 1
                context_item = {
                    "clip": name,
                    "frame_index": frame_number,
                    "pf_sam_iou": agreements[index],
                    "pf_box_xyxy_pixels": pf_boxes[index],
                    "sam_box_xyxy_pixels": sam_boxes[index],
                    "reasons": [role],
                }
                context_images.append(render_frame(cv2.imread(str(frame_paths[index])), context_item))
            make_sheet(
                context_images, args.output_dir / f"{name}_clip_conflict_overview.jpg",
                columns=5,
            )
        manifest["clips"].append(
            {
                "clip": name,
                "anchor_frame": sam_payload["anchor_frame"],
                "anchor_source": anchor_source,
                "propagation_source": propagation_source,
                "sam_result_path": str(sam_result_path),
                "multi_parcel": multi_parcel,
                "clip_status": "clip_level_conflict" if clip_level_conflict else "frame_review",
                "anchor_review": anchor_review,
                "conflict_stats": conflict_stats,
                "attribution": attribution,
                "error_content": error_content,
                "multi_parcel_review": multi_parcel_review,
                "review_mode": (
                    "anchor_confirmation" if (
                        clip_level_conflict and anchor_review["result"] == "pending"
                    ) else "anchor_correction" if (
                        clip_level_conflict and anchor_review["result"] == "anchor_rejected"
                    ) else "resolved_clip_conflict" if clip_level_conflict else "frame_review"
                ),
                "recommended_action": (
                    "confirm_or_correct_anchor" if (
                        clip_level_conflict and anchor_review["result"] == "pending"
                    ) else "draw_human_bbox_and_rerun_sam" if (
                        clip_level_conflict and anchor_review["result"] == "anchor_rejected"
                    ) else "review_propagated_result" if clip_level_conflict else "review_frames"
                ),
                "human_action_count": 1 if clip_level_conflict else len(candidate_indices),
                "conflict_review_frames": conflict_review_frames,
                "all_candidate_count": len(all_candidate_indices),
                "review_candidate_count": len(candidate_indices),
                "excluded_by_grasp_window_count": excluded_count,
                "candidate_ranges": ranges,
            }
        )
        make_sheet(rendered_by_clip.get(name, []), args.output_dir / f"{name}_review_sheet.jpg")

    manifest["summary"] = {
        "clip_level_conflict_count": sum(
            clip["clip_status"] == "clip_level_conflict" for clip in manifest["clips"]
        ),
        "frame_review_clip_count": sum(
            clip["review_mode"] == "frame_review" for clip in manifest["clips"]
        ),
        "human_action_count": sum(clip["human_action_count"] for clip in manifest["clips"]),
    }

    representatives = []
    for clip in manifest["clips"]:
        candidates = [
            item for item in manifest["frames"]
            if item["clip"] == clip["clip"] and item["grasp_active"] is not False
        ]
        for start, end in clip["candidate_ranges"]:
            interval = [item for item in candidates if start <= item["frame_index"] <= end]
            representative = min(interval, key=lambda item: item["pf_sam_iou"])
            representatives.append(source_by_key[(clip["clip"], representative["frame_index"])])
    make_sheet(representatives, args.output_dir / "review_overview_interval_worst.jpg")
    make_sheet(
        [
            source_by_key[(item["clip"], item["frame_index"])]
            for item in manifest["frames"] if item["grasp_active"] is not False
        ],
        args.output_dir / "review_all_candidates.jpg",
    )

    (args.output_dir / "review_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    with (args.output_dir / "review_candidates.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=(
            "clip", "frame_index", "anchor_frame", "anchor_source", "sam_source", "multi_parcel",
            "grasp_active", "pf_sam_iou", "pf_adjacent_iou", "sam_adjacent_iou", "reasons",
            "decision", "human_gt", "target_identity_clear", "notes",
        ))
        writer.writeheader()
        for item in manifest["frames"]:
            row = {key: item[key] for key in writer.fieldnames}
            row["reasons"] = ";".join(row["reasons"])
            writer.writerow(row)

    range_lines = [
        f'- {clip["clip"]}: mode={clip["review_mode"]}, action={clip["recommended_action"]}, '
        f'review={clip["review_candidate_count"]}, '
        f'excluded={clip["excluded_by_grasp_window_count"]}, ranges={clip["candidate_ranges"]}'
        for clip in manifest["clips"]
    ]
    readme = """# PF / SAM 人工复查包

绿色粗框为 PerceptFlow，蓝色框为 SAM2.1 Tiny。底图可能保留上游红色框，请忽略红框。

候选条件：PF/SAM IoU < 0.5，或 PF/SAM 出现相邻帧 IoU < 0.3 的时序跳变。
这些帧仅表示需要人工判断，不能直接认定 PF 或 SAM 错误。
自动采用保持关闭。只有 `human_gt` 人工确认后，才可统计规则准确率。
当低 IoU 比例至少 60%，或最长连续低 IoU 区间至少 8 帧时，标记为
`clip_level_conflict`。这只表示 PF/SAM 存在持续冲突，不自动归因。
人工先确认当前锚点：锚点正确则重点复查 PF，锚点错误则重画 bbox 并重新运行 SAM。

CSV 中请填写 `human_gt`：PF_CORRECT / SAM_CORRECT / BOTH_OK / BOTH_WRONG / IGNORE。

## 候选范围

""" + "\n".join(range_lines) + "\n"
    (args.output_dir / "README.md").write_text(readme, encoding="utf-8")
    print(f'wrote {len(manifest["frames"])} review frames to {args.output_dir}')


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Compare three PF-anchor SAM2 tracks against the human-selected final track."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import statistics
import time
from urllib import request

import cv2


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


def choose_anchor_frame(references, fraction):
    requested = int((len(references) - 1) * fraction)
    valid = [index for index, item in enumerate(references) if item.get("box") is not None]
    if not valid:
        raise ValueError("PF track has no valid anchor bbox")
    selected = min(valid, key=lambda index: (abs(index - requested), index))
    return selected + 1


def normalized_to_pixels(box, width, height):
    if box is None:
        return None
    return [
        float(box[0]) * width / 1000,
        float(box[1]) * height / 1000,
        float(box[2]) * width / 1000,
        float(box[3]) * height / 1000,
    ]


def post_json(url, payload, timeout):
    body = json.dumps(payload).encode("utf-8")
    http_request = request.Request(
        url, data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    with request.urlopen(http_request, timeout=timeout) as response:
        result = json.loads(response.read().decode("utf-8"))
    if str(result.get("status")) != "200":
        raise RuntimeError(result.get("message") or "SAM2 request failed")
    return result


def summarize(track, reference):
    ious = [box_iou(box, target) for box, target in zip(track, reference)]
    return {
        "iou_mean": round(statistics.mean(ious), 6),
        "iou_median": round(statistics.median(ious), 6),
        "iou_rate_at_0_5": round(sum(value >= 0.5 for value in ious) / len(ious), 6),
        "missing_bbox_count": sum(box is None for box in track),
    }


def select_consensus_anchor(anchor_frames, tracks, threshold=0.7):
    support = {}
    supported_pairs = []
    for frame in anchor_frames:
        comparisons = []
        for other in anchor_frames:
            if other == frame:
                continue
            values = [box_iou(left, right) for left, right in zip(tracks[frame], tracks[other])]
            comparisons.append(statistics.mean(values))
        support[frame] = statistics.mean(comparisons)
    for left_index, left in enumerate(anchor_frames):
        for right in anchor_frames[left_index + 1:]:
            values = [box_iou(a, b) for a, b in zip(tracks[left], tracks[right])]
            if statistics.median(values) >= threshold:
                supported_pairs.append((left, right))
    candidates = {frame for pair in supported_pairs for frame in pair}
    primary_anchor = anchor_frames[-1]
    selected = None
    if primary_anchor in candidates:
        selected = primary_anchor
    elif candidates:
        selected = max(candidates, key=lambda frame: (support[frame], frame))
    return (
        selected,
        {str(frame): round(score, 6) for frame, score in support.items()},
        [list(pair) for pair in supported_pairs],
    )


def draw_box(image, box, color, label):
    if box is None:
        return
    x1, y1, x2, y2 = (int(round(value)) for value in box)
    cv2.rectangle(image, (x1, y1), (x2, y2), color, 2)
    cv2.putText(image, label, (x1, max(18, y1 - 5)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)


def render_video(frame_paths, pf_boxes, tracks, reference, output, fps):
    first = cv2.imread(str(frame_paths[0]))
    height, width = first.shape[:2]
    writer = cv2.VideoWriter(
        str(output), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height)
    )
    if not writer.isOpened():
        raise RuntimeError(f"failed to create video: {output}")
    colors = [(0, 0, 255), (255, 100, 0), (0, 255, 255)]
    for index, frame_path in enumerate(frame_paths):
        image = cv2.imread(str(frame_path))
        draw_box(image, pf_boxes[index], (0, 220, 0), "PF")
        for color, (anchor_frame, track) in zip(colors, sorted(tracks.items())):
            draw_box(image, track[index], color, f"SAM@{anchor_frame}")
        draw_box(image, reference[index], (255, 0, 255), "FINAL")
        cv2.putText(
            image,
            f"frame={index + 1}",
            (12, 28),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (255, 255, 255),
            2,
        )
        writer.write(image)
    writer.release()


def load_final_track(final_track_root, episode, clip):
    path = final_track_root / episode / f"{clip}.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    return path, [item.get("box_xyxy_pixels") for item in payload["frames"]]


def benchmark_clip(args, key):
    episode, clip = key.split("/", 1)
    clip_dir = args.dataset_root / episode / clip
    frame_paths = sorted((clip_dir / "frames").glob("frame_*.jpg"))
    references = sorted(
        json.loads((clip_dir / "calibrated" / "results.json").read_text()),
        key=lambda item: int(item["frame_index"]),
    )
    first = cv2.imread(str(frame_paths[0]))
    height, width = first.shape[:2]
    pf_boxes = [normalized_to_pixels(item.get("box"), width, height) for item in references]
    final_path, final_track = load_final_track(args.final_track_root, episode, clip)
    if not len(frame_paths) == len(references) == len(final_track):
        raise ValueError(f"frame count mismatch: {key}")

    anchor_frames = []
    tracks = {}
    raw_dir = args.output_dir / episode / clip / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    for fraction in args.anchor_fractions:
        anchor_frame = choose_anchor_frame(references, fraction)
        if anchor_frame in tracks:
            continue
        anchor_frames.append(anchor_frame)
        raw_path = raw_dir / f"anchor_{anchor_frame:06d}.json"
        if args.reuse_raw and raw_path.is_file():
            result = json.loads(raw_path.read_text(encoding="utf-8"))
        else:
            result = post_json(
                f"{args.sam2_url.rstrip('/')}/api/v1/mot/sam2/propagate",
                {
                    "frames_dir": str(args.service_dataset_root / episode / clip / "frames"),
                    "anchor_frame": anchor_frame,
                    "anchor_source": "pf",
                    "box_xyxy_pixels": pf_boxes[anchor_frame - 1],
                },
                args.timeout,
            )
            raw_path.write_text(
                json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
        tracks[anchor_frame] = [item.get("box_xyxy_pixels") for item in result["frames"]]

    pairwise = {}
    for left_index, left in enumerate(anchor_frames):
        for right in anchor_frames[left_index + 1:]:
            pairwise[f"{left}-{right}"] = summarize(tracks[left], tracks[right])
    consensus_anchor, support, supported_pairs = select_consensus_anchor(
        anchor_frames, tracks, args.consensus_iou_threshold
    )
    final_metrics = {
        str(frame): summarize(track, final_track) for frame, track in tracks.items()
    }
    best_final_anchor = max(
        anchor_frames, key=lambda frame: final_metrics[str(frame)]["iou_mean"]
    )
    clip_output = args.output_dir / episode / clip
    render_video(
        frame_paths,
        pf_boxes,
        tracks,
        final_track,
        clip_output / "multi_anchor_comparison.mp4",
        args.fps,
    )
    report = {
        "key": key,
        "frame_count": len(frame_paths),
        "anchor_frames": anchor_frames,
        "final_track": str(final_path),
        "final_track_source": json.loads(final_path.read_text())["decision_source"],
        "pairwise_sam_metrics": pairwise,
        "consensus_support": support,
        "consensus_iou_threshold": args.consensus_iou_threshold,
        "supported_anchor_pairs": supported_pairs,
        "consensus_status": "supported" if consensus_anchor is not None else "no_consensus",
        "consensus_anchor": consensus_anchor,
        "best_anchor_against_final": best_final_anchor,
        "anchor_vs_final_metrics": final_metrics,
        "consensus_matches_best_final": (
            consensus_anchor is not None and consensus_anchor == best_final_anchor
        ),
        "video": str(clip_output / "multi_anchor_comparison.mp4"),
    }
    (clip_output / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--service-dataset-root", type=Path, required=True)
    parser.add_argument("--final-track-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--clips", nargs="+", required=True)
    parser.add_argument("--anchor-fractions", type=float, nargs="+", default=(0.25, 0.5, 0.75))
    parser.add_argument("--sam2-url", default="http://127.0.0.1:5001")
    parser.add_argument("--timeout", type=float, default=600.0)
    parser.add_argument("--fps", type=float, default=10.0)
    parser.add_argument("--consensus-iou-threshold", type=float, default=0.7)
    parser.add_argument("--reuse-raw", action="store_true")
    args = parser.parse_args()
    if any(not 0 <= fraction <= 1 for fraction in args.anchor_fractions):
        raise ValueError("anchor fractions must be between zero and one")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    reports = [benchmark_clip(args, key) for key in args.clips]
    summary = {
        "model": "sam2.1_hiera_tiny",
        "method": "three_pf_anchor_bidirectional_propagation",
        "clip_count": len(reports),
        "anchor_fractions": args.anchor_fractions,
        "consensus_supported_count": sum(
            item["consensus_status"] == "supported" for item in reports
        ),
        "consensus_matches_best_final_count": sum(
            item["consensus_matches_best_final"] for item in reports
        ),
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "clips": reports,
    }
    (args.output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Benchmark bidirectional Cutie propagation with SAM and rectangle anchor masks."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import statistics
import time

import cv2
import numpy as np
from PIL import Image


def box_iou(left, right) -> float:
    if left is None or right is None:
        return 0.0
    intersection_width = max(0.0, min(left[2], right[2]) - max(left[0], right[0]))
    intersection_height = max(0.0, min(left[3], right[3]) - max(left[1], right[1]))
    intersection = intersection_width * intersection_height
    left_area = max(0.0, left[2] - left[0]) * max(0.0, left[3] - left[1])
    right_area = max(0.0, right[2] - right[0]) * max(0.0, right[3] - right[1])
    union = left_area + right_area - intersection
    return 0.0 if union <= 0 else intersection / union


def normalized_to_pixel_xyxy(box, width: int, height: int) -> list[int]:
    values = [
        round(float(box[0]) * width / 1000),
        round(float(box[1]) * height / 1000),
        round(float(box[2]) * width / 1000),
        round(float(box[3]) * height / 1000),
    ]
    values[0] = min(max(values[0], 0), width - 1)
    values[1] = min(max(values[1], 0), height - 1)
    values[2] = min(max(values[2], values[0] + 1), width)
    values[3] = min(max(values[3], values[1] + 1), height)
    return values


def mask_to_normalized_box(mask: np.ndarray):
    ys, xs = np.where(mask > 0)
    if not len(xs):
        return None
    height, width = mask.shape
    return [
        float(xs.min()) * 1000 / width,
        float(ys.min()) * 1000 / height,
        float(xs.max() + 1) * 1000 / width,
        float(ys.max() + 1) * 1000 / height,
    ]


def rectangle_mask(box, width: int, height: int) -> np.ndarray:
    x1, y1, x2, y2 = normalized_to_pixel_xyxy(box, width, height)
    mask = np.zeros((height, width), dtype=np.uint8)
    mask[y1:y2, x1:x2] = 1
    return mask


def load_clip(clip_dir: Path):
    frame_paths = sorted((clip_dir / "frames").glob("frame_*.jpg"))
    reference = sorted(
        json.loads((clip_dir / "calibrated" / "results.json").read_text()),
        key=lambda item: int(item["frame_index"]),
    )
    if not frame_paths or len(frame_paths) != len(reference):
        raise ValueError(f"frame/result mismatch in {clip_dir}")
    return frame_paths, [item["box"] for item in reference]


def load_sam_boxes(raw_path: Path) -> list[list[float] | None]:
    payload = json.loads(raw_path.read_text())
    boxes = []
    for frame in payload["frames"]:
        box = frame["box_xyxy_pixels"]
        if box is None:
            boxes.append(None)
            continue
        width = int(payload.get("image_width", 0))
        height = int(payload.get("image_height", 0))
        if not width or not height:
            boxes.append(box)
        else:
            boxes.append([box[0] * 1000 / width, box[1] * 1000 / height,
                          box[2] * 1000 / width, box[3] * 1000 / height])
    return boxes


def sam_boxes_from_raw(raw_path: Path, frame_paths: list[Path]):
    payload = json.loads(raw_path.read_text())
    boxes = []
    for frame_path, frame in zip(frame_paths, payload["frames"]):
        box = frame["box_xyxy_pixels"]
        if box is None:
            boxes.append(None)
            continue
        with Image.open(frame_path) as image:
            width, height = image.size
        boxes.append([box[0] * 1000 / width, box[1] * 1000 / height,
                      box[2] * 1000 / width, box[3] * 1000 / height])
    return boxes


def run_branch(model, frame_paths, anchor_index, anchor_mask, indices, max_internal_size):
    import torch
    from torchvision.transforms.functional import to_tensor
    from cutie.inference.inference_core import InferenceCore

    processor = InferenceCore(model, cfg=model.cfg)
    processor.max_internal_size = max_internal_size
    outputs = {}
    sequence = [anchor_index, *indices]
    for position, index in enumerate(sequence):
        with Image.open(frame_paths[index]) as image:
            tensor = to_tensor(image.convert("RGB")).cuda().float()
        probability = processor.step(
            tensor,
            torch.from_numpy(anchor_mask).cuda() if position == 0 else None,
            objects=[1] if position == 0 else None,
            end=position == len(sequence) - 1,
        )
        mask = processor.output_prob_to_mask(probability).cpu().numpy().astype(np.uint8)
        outputs[index] = mask_to_normalized_box(mask)
    return outputs


def run_cutie(model, frame_paths, anchor_index, anchor_mask, max_internal_size):
    import torch

    torch.cuda.reset_peak_memory_stats()
    started = time.perf_counter()
    with torch.inference_mode(), torch.autocast("cuda", dtype=torch.float16):
        backward = run_branch(
            model, frame_paths, anchor_index, anchor_mask,
            list(range(anchor_index - 1, -1, -1)), max_internal_size,
        )
        forward = run_branch(
            model, frame_paths, anchor_index, anchor_mask,
            list(range(anchor_index + 1, len(frame_paths))), max_internal_size,
        )
    torch.cuda.synchronize()
    elapsed = time.perf_counter() - started
    outputs = {**backward, **forward}
    boxes = [outputs.get(index) for index in range(len(frame_paths))]
    return boxes, elapsed, torch.cuda.max_memory_allocated(), torch.cuda.max_memory_reserved()


def summarize(reference, boxes, anchor_index, elapsed, sam_boxes=None):
    evaluated = [index for index in range(len(boxes)) if index != anchor_index]
    ious = [box_iou(reference[index], boxes[index]) for index in evaluated]
    adjacent = [box_iou(boxes[index - 1], boxes[index]) for index in range(1, len(boxes))]
    result = {
        "frame_count": len(boxes),
        "evaluated_frame_count": len(evaluated),
        "missing_box_count": sum(box is None for box in boxes),
        "perceptflow_agreement_iou_mean": round(statistics.mean(ious), 6),
        "perceptflow_agreement_iou_median": round(statistics.median(ious), 6),
        "perceptflow_agreement_rate_at_0_5": round(sum(iou >= 0.5 for iou in ious) / len(ious), 6),
        "temporal_adjacent_iou_mean": round(statistics.mean(adjacent), 6),
        "temporal_jump_count_below_0_3": sum(iou < 0.3 for iou in adjacent),
        "elapsed_seconds": round(elapsed, 6),
        "throughput_fps": round(len(boxes) / elapsed, 6),
    }
    if sam_boxes is not None:
        sam_ious = [box_iou(sam_boxes[index], boxes[index]) for index in evaluated]
        result["sam2_agreement_iou_mean"] = round(statistics.mean(sam_ious), 6)
    return result


def render(frame_paths, reference, sam_boxes, outputs, output_path, anchor_index):
    first = cv2.imread(str(frame_paths[0]))
    height, width = first.shape[:2]
    writer = cv2.VideoWriter(str(output_path), cv2.VideoWriter_fourcc(*"mp4v"), 5.0, (width, height))
    colors = {"sam2.1_tiny": (0, 0, 255), "cutie_sam_mask": (255, 0, 255),
              "cutie_rectangle": (255, 255, 0)}

    def pixels(box):
        if box is None:
            return None
        return tuple(round(value) for value in (
            box[0] * width / 1000, box[1] * height / 1000,
            box[2] * width / 1000, box[3] * height / 1000,
        ))

    for index, frame_path in enumerate(frame_paths):
        image = cv2.imread(str(frame_path))
        pf = pixels(reference[index])
        cv2.rectangle(image, pf[:2], pf[2:], (0, 255, 0), 2)
        candidates = {"sam2.1_tiny": sam_boxes[index], **{name: boxes[index] for name, boxes in outputs.items()}}
        for name, box in candidates.items():
            points = pixels(box)
            if points is not None:
                cv2.rectangle(image, points[:2], points[2:], colors[name], 2)
        cv2.putText(image, f"frame={index + 1} anchor={anchor_index + 1}", (15, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        cv2.putText(image, "PF=green SAM=red CutieSAM=magenta CutieBox=cyan", (15, 60),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2)
        writer.write(image)
    writer.release()


def current_rss_bytes() -> int:
    for line in Path("/proc/self/status").read_text().splitlines():
        if line.startswith("VmRSS:"):
            return int(line.split()[1]) * 1024
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset_dir", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--anchor-mask-dir", type=Path, required=True)
    parser.add_argument("--sam2-results-dir", type=Path, required=True)
    parser.add_argument("--cutie-checkpoint", type=Path, required=True)
    parser.add_argument("--anchor-fraction", type=float, default=0.75)
    parser.add_argument("--max-internal-size", type=int, default=480)
    args = parser.parse_args()

    import torch
    from cutie.utils.get_default_model import get_default_model

    args.output_dir.mkdir(parents=True, exist_ok=True)
    torch.cuda.reset_peak_memory_stats()
    model = get_default_model()
    model_allocated = torch.cuda.memory_allocated()
    report = {
        "method": "single_anchor_bidirectional_cutie_propagation",
        "anchor_fraction": args.anchor_fraction,
        "max_internal_size": args.max_internal_size,
        "model": {
            "name": "cutie-base-mega",
            "checkpoint_bytes": args.cutie_checkpoint.stat().st_size,
            "parameter_count": sum(parameter.numel() for parameter in model.parameters()),
            "model_cuda_allocated_bytes": model_allocated,
            "process_rss_after_load_bytes": current_rss_bytes(),
        },
        "clips": [],
    }

    warm_clip = sorted(args.dataset_dir.glob("clip_[0-9][0-9][0-9]"))[0]
    warm_frames, _ = load_clip(warm_clip)
    warm_anchor = int((len(warm_frames) - 1) * args.anchor_fraction)
    warm_mask = np.array(
        Image.open(args.anchor_mask_dir / f"{warm_clip.name}_anchor_mask.png"),
        dtype=np.uint8,
        copy=True,
    )
    warm_indices = list(range(warm_anchor + 1, min(warm_anchor + 3, len(warm_frames))))
    warm_started = time.perf_counter()
    with torch.inference_mode(), torch.autocast("cuda", dtype=torch.float16):
        run_branch(
            model, warm_frames, warm_anchor, warm_mask, warm_indices,
            args.max_internal_size,
        )
    torch.cuda.synchronize()
    report["warmup_seconds"] = time.perf_counter() - warm_started
    torch.cuda.empty_cache()

    for clip_dir in sorted(args.dataset_dir.glob("clip_[0-9][0-9][0-9]")):
        frame_paths, reference = load_clip(clip_dir)
        anchor_index = int((len(frame_paths) - 1) * args.anchor_fraction)
        with Image.open(frame_paths[anchor_index]) as image:
            width, height = image.size
        sam_mask = np.array(
            Image.open(args.anchor_mask_dir / f"{clip_dir.name}_anchor_mask.png"),
            dtype=np.uint8, copy=True,
        )
        box_mask = rectangle_mask(reference[anchor_index], width, height)
        sam_boxes = sam_boxes_from_raw(
            args.sam2_results_dir / f"{clip_dir.name}_sam2.1_tiny_raw.json", frame_paths
        )
        outputs = {}
        clip_result = {"clip": clip_dir.name, "anchor_frame": anchor_index + 1,
                       "frame_count": len(frame_paths), "backends": {}}
        for name, mask in (("cutie_sam_mask", sam_mask), ("cutie_rectangle", box_mask)):
            boxes, elapsed, peak_allocated, peak_reserved = run_cutie(
                model, frame_paths, anchor_index, mask, args.max_internal_size
            )
            outputs[name] = boxes
            clip_result["backends"][name] = {
                "status": "succeeded",
                **summarize(reference, boxes, anchor_index, elapsed, sam_boxes),
                "peak_cuda_allocated_bytes": peak_allocated,
                "peak_cuda_reserved_bytes": peak_reserved,
            }
            (args.output_dir / f"{clip_dir.name}_{name}_raw.json").write_text(
                json.dumps({"boxes": boxes}, indent=2) + "\n", encoding="utf-8"
            )
        render(frame_paths, reference, sam_boxes, outputs,
               args.output_dir / f"{clip_dir.name}_cutie_comparison.mp4", anchor_index)
        report["clips"].append(clip_result)
        print(json.dumps(clip_result, ensure_ascii=False), flush=True)

    if len(report["clips"]) != 3:
        raise ValueError(f"expected three clips, found {len(report['clips'])}")
    report["process_rss_final_bytes"] = current_rss_bytes()
    (args.output_dir / "cutie_benchmark_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()

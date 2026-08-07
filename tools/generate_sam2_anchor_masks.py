#!/usr/bin/env python3
"""Generate one SAM2 anchor mask per benchmark clip from the shared PF anchor box."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import tempfile
import time

import numpy as np
from PIL import Image


def normalized_to_pixel_xyxy(box, width: int, height: int) -> list[float]:
    return [
        float(box[0]) * width / 1000,
        float(box[1]) * height / 1000,
        float(box[2]) * width / 1000,
        float(box[3]) * height / 1000,
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset_dir", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--model-cfg", required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--anchor-fraction", type=float, default=0.75)
    args = parser.parse_args()
    if not 0 <= args.anchor_fraction <= 1:
        raise ValueError("anchor-fraction must be between zero and one")

    import torch
    from sam2.build_sam import build_sam2_video_predictor

    args.output_dir.mkdir(parents=True, exist_ok=True)
    torch.cuda.reset_peak_memory_stats()
    predictor = build_sam2_video_predictor(
        args.model_cfg, str(args.checkpoint), device="cuda"
    )
    model_allocated = torch.cuda.memory_allocated()
    records = []
    started = time.perf_counter()

    with torch.inference_mode(), torch.autocast("cuda", dtype=torch.bfloat16):
        for clip_dir in sorted(args.dataset_dir.glob("clip_[0-9][0-9][0-9]")):
            frames = sorted((clip_dir / "frames").glob("frame_*.jpg"))
            reference = sorted(
                json.loads((clip_dir / "calibrated" / "results.json").read_text()),
                key=lambda item: int(item["frame_index"]),
            )
            if len(frames) != len(reference) or not frames:
                raise ValueError(f"frame/result mismatch in {clip_dir}")
            anchor_index = int((len(frames) - 1) * args.anchor_fraction)
            with Image.open(frames[anchor_index]) as image:
                width, height = image.size
            box = normalized_to_pixel_xyxy(
                reference[anchor_index]["box"], width, height
            )
            with tempfile.TemporaryDirectory(prefix="sam21_anchor_") as temp_dir:
                for index, frame in enumerate(frames):
                    (Path(temp_dir) / f"{index:06d}.jpg").symlink_to(frame)
                state = predictor.init_state(video_path=temp_dir)
                _, _, logits = predictor.add_new_points_or_box(
                    inference_state=state,
                    frame_idx=anchor_index,
                    obj_id=1,
                    box=np.asarray(box, dtype=np.float32),
                )
                mask = (logits[0] > 0).cpu().numpy().squeeze().astype(np.uint8)
                predictor.reset_state(state)
            output_path = args.output_dir / f"{clip_dir.name}_anchor_mask.png"
            Image.fromarray(mask).save(output_path)
            records.append(
                {
                    "clip": clip_dir.name,
                    "anchor_frame": anchor_index + 1,
                    "frame_count": len(frames),
                    "mask_area_pixels": int(mask.sum()),
                    "mask_path": str(output_path),
                }
            )

    torch.cuda.synchronize()
    report = {
        "model": "sam2.1_hiera_tiny",
        "checkpoint_bytes": args.checkpoint.stat().st_size,
        "parameter_count": sum(parameter.numel() for parameter in predictor.parameters()),
        "model_cuda_allocated_bytes": model_allocated,
        "peak_cuda_allocated_bytes": torch.cuda.max_memory_allocated(),
        "elapsed_seconds": time.perf_counter() - started,
        "clips": records,
    }
    (args.output_dir / "anchor_mask_report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Serve bidirectional SAM2.1 video propagation for one human box anchor."""

from __future__ import annotations

import argparse
from contextlib import nullcontext
from pathlib import Path
import tempfile
import threading
import time
from typing import Any, Sequence

import numpy as np
from PIL import Image


MODEL_NAME = "sam2.1_hiera_tiny"
ANCHOR_SOURCES = {"pf", "human", "redetection"}


def mask_to_box(mask: np.ndarray) -> list[int] | None:
    """Return inclusive-exclusive pixel xyxy around one binary mask."""
    if mask.ndim != 2:
        raise ValueError("mask must be two-dimensional")
    ys, xs = np.where(mask)
    if not len(xs):
        return None
    return [int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1]


def validate_box(box: Sequence[Any], width: int, height: int) -> list[float]:
    if not isinstance(box, (list, tuple)) or len(box) != 4:
        raise ValueError("box_xyxy_pixels must contain four values")
    try:
        x1, y1, x2, y2 = (float(value) for value in box)
    except (TypeError, ValueError) as exc:
        raise ValueError("box_xyxy_pixels must contain numbers") from exc
    if not (0 <= x1 < x2 <= width and 0 <= y1 < y2 <= height):
        raise ValueError("box_xyxy_pixels must stay inside the image and have positive area")
    return [x1, y1, x2, y2]


def validate_anchor_source(value: Any) -> str:
    if not isinstance(value, str) or value not in ANCHOR_SOURCES:
        allowed = ", ".join(sorted(ANCHOR_SOURCES))
        raise ValueError(f"anchor_source must be one of: {allowed}")
    return value


def resolve_frames(frames_dir: str, allowed_root: Path) -> list[Path]:
    directory = Path(frames_dir).expanduser().resolve()
    try:
        directory.relative_to(allowed_root.resolve())
    except ValueError as exc:
        raise ValueError(f"frames_dir must be under {allowed_root}") from exc
    if not directory.is_dir():
        raise ValueError(f"frames_dir is not a directory: {directory}")
    frames = sorted(
        path for path in directory.iterdir()
        if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg"}
    )
    if not frames:
        raise ValueError("frames_dir contains no JPEG frames")
    return frames


class Sam2Runtime:
    def __init__(self, model_cfg: str, checkpoint: str, device: str = "cuda"):
        import torch
        from sam2.build_sam import build_sam2_video_predictor

        self.torch = torch
        self.device = device
        self.predictor = build_sam2_video_predictor(model_cfg, checkpoint, device=device)
        self.lock = threading.Lock()

    def _precision_context(self):
        if self.device.startswith("cuda"):
            return self.torch.autocast("cuda", dtype=self.torch.bfloat16)
        return nullcontext()

    def _run_direction(
        self,
        video_dir: str,
        anchor_index: int,
        box: Sequence[float],
        reverse: bool,
    ) -> dict[int, np.ndarray]:
        state = self.predictor.init_state(video_path=video_dir)
        _, _, anchor_logits = self.predictor.add_new_points_or_box(
            inference_state=state,
            frame_idx=anchor_index,
            obj_id=1,
            box=np.asarray(box, dtype=np.float32),
        )
        masks = {anchor_index: (anchor_logits[0] > 0.0).cpu().numpy().squeeze()}
        for frame_index, _, mask_logits in self.predictor.propagate_in_video(
            state,
            start_frame_idx=anchor_index,
            reverse=reverse,
        ):
            masks[int(frame_index)] = (mask_logits[0] > 0.0).cpu().numpy().squeeze()
        return masks

    def propagate(
        self,
        frames: Sequence[Path],
        anchor_index: int,
        box: Sequence[float],
        anchor_source: str,
    ) -> list[dict[str, Any]]:
        with self.lock, tempfile.TemporaryDirectory(prefix="sam21_frames_") as temp_dir:
            temp_path = Path(temp_dir)
            for index, source in enumerate(frames):
                (temp_path / f"{index:06d}.jpg").symlink_to(source)

            started = time.perf_counter()
            with self.torch.inference_mode(), self._precision_context():
                backward = self._run_direction(str(temp_path), anchor_index, box, True)
                forward = self._run_direction(str(temp_path), anchor_index, box, False)
            elapsed = time.perf_counter() - started
            masks = {**backward, **forward}

        results = []
        for index, frame in enumerate(frames):
            mask = masks.get(index)
            detected_box = None if mask is None else mask_to_box(mask)
            results.append(
                {
                    "frame_index": index + 1,
                    "frame_name": frame.name,
                    "box_xyxy_pixels": detected_box,
                    "mask_area_pixels": None if mask is None else int(mask.sum()),
                    "source": (
                        f"{anchor_source}_anchor"
                        if index == anchor_index
                        else f"sam_from_{anchor_source}_anchor"
                    ),
                }
            )
        return results, elapsed


def create_app(runtime: Sam2Runtime, allowed_root: Path):
    from flask import Flask, jsonify, request

    app = Flask(__name__)
    loaded_at = time.time()

    @app.get("/healthz")
    def healthz():
        return jsonify(
            status="ready",
            model=MODEL_NAME,
            device=runtime.device,
            loaded_at_unix=loaded_at,
        )

    @app.post("/api/v1/mot/sam2/propagate")
    def propagate():
        payload = request.get_json(force=True)
        if not isinstance(payload, dict):
            return jsonify(status=400, message="request body must be a JSON object"), 400
        try:
            frames = resolve_frames(payload.get("frames_dir", ""), allowed_root)
            anchor_frame = payload.get("anchor_frame")
            if isinstance(anchor_frame, bool) or not isinstance(anchor_frame, int):
                raise ValueError("anchor_frame must be a 1-based integer")
            if not 1 <= anchor_frame <= len(frames):
                raise ValueError(f"anchor_frame must be between 1 and {len(frames)}")
            anchor_source = validate_anchor_source(payload.get("anchor_source"))
            with Image.open(frames[0]) as image:
                width, height = image.size
            for frame in frames[1:]:
                with Image.open(frame) as image:
                    if image.size != (width, height):
                        raise ValueError("all frames must have the same dimensions")
            box = validate_box(payload.get("box_xyxy_pixels"), width, height)
            results, elapsed = runtime.propagate(frames, anchor_frame - 1, box, anchor_source)
        except ValueError as exc:
            return jsonify(status=400, message=str(exc)), 400
        except Exception as exc:
            app.logger.exception("SAM2 propagation failed")
            return jsonify(status=500, message=f"SAM2 propagation failed: {exc}"), 500

        empty_count = sum(item["box_xyxy_pixels"] is None for item in results)
        return jsonify(
            status=200,
            model=MODEL_NAME,
            coordinate_space="pixel_xyxy",
            anchor_frame=anchor_frame,
            anchor_source=anchor_source,
            propagation_source=f"sam_from_{anchor_source}_anchor",
            frame_count=len(results),
            empty_mask_count=empty_count,
            elapsed_seconds=elapsed,
            frames=results,
        )

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-cfg", required=True)
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--allowed-root", type=Path, required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5001)
    args = parser.parse_args()

    runtime = Sam2Runtime(args.model_cfg, args.checkpoint)
    app = create_app(runtime, args.allowed_root)
    app.run(host=args.host, port=args.port, threaded=True)


if __name__ == "__main__":
    main()

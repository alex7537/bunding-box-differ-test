#!/usr/bin/env python3
"""Propagate one human parcel annotation through an image sequence."""

from __future__ import annotations

import argparse
import base64
import json
import math
from pathlib import Path
import shutil
from typing import Sequence

from PIL import Image
import requests


CANONICAL_PARCEL_LABELS = ("parcel_front", "parcel_back")


def yolo_to_pixel_xywh(values: Sequence[float], width: int, height: int) -> list[float]:
    center_x, center_y, box_width, box_height = _validated_yolo_box(values)
    return [
        (center_x - box_width / 2) * width,
        (center_y - box_height / 2) * height,
        box_width * width,
        box_height * height,
    ]


def pixel_xywh_to_yolo(values: Sequence[float], width: int, height: int) -> list[float]:
    if width <= 0 or height <= 0 or len(values) != 4:
        raise ValueError("image size must be positive and bbox must contain four values")
    x, y, box_width, box_height = (float(value) for value in values)
    if not all(math.isfinite(value) for value in (x, y, box_width, box_height)):
        raise ValueError("tracker bbox must contain finite values")
    if box_width <= 0 or box_height <= 0:
        raise ValueError("tracker bbox width and height must be positive")
    yolo = [
        (x + box_width / 2) / width,
        (y + box_height / 2) / height,
        box_width / width,
        box_height / height,
    ]
    return _validated_yolo_box(yolo)


def _validated_yolo_box(values: Sequence[float]) -> list[float]:
    if len(values) != 4:
        raise ValueError("YOLO bbox must contain four values")
    center_x, center_y, box_width, box_height = (float(value) for value in values)
    if not all(math.isfinite(value) for value in (center_x, center_y, box_width, box_height)):
        raise ValueError("YOLO bbox must contain finite values")
    if box_width <= 0 or box_height <= 0:
        raise ValueError("YOLO bbox width and height must be positive")
    x1 = center_x - box_width / 2
    y1 = center_y - box_height / 2
    x2 = center_x + box_width / 2
    y2 = center_y + box_height / 2
    if x1 < 0 or y1 < 0 or x2 > 1 or y2 > 1:
        raise ValueError("YOLO bbox must stay inside normalized image bounds")
    return [center_x, center_y, box_width, box_height]


def _read_single_yolo_box(path: Path) -> tuple[int, list[float]]:
    lines = [line.split() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(lines) != 1 or len(lines[0]) != 5:
        raise ValueError(f"expected exactly one YOLO box in {path}")
    try:
        class_id = int(lines[0][0])
    except ValueError as exc:
        raise ValueError(f"invalid YOLO class id in {path}") from exc
    if class_id < 0:
        raise ValueError(f"YOLO class id must be non-negative in {path}")
    try:
        box = _validated_yolo_box([float(value) for value in lines[0][1:]])
    except ValueError as exc:
        raise ValueError(f"invalid YOLO bbox in {path}: {exc}") from exc
    return class_id, box


def _load_classes(path: Path) -> list[str]:
    if not path.is_file():
        raise ValueError(f"missing classes file: {path}")
    classes = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not classes:
        raise ValueError(f"classes file is empty: {path}")
    if len(set(classes)) != len(classes):
        raise ValueError(f"classes file contains duplicate labels: {path}")
    return classes


def _find_anchor(frame_paths: Sequence[Path], requested_frame: int | None) -> tuple[int, int, list[float]]:
    annotations = {
        index: frame_path.with_suffix(".txt")
        for index, frame_path in enumerate(frame_paths)
        if frame_path.with_suffix(".txt").is_file()
    }
    if requested_frame is None:
        if len(annotations) != 1:
            raise ValueError(
                "expected exactly one human anchor annotation; "
                f"found {len(annotations)} (use --anchor-frame to select one)"
            )
        anchor_index = next(iter(annotations))
    else:
        if not 1 <= requested_frame <= len(frame_paths):
            raise ValueError(f"anchor frame must be between 1 and {len(frame_paths)}")
        anchor_index = requested_frame - 1
        if anchor_index not in annotations:
            raise ValueError(f"missing anchor annotation: {frame_paths[anchor_index].with_suffix('.txt')}")
    class_id, box = _read_single_yolo_box(annotations[anchor_index])
    return anchor_index, class_id, box


def _encoded_image(path: Path) -> str:
    return base64.urlsafe_b64encode(path.read_bytes()).decode("utf-8")


def _post(session: requests.Session, url: str, payload: dict, timeout: float) -> dict:
    # The legacy Flask API expects a JSON string nested inside the JSON body.
    response = session.post(url, json=json.dumps(payload), timeout=timeout)
    response.raise_for_status()
    result = response.json()
    if str(result.get("status")) != "200":
        raise RuntimeError(result.get("message") or f"tracker returned status {result.get('status')}")
    if len(result.get("bboxes", [])) != 1:
        raise RuntimeError("tracker must return exactly one bbox")
    return result


def _image_size(path: Path) -> tuple[int, int]:
    with Image.open(path) as image:
        return image.size


def _track_branch(
    frame_paths: Sequence[Path],
    anchor_index: int,
    initial_yolo: Sequence[float],
    indices: Sequence[int],
    *,
    base_url: str,
    model: str,
    parameter: str,
    timeout: float,
) -> dict[int, list[float]]:
    session = requests.Session()
    anchor_width, anchor_height = _image_size(frame_paths[anchor_index])
    x, y, box_width, box_height = yolo_to_pixel_xywh(initial_yolo, anchor_width, anchor_height)
    launch_payload = {
        "bboxes": [{"x": x, "y": y, "w": box_width, "h": box_height}],
        "request_id": "",
        "image_width": anchor_width,
        "image_height": anchor_height,
        "image_data": _encoded_image(frame_paths[anchor_index]),
        "algo_name": model,
        "algo_param": parameter,
    }
    launch = _post(
        session,
        f"{base_url.rstrip('/')}/api/v1/mot/pytracking/launch_tracking",
        launch_payload,
        timeout,
    )
    request_id = str(launch["request_id"])
    tracked: dict[int, list[float]] = {}
    for index in indices:
        width, height = _image_size(frame_paths[index])
        payload = {
            "bboxes": [],
            "request_id": request_id,
            "image_width": width,
            "image_height": height,
            "image_data": _encoded_image(frame_paths[index]),
            "algo_name": model,
            "algo_param": parameter,
        }
        response = _post(
            session,
            f"{base_url.rstrip('/')}/api/v1/mot/pytracking/track_next",
            payload,
            timeout,
        )
        bbox = response["bboxes"][0]
        tracked[index] = pixel_xywh_to_yolo(
            [float(bbox[key]) for key in ("x", "y", "w", "h")],
            width,
            height,
        )
    return tracked


def propagate_annotation(
    frame_paths: Sequence[Path],
    anchor_index: int,
    initial_yolo: Sequence[float],
    *,
    base_url: str,
    model: str,
    parameter: str,
    timeout: float,
) -> dict[int, list[float]]:
    """Track backward and forward from one trusted human annotation."""
    boxes = {anchor_index: _validated_yolo_box(initial_yolo)}
    if anchor_index > 0:
        boxes.update(
            _track_branch(
                frame_paths,
                anchor_index,
                initial_yolo,
                list(range(anchor_index - 1, -1, -1)),
                base_url=base_url,
                model=model,
                parameter=parameter,
                timeout=timeout,
            )
        )
    if anchor_index + 1 < len(frame_paths):
        boxes.update(
            _track_branch(
                frame_paths,
                anchor_index,
                initial_yolo,
                list(range(anchor_index + 1, len(frame_paths))),
                base_url=base_url,
                model=model,
                parameter=parameter,
                timeout=timeout,
            )
        )
    if len(boxes) != len(frame_paths):
        raise RuntimeError("tracker did not produce one bbox for every frame")
    return boxes


def _write_outputs(
    output_dir: Path,
    frame_paths: Sequence[Path],
    boxes: dict[int, list[float]],
    *,
    anchor_index: int,
    class_id: int,
    label: str,
    classes_path: Path,
    model: str,
    parameter: str,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    conflicting = [path for path in output_dir.glob("frame_*.txt")]
    if conflicting or (output_dir / "annotation_manifest.json").exists():
        raise FileExistsError(f"output directory already contains propagated annotations: {output_dir}")

    results = []
    for index, frame_path in enumerate(frame_paths):
        yolo_box = boxes[index]
        label_path = output_dir / f"{frame_path.stem}.txt"
        label_path.write_text(
            f"{class_id} " + " ".join(f"{value:.6f}" for value in yolo_box) + "\n",
            encoding="utf-8",
        )
        results.append(
            {
                "frame_index": index + 1,
                "frame_name": frame_path.name,
                "class_id": class_id,
                "label": label,
                "bbox_yolo_cxcywh_0_1": yolo_box,
                "source": "human" if index == anchor_index else "tracker",
            }
        )

    shutil.copy2(classes_path, output_dir / "classes.txt")
    manifest = {
        "schema_version": 1,
        "annotation_type": "human_parcel_bbox_and_side",
        "coordinate_space": "yolo_cxcywh_0_1",
        "anchor_frame": anchor_index + 1,
        "label": label,
        "model": model,
        "parameter": parameter,
        "frames": results,
    }
    (output_dir / "annotation_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("frames_dir", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--anchor-frame", type=int, default=None, help="1-based human anchor frame")
    parser.add_argument("--classes", type=Path, default=None)
    parser.add_argument(
        "--allow-any-label",
        action="store_true",
        help="accept a label other than parcel_front or parcel_back",
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:5000")
    parser.add_argument("--model", default="tomp")
    parser.add_argument("--parameter", default="tomp50")
    parser.add_argument("--timeout", type=float, default=60.0)
    args = parser.parse_args()

    frame_paths = sorted(args.frames_dir.glob("frame_*.png"))
    if not frame_paths:
        frame_paths = sorted(args.frames_dir.glob("frame_*.jpg"))
    if not frame_paths:
        raise ValueError(f"no frame_*.png or frame_*.jpg files found in {args.frames_dir}")
    if args.timeout <= 0:
        raise ValueError("timeout must be positive")

    anchor_index, class_id, initial_yolo = _find_anchor(frame_paths, args.anchor_frame)
    classes_path = args.classes or args.frames_dir / "classes.txt"
    classes = _load_classes(classes_path)
    if class_id >= len(classes):
        raise ValueError(f"class id {class_id} is outside classes file range")
    label = classes[class_id]
    if not args.allow_any_label and label not in CANONICAL_PARCEL_LABELS:
        raise ValueError(
            f"anchor label must be one of {CANONICAL_PARCEL_LABELS}; got {label!r}. "
            "Use --allow-any-label only for legacy datasets."
        )

    boxes = propagate_annotation(
        frame_paths,
        anchor_index,
        initial_yolo,
        base_url=args.base_url,
        model=args.model,
        parameter=args.parameter,
        timeout=args.timeout,
    )
    _write_outputs(
        args.output_dir,
        frame_paths,
        boxes,
        anchor_index=anchor_index,
        class_id=class_id,
        label=label,
        classes_path=classes_path,
        model=args.model,
        parameter=args.parameter,
    )
    print(f"wrote {len(frame_paths)} frames to {args.output_dir}")


if __name__ == "__main__":
    main()

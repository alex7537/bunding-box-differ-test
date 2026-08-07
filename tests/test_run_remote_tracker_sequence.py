import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from PIL import Image

from tools.run_remote_tracker_sequence import (
    _find_anchor,
    _write_outputs,
    pixel_xywh_to_yolo,
    propagate_annotation,
    yolo_to_pixel_xywh,
)


class RemoteTrackerSequenceTest(unittest.TestCase):
    def test_coordinate_round_trip(self):
        yolo = [0.5, 0.4, 0.2, 0.1]
        pixels = yolo_to_pixel_xywh(yolo, 1000, 500)
        for actual, expected in zip(pixels, [400.0, 175.0, 200.0, 50.0]):
            self.assertAlmostEqual(actual, expected)
        for actual, expected in zip(pixel_xywh_to_yolo(pixels, 1000, 500), yolo):
            self.assertAlmostEqual(actual, expected)

    def test_rejects_box_outside_image(self):
        with self.assertRaisesRegex(ValueError, "inside normalized image bounds"):
            yolo_to_pixel_xywh([0.95, 0.5, 0.2, 0.2], 100, 100)

    def test_auto_discovers_one_human_anchor(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            frames = [root / f"frame_{index:06d}.jpg" for index in range(1, 4)]
            frames[1].with_suffix(".txt").write_text("1 0.5 0.5 0.2 0.2\n")
            self.assertEqual(_find_anchor(frames, None), (1, 1, [0.5, 0.5, 0.2, 0.2]))

    def test_tracks_both_directions_from_middle_anchor(self):
        frames = [Path(f"frame_{index:06d}.jpg") for index in range(1, 5)]
        calls = []

        def fake_branch(_frames, anchor, initial, indices, **_kwargs):
            calls.append((anchor, list(indices)))
            return {index: [0.5, 0.5, 0.2, 0.2] for index in indices}

        with patch("tools.run_remote_tracker_sequence._track_branch", side_effect=fake_branch):
            result = propagate_annotation(
                frames,
                1,
                [0.5, 0.5, 0.2, 0.2],
                base_url="http://tracker",
                model="tomp",
                parameter="tomp50",
                timeout=1,
            )
        self.assertEqual(calls, [(1, [0]), (1, [2, 3])])
        self.assertEqual(sorted(result), [0, 1, 2, 3])

    def test_manifest_marks_only_anchor_as_human(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "output"
            classes = root / "classes.txt"
            classes.write_text("parcel_front\nparcel_back\n")
            frames = [root / f"frame_{index:06d}.jpg" for index in range(1, 4)]
            for frame in frames:
                Image.new("RGB", (8, 8)).save(frame)
            boxes = {index: [0.5, 0.5, 0.2, 0.2] for index in range(3)}
            _write_outputs(
                output,
                frames,
                boxes,
                anchor_index=1,
                class_id=0,
                label="parcel_front",
                classes_path=classes,
                model="tomp",
                parameter="tomp50",
            )
            import json

            manifest = json.loads((output / "annotation_manifest.json").read_text())
            self.assertEqual([frame["source"] for frame in manifest["frames"]], ["tracker", "human", "tracker"])
            self.assertEqual(manifest["annotation_type"], "human_parcel_bbox_and_side")


if __name__ == "__main__":
    unittest.main()

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from PIL import Image

from tools.export_final_bbox_tracks import build_pf_track, export_tracks


class ExportFinalBboxTracksTest(unittest.TestCase):
    def make_clip(self, dataset_root: Path, episode: str, clip: str):
        clip_dir = dataset_root / episode / clip
        frames_dir = clip_dir / "frames"
        calibrated_dir = clip_dir / "calibrated"
        frames_dir.mkdir(parents=True)
        calibrated_dir.mkdir()
        Image.new("RGB", (100, 50)).save(frames_dir / "frame_000001.jpg")
        (calibrated_dir / "results.json").write_text(
            json.dumps([{"frame_index": 1, "box": [100, 200, 500, 600]}]),
            encoding="utf-8",
        )

    def test_preserves_missing_pf_box_as_null(self):
        with TemporaryDirectory() as temporary:
            dataset_root = Path(temporary) / "dataset"
            self.make_clip(dataset_root, "ep1", "clip_001")
            results = dataset_root / "ep1" / "clip_001" / "calibrated" / "results.json"
            results.write_text(
                json.dumps([{"frame_index": 1, "box": None}]), encoding="utf-8"
            )

            payload = build_pf_track(dataset_root / "ep1" / "clip_001")

            self.assertIsNone(payload["frames"][0]["box_xyxy_pixels"])

    def test_exports_selected_sam_and_default_pf_with_pending_state(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            dataset_root = root / "dataset"
            self.make_clip(dataset_root, "ep1", "clip_001")
            self.make_clip(dataset_root, "ep1", "clip_002")
            selected = root / "final_bbox_tracks" / "ep1" / "clip_001.json"
            selected.parent.mkdir(parents=True)
            selected.write_text(
                json.dumps(
                    {
                        "selected_track": "sam",
                        "source_artifact": "clip_001_sam2.1_tiny_human_raw.json",
                        "frame_count": 1,
                        "frames": [{"frame_index": 1, "box_xyxy_pixels": [1, 2, 3, 4]}],
                    }
                ),
                encoding="utf-8",
            )
            queue_path = root / "queue.json"
            queue_path.write_text(
                json.dumps(
                    {
                        "items": [
                            {
                                "key": "ep1/clip_001",
                                "final_track_source": "sam",
                                "final_track_file": "final_bbox_tracks/ep1/clip_001.json",
                            },
                            {"key": "ep1/clip_002", "status": "pending_anchor_review"},
                        ]
                    }
                ),
                encoding="utf-8",
            )

            manifest = export_tracks(dataset_root, queue_path, root / "final_bbox_tracks")

            self.assertEqual(manifest["clip_count"], 2)
            self.assertEqual(manifest["review_pending_count"], 1)
            self.assertEqual(manifest["decision_counts"]["human_confirmed_sam_after_reanchor"], 1)
            fallback = json.loads(
                (root / "final_bbox_tracks" / "ep1" / "clip_002.json").read_text()
            )
            self.assertEqual(fallback["selected_track"], "pf")
            self.assertTrue(fallback["review_pending"])
            self.assertEqual(fallback["missing_bbox_count"], 0)
            self.assertEqual(fallback["frames"][0]["box_xyxy_pixels"], [10.0, 10.0, 50.0, 30.0])


if __name__ == "__main__":
    unittest.main()

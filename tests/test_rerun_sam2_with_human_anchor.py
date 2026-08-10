import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import cv2
import numpy as np

from tools.rerun_sam2_with_human_anchor import rerun_with_human_anchor, validate_box


class RerunSam2WithHumanAnchorTest(unittest.TestCase):
    def test_validate_box_rejects_out_of_frame_box(self):
        with self.assertRaisesRegex(ValueError, "bbox must satisfy"):
            validate_box([-1, 0, 50, 50], 100, 100)

    @patch("tools.rerun_sam2_with_human_anchor._post_json")
    def test_rerun_declares_human_anchor_and_preserves_pf_result(self, post_json):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            clip = root / "clip_002"
            frames = clip / "frames"
            results = root / "results"
            frames.mkdir(parents=True)
            results.mkdir()
            cv2.imwrite(str(frames / "frame_000001.jpg"), np.zeros((100, 200, 3), dtype=np.uint8))
            pf_result = results / "clip_002_sam2.1_tiny_raw.json"
            pf_result.write_text("pf result")
            post_json.return_value = {
                "status": 200,
                "anchor_source": "human",
                "anchor_frame": 1,
                "frame_count": 1,
                "frames": [{"frame_index": 1, "box_xyxy_pixels": [10, 20, 80, 90]}],
            }

            output = rerun_with_human_anchor(
                clip, results, 1, [10, 20, 80, 90], "http://sam",
                anchor_review_result="anchor_confirmed", attribution="pf_wrong_smooth",
                error_content="oversized_region", multi_parcel="true", reviewed_by="tester",
            )

            payload = post_json.call_args.args[1]
            self.assertEqual(payload["anchor_source"], "human")
            self.assertEqual(payload["anchor_frame"], 1)
            self.assertEqual(payload["box_xyxy_pixels"], [10.0, 20.0, 80.0, 90.0])
            self.assertEqual(pf_result.read_text(), "pf result")
            self.assertEqual(json.loads(output.read_text())["anchor_source"], "human")
            anchor = json.loads((results / "clip_002_human_anchor.json").read_text())
            self.assertEqual(anchor["sam_result"], output.name)
            self.assertEqual(anchor["anchor_review_result"], "anchor_confirmed")
            self.assertEqual(anchor["attribution"], "pf_wrong_smooth")
            self.assertEqual(anchor["error_content"], "oversized_region")
            self.assertEqual(anchor["multi_parcel"], "true")
            self.assertEqual(anchor["reviewed_by"], "tester")
            self.assertTrue(anchor["reviewed_at"].endswith("+00:00"))

    @patch("tools.rerun_sam2_with_human_anchor._post_json")
    def test_remote_service_can_use_a_different_frames_path(self, post_json):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            clip = root / "clip_001"
            frames = clip / "frames"
            results = root / "results"
            frames.mkdir(parents=True)
            results.mkdir()
            cv2.imwrite(str(frames / "frame_000001.jpg"), np.zeros((20, 30, 3), dtype=np.uint8))
            post_json.return_value = {
                "status": 200,
                "anchor_source": "human",
                "anchor_frame": 1,
                "frame_count": 1,
                "frames": [{"frame_index": 1, "box_xyxy_pixels": [1, 2, 10, 12]}],
            }

            rerun_with_human_anchor(
                clip, results, 1, [1, 2, 10, 12], "http://sam",
                anchor_review_result="anchor_corrected", attribution="sam_wrong_anchor",
                error_content="other", multi_parcel="unknown", reviewed_by="tester",
                service_frames_dir="/share_data/zhangyurui/dataset/clip_001/frames",
            )

            self.assertEqual(
                post_json.call_args.args[1]["frames_dir"],
                "/share_data/zhangyurui/dataset/clip_001/frames",
            )


if __name__ == "__main__":
    unittest.main()

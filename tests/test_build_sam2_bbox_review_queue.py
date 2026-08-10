import json
from pathlib import Path
import tempfile
import unittest

from tools.build_sam2_bbox_review_queue import build_queue, load_overrides


class BuildSam2BboxReviewQueueTest(unittest.TestCase):
    def test_only_clip_conflicts_enter_queue_and_override_sets_priority(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            episode = root / "episode_1"
            episode.mkdir()
            manifest = {
                "clips": [
                    {
                        "clip": "clip_001",
                        "clip_status": "frame_review",
                        "anchor_frame": 2,
                    },
                    {
                        "clip": "clip_002",
                        "clip_status": "clip_level_conflict",
                        "anchor_frame": 7,
                        "anchor_source": "pf",
                        "review_candidate_count": 12,
                        "conflict_review_frames": {
                            "lowest_iou": 3,
                            "divergence_start": 2,
                            "before_anchor": 6,
                            "after_anchor": 8,
                        },
                        "conflict_stats": {
                            "low_iou_ratio": 0.8,
                            "longest_low_iou_run": [2, 9],
                            "area_ratio_median": 1.2,
                        },
                    },
                ]
            }
            (episode / "review_manifest.json").write_text(json.dumps(manifest))
            queue = build_queue(
                root,
                {
                    "episode_1/clip_002": {
                        "status": "reanchor_required",
                        "notes": "wrong target",
                    }
                },
            )

        self.assertEqual(queue["summary"]["clip_count"], 1)
        item = queue["items"][0]
        self.assertEqual(item["status"], "reanchor_required")
        self.assertEqual(item["recommended_action"], "draw_human_bbox_and_rerun_sam")
        self.assertEqual(item["lowest_iou_frame"], 3)

    def test_invalid_override_status_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "overrides.json"
            path.write_text(json.dumps({"e/c": {"status": "wrong"}}))
            with self.assertRaisesRegex(ValueError, "invalid status"):
                load_overrides(path)


if __name__ == "__main__":
    unittest.main()

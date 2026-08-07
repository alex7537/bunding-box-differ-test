import json
import tempfile
from pathlib import Path
import unittest

from tools.generate_sam2_review_pack import (
    anchor_disagreement_ratio,
    box_iou,
    calculate_conflict_stats,
    frame_in_grasp_window,
    load_grasp_windows,
    is_clip_level_conflict,
    select_sam_result,
)


class Sam2ReviewPackTest(unittest.TestCase):
    def test_grasp_windows_filter_only_out_of_scope_frames(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "windows.json"
            path.write_text(json.dumps({"clips": {"clip_001": [[3, 5], [8, 9]]}}))
            windows = load_grasp_windows(path)
        self.assertIs(frame_in_grasp_window(windows, "clip_001", 2), False)
        self.assertIs(frame_in_grasp_window(windows, "clip_001", 4), True)
        self.assertIs(frame_in_grasp_window(windows, "clip_001", 8), True)
        self.assertIs(frame_in_grasp_window(windows, "clip_002", 4), False)

    def test_missing_grasp_windows_leave_scope_unknown(self):
        self.assertIsNone(frame_in_grasp_window(None, "clip_001", 1))

    def test_sustained_disagreement_can_invalidate_anchor(self):
        ratio, count = anchor_disagreement_ratio(
            [0.1, 0.2, 1.0, 0.3, 0.4, 0.9],
            anchor_frame=3,
            in_scope=[True] * 6,
            iou_threshold=0.5,
        )
        self.assertEqual(count, 5)
        self.assertEqual(ratio, 0.8)

    def test_out_of_scope_frames_do_not_invalidate_anchor(self):
        ratio, count = anchor_disagreement_ratio(
            [0.0, 0.0, 1.0, 0.9, 0.9],
            anchor_frame=3,
            in_scope=[False, False, True, True, True],
            iou_threshold=0.5,
        )
        self.assertEqual(count, 2)
        self.assertEqual(ratio, 0.0)

    def test_missing_box_is_safe(self):
        self.assertEqual(box_iou(None, [0, 0, 10, 10]), 0.0)

    def test_human_result_overrides_pf_result(self):
        with tempfile.TemporaryDirectory() as directory:
            result_dir = Path(directory)
            pf = result_dir / "clip_001_sam2.1_tiny_raw.json"
            human = result_dir / "clip_001_sam2.1_tiny_human_raw.json"
            pf.touch()
            self.assertEqual(select_sam_result(result_dir, "clip_001"), pf)
            human.touch()
            self.assertEqual(select_sam_result(result_dir, "clip_001"), human)

    def test_long_run_triggers_conflict_even_below_ratio_threshold(self):
        agreements = [0.9] * 10 + [0.1] * 8 + [0.9] * 12
        stats = calculate_conflict_stats(
            agreements, [None] * 30, [None] * 30,
            anchor_frame=25, in_scope=[True] * 30, iou_threshold=0.5,
        )
        self.assertLess(stats["low_iou_ratio"], 0.6)
        self.assertEqual(stats["longest_low_iou_run"], [11, 18])
        self.assertTrue(is_clip_level_conflict(stats, 0.6, 8, 5))

    def test_anchor_does_not_split_a_low_iou_run(self):
        stats = calculate_conflict_stats(
            [0.1, 0.1, 1.0, 0.1, 0.1], [None] * 5, [None] * 5,
            anchor_frame=3, in_scope=[True] * 5, iou_threshold=0.5,
        )
        self.assertEqual(stats["longest_low_iou_run"], [1, 5])
        self.assertEqual(stats["longest_low_iou_run_length"], 4)


if __name__ == "__main__":
    unittest.main()

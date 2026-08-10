import os
from types import SimpleNamespace
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication

from tools.sam2_bbox_review_gui import (
    ReviewWindow,
    build_final_track_payload,
    normalized_pf_box,
    shape_box,
)


class Sam2BboxReviewGuiTest(unittest.TestCase):
    def test_normalized_pf_box_converts_1000_space_to_pixels(self):
        box = normalized_pf_box({"box": [100, 200, 700, 800]}, 1280, 720)
        self.assertEqual(box, [128.0, 144.0, 896.0, 576.0])

    def test_shape_box_orders_drag_directions(self):
        self.assertEqual(shape_box([20, 30, 5, 7]), [5.0, 7.0, 20.0, 30.0])

    def test_build_final_track_payload_selects_one_whole_track(self):
        entry = {"episode": "episode_1", "clip": "clip_001"}
        frame_paths = [
            SimpleNamespace(name="frame_000001.jpg"),
            SimpleNamespace(name="frame_000002.jpg"),
        ]
        references = [{"box": [100, 200, 500, 600]}, {"box": [200, 300, 600, 700]}]
        sam_frames = [
            {"box_xyxy_pixels": [11, 12, 21, 22]},
            {"box_xyxy_pixels": [31, 32, 41, 42]},
        ]

        payload = build_final_track_payload(
            entry, "sam", frame_paths, references, sam_frames, (1280, 720)
        )

        self.assertEqual(payload["decision_scope"], "whole_clip")
        self.assertEqual(payload["selected_track"], "sam")
        self.assertEqual(payload["frame_count"], 2)
        self.assertEqual(payload["frames"][1]["box_xyxy_pixels"], [31.0, 32.0, 41.0, 42.0])

    def test_frame_slider_and_spin_box_stay_synchronized(self):
        application = QApplication.instance() or QApplication([])
        window = ReviewWindow(
            SimpleNamespace(reviewed_by="tester"),
            {"items": [], "summary": {"status_counts": {}}},
        )
        window.frame_spin.setRange(1, 20)
        window.frame_slider.setRange(1, 20)

        window.frame_slider.setValue(14)
        self.assertEqual(window.frame_spin.value(), 14)
        window.frame_spin.setValue(6)
        self.assertEqual(window.frame_slider.value(), 6)

        window.close()
        application.processEvents()


if __name__ == "__main__":
    unittest.main()

import os
from types import SimpleNamespace
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication

from tools.sam2_bbox_review_gui import ReviewWindow, normalized_pf_box, shape_box


class Sam2BboxReviewGuiTest(unittest.TestCase):
    def test_normalized_pf_box_converts_1000_space_to_pixels(self):
        box = normalized_pf_box({"box": [100, 200, 700, 800]}, 1280, 720)
        self.assertEqual(box, [128.0, 144.0, 896.0, 576.0])

    def test_shape_box_orders_drag_directions(self):
        self.assertEqual(shape_box([20, 30, 5, 7]), [5.0, 7.0, 20.0, 30.0])

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

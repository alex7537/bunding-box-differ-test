import unittest

from tools.sam2_bbox_review_gui import normalized_pf_box, shape_box


class Sam2BboxReviewGuiTest(unittest.TestCase):
    def test_normalized_pf_box_converts_1000_space_to_pixels(self):
        box = normalized_pf_box({"box": [100, 200, 700, 800]}, 1280, 720)
        self.assertEqual(box, [128.0, 144.0, 896.0, 576.0])

    def test_shape_box_orders_drag_directions(self):
        self.assertEqual(shape_box([20, 30, 5, 7]), [5.0, 7.0, 20.0, 30.0])


if __name__ == "__main__":
    unittest.main()

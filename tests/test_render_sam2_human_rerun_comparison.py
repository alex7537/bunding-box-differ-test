import unittest

from tools.render_sam2_human_rerun_comparison import box_iou, pf_box_pixels


class RenderSam2HumanRerunComparisonTest(unittest.TestCase):
    def test_pf_box_pixels_converts_1000_space(self):
        self.assertEqual(
            pf_box_pixels({"box": [100, 200, 500, 600]}, 1280, 720),
            [128.0, 144.0, 640.0, 432.0],
        )

    def test_iou_handles_missing_and_overlap(self):
        self.assertEqual(box_iou(None, [0, 0, 10, 10]), 0.0)
        self.assertAlmostEqual(box_iou([0, 0, 10, 10], [5, 0, 15, 10]), 1 / 3)


if __name__ == "__main__":
    unittest.main()

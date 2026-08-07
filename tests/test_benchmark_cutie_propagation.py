import unittest

import numpy as np

from tools.benchmark_cutie_propagation import (
    mask_to_normalized_box,
    rectangle_mask,
    summarize,
)


class CutieBenchmarkHelpersTest(unittest.TestCase):
    def test_mask_to_box_uses_exclusive_max_corner(self):
        mask = np.zeros((10, 20), dtype=np.uint8)
        mask[2:8, 4:16] = 1
        self.assertEqual(mask_to_normalized_box(mask), [200.0, 200.0, 800.0, 800.0])

    def test_rectangle_mask_matches_normalized_box(self):
        mask = rectangle_mask([250, 200, 750, 800], width=20, height=10)
        self.assertEqual(int(mask.sum()), 60)
        self.assertEqual(mask_to_normalized_box(mask), [250.0, 200.0, 750.0, 800.0])

    def test_summary_excludes_anchor_from_reference_agreement(self):
        boxes = [[0, 0, 100, 100], [100, 100, 200, 200], [200, 200, 300, 300]]
        result = summarize(boxes, boxes, anchor_index=1, elapsed=1.5, sam_boxes=boxes)
        self.assertEqual(result["evaluated_frame_count"], 2)
        self.assertEqual(result["perceptflow_agreement_iou_mean"], 1.0)
        self.assertEqual(result["sam2_agreement_iou_mean"], 1.0)


if __name__ == "__main__":
    unittest.main()

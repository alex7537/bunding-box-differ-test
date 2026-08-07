import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from tools.benchmark_sam2_propagation import box_iou, run_sam2, summarize


class Sam2BenchmarkMetricTest(unittest.TestCase):
    def test_iou(self):
        self.assertEqual(box_iou([0, 0, 10, 10], [0, 0, 10, 10]), 1.0)
        self.assertEqual(box_iou([0, 0, 1, 1], [2, 2, 3, 3]), 0.0)

    def test_summary_excludes_anchor_from_reference_agreement(self):
        reference = [[0, 0, 10, 10]] * 3
        boxes = [[0, 0, 10, 10], [50, 50, 60, 60], [0, 0, 10, 10]]
        result = summarize(reference, boxes, anchor_index=1, elapsed_seconds=1.5)
        self.assertEqual(result["evaluated_frame_count"], 2)
        self.assertEqual(result["perceptflow_agreement_rate_at_0_5"], 1.0)

    @patch("tools.benchmark_sam2_propagation._post_json")
    def test_sam_benchmark_declares_pf_anchor_source(self, post_json):
        post_json.return_value = {
            "status": 200,
            "elapsed_seconds": 0.1,
            "frames": [{"box_xyxy_pixels": [1, 1, 9, 9]}],
        }
        image = np.zeros((10, 10, 3), dtype=np.uint8)
        run_sam2(Path("/tmp/frames"), [image], 0, [100, 100, 900, 900], "http://sam", 1.0)
        self.assertEqual(post_json.call_args.args[1]["anchor_source"], "pf")


if __name__ == "__main__":
    unittest.main()

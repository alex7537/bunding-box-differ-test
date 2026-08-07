import unittest

from libs.multi_anchor_validator import classify_evidence, select_stable_anchors


class MultiAnchorValidatorTest(unittest.TestCase):
    def test_selects_best_local_frame_from_each_segment(self):
        frames = [{"iou": value} for value in (0.1, 0.9, 0.2, 0.7, 0.3, 0.8)]
        self.assertEqual(select_stable_anchors(frames, 3), [1, 3, 5])

    def test_requires_reliable_consensus_before_suspecting_drift(self):
        self.assertEqual(
            classify_evidence(
                1, 0.9, 0.1,
                consensus_iou_threshold=0.5,
                deviation_iou_threshold=0.5,
            ),
            "tracker_unreliable",
        )
        self.assertEqual(
            classify_evidence(
                2, 0.8, 0.2,
                consensus_iou_threshold=0.5,
                deviation_iou_threshold=0.5,
            ),
            "suspected_perceptflow_drift",
        )
        self.assertEqual(
            classify_evidence(
                2, 0.8, 0.7,
                consensus_iou_threshold=0.5,
                deviation_iou_threshold=0.5,
            ),
            "supported",
        )


if __name__ == "__main__":
    unittest.main()

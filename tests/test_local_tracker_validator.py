import unittest

import numpy as np

from libs.local_tracker_validator import validate_adjacent_boxes


class _FakeTracker:
    def init(self, image, box):
        return True

    def update(self, image):
        return True, (10, 10, 20, 20)


class LocalTrackerValidatorTest(unittest.TestCase):
    def test_every_frame_is_reinitialized_and_checked_locally(self):
        images = [np.zeros((100, 100, 3), dtype=np.uint8) for _ in range(3)]
        boxes = [[100, 100, 300, 300] for _ in images]

        report = validate_adjacent_boxes(
            images,
            boxes,
            tracker_factory=_FakeTracker,
            iou_threshold=0.5,
        )

        self.assertEqual(report["supported_count"], 3)
        self.assertEqual([frame["evidence_count"] for frame in report["frames"]], [2, 4, 2])
        self.assertTrue(all(frame["iou"] == 1.0 for frame in report["frames"]))


if __name__ == "__main__":
    unittest.main()

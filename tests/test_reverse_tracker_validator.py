import unittest

import numpy as np

from libs.reverse_tracker_validator import box_iou, validate_boxes_from_anchor


class _FakeTracker:
    def __init__(self, boxes_by_frame, failed_frames=()):
        self.boxes_by_frame = boxes_by_frame
        self.failed_frames = set(failed_frames)

    def init(self, image, box):
        return True

    def update(self, image):
        frame_index = int(image[0, 0, 0])
        if frame_index in self.failed_frames:
            return False, (0, 0, 0, 0)
        return True, self.boxes_by_frame[frame_index]


class ReverseTrackerValidatorTest(unittest.TestCase):
    def test_iou(self):
        self.assertEqual(box_iou([0, 0, 10, 10], [0, 0, 10, 10]), 1)
        self.assertEqual(box_iou([0, 0, 10, 10], [20, 20, 30, 30]), 0)

    def test_anchor_covers_backward_and_forward_tail(self):
        images = [np.full((100, 100, 3), index, dtype=np.uint8) for index in range(5)]
        proposed = [
            [100, 100, 300, 300],
            [600, 600, 800, 800],
            [100, 100, 300, 300],
            [100, 100, 300, 300],
            [100, 100, 300, 300],
        ]
        tracker_boxes = {index: (10, 10, 20, 20) for index in range(5)}

        report = validate_boxes_from_anchor(
            images,
            proposed,
            tracker_factory=lambda: _FakeTracker(tracker_boxes),
            anchor_fraction=0.75,
            iou_threshold=0.5,
        )

        self.assertEqual(report["anchor_frame"], 4)
        self.assertEqual(report["review_frames"], [2])
        self.assertEqual(report["frames"][0]["direction"], "backward")
        self.assertEqual(report["frames"][4]["direction"], "forward_tail")

    def test_tracking_failure_flags_current_and_remaining_branch_frames(self):
        images = [np.full((100, 100, 3), index, dtype=np.uint8) for index in range(4)]
        proposed = [[100, 100, 300, 300] for _ in images]
        tracker_boxes = {index: (10, 10, 20, 20) for index in range(4)}

        report = validate_boxes_from_anchor(
            images,
            proposed,
            tracker_factory=lambda: _FakeTracker(tracker_boxes, failed_frames={1}),
            anchor_fraction=0.75,
        )

        self.assertEqual(report["anchor_frame"], 3)
        self.assertEqual(report["review_frames"], [1, 2])
        self.assertEqual(report["frames"][0]["status"], "tracking_failed")
        self.assertEqual(report["frames"][1]["status"], "tracking_failed")


if __name__ == "__main__":
    unittest.main()

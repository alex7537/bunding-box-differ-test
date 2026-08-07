from unittest import TestCase

from libs.opencv_tracker import OpenCVTracker


class TestOpenCVTrackerAvailability(TestCase):
    def test_available_tracker_can_be_created(self):
        tracker = OpenCVTracker.__new__(OpenCVTracker)
        self.assertTrue(OpenCVTracker.is_tracker_available('inner_opencv_tracker_CSRT'))
        self.assertIsNotNone(tracker.createTrackerByName('inner_opencv_tracker_CSRT'))

    def test_unavailable_tracker_is_rejected(self):
        tracker = OpenCVTracker.__new__(OpenCVTracker)
        self.assertFalse(OpenCVTracker.is_tracker_available('inner_opencv_tracker_UNKNOWN'))
        self.assertIsNone(tracker.createTrackerByName('inner_opencv_tracker_UNKNOWN'))

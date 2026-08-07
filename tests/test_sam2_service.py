import tempfile
from pathlib import Path
import unittest

import numpy as np

from sam2_service.app import mask_to_box, resolve_frames, validate_anchor_source, validate_box


class Sam2ServiceContractTest(unittest.TestCase):
    def test_mask_to_box_uses_exclusive_max_corner(self):
        mask = np.zeros((8, 10), dtype=bool)
        mask[2:6, 3:9] = True
        self.assertEqual(mask_to_box(mask), [3, 2, 9, 6])

    def test_empty_mask_has_no_box(self):
        self.assertIsNone(mask_to_box(np.zeros((3, 4), dtype=bool)))

    def test_box_must_be_inside_image(self):
        self.assertEqual(validate_box([1, 2, 9, 8], 10, 10), [1.0, 2.0, 9.0, 8.0])
        with self.assertRaisesRegex(ValueError, "inside the image"):
            validate_box([-1, 2, 9, 8], 10, 10)

    def test_frames_cannot_escape_allowed_root(self):
        with tempfile.TemporaryDirectory() as directory:
            allowed = Path(directory) / "allowed"
            outside = Path(directory) / "outside"
            allowed.mkdir()
            outside.mkdir()
            with self.assertRaisesRegex(ValueError, "must be under"):
                resolve_frames(str(outside), allowed)

    def test_anchor_source_is_explicit_and_validated(self):
        for source in ("pf", "human", "redetection"):
            self.assertEqual(validate_anchor_source(source), source)
        with self.assertRaisesRegex(ValueError, "anchor_source"):
            validate_anchor_source(None)
        with self.assertRaisesRegex(ValueError, "anchor_source"):
            validate_anchor_source("human_prompt")


if __name__ == "__main__":
    unittest.main()

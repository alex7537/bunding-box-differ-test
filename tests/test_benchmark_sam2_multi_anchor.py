import unittest

from tools.benchmark_sam2_multi_anchor import choose_anchor_frame, select_consensus_anchor


class BenchmarkSam2MultiAnchorTest(unittest.TestCase):
    def test_choose_anchor_uses_nearest_valid_pf_box(self):
        references = [{"box": [0, 0, 1, 1]}, {"box": None}, {"box": [0, 0, 1, 1]}]
        self.assertEqual(choose_anchor_frame(references, 0.5), 1)

    def test_consensus_selects_track_closest_to_other_tracks(self):
        tracks = {
            1: [[0, 0, 10, 10], [0, 0, 10, 10]],
            2: [[1, 0, 11, 10], [1, 0, 11, 10]],
            3: [[50, 50, 60, 60], [50, 50, 60, 60]],
        }
        selected, support, pairs = select_consensus_anchor([1, 2, 3], tracks, 0.7)
        self.assertEqual(selected, 2)
        self.assertEqual(pairs, [[1, 2]])
        self.assertGreater(support["1"], support["3"])

    def test_consensus_does_not_force_a_choice_when_all_tracks_disagree(self):
        tracks = {
            1: [[0, 0, 10, 10]],
            2: [[20, 20, 30, 30]],
            3: [[40, 40, 50, 50]],
        }
        selected, _support, pairs = select_consensus_anchor([1, 2, 3], tracks, 0.7)
        self.assertIsNone(selected)
        self.assertEqual(pairs, [])


if __name__ == "__main__":
    unittest.main()

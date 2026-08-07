import unittest

from tools.evaluate_sam2_review_labels import evaluate_rows, parse_optional_bool


class Sam2ReviewEvaluationTest(unittest.TestCase):
    def test_optional_boolean_parser(self):
        self.assertIs(parse_optional_bool("true"), True)
        self.assertIs(parse_optional_bool("0"), False)
        self.assertIsNone(parse_optional_bool(""))
        with self.assertRaisesRegex(ValueError, "invalid boolean"):
            parse_optional_bool("maybe")

    def test_metrics_ignore_out_of_scope_and_pending_rows(self):
        rows = [
            {"grasp_active": "true", "human_gt": "SAM_CORRECT"},
            {"grasp_active": "true", "human_gt": "BOTH_WRONG"},
            {"grasp_active": "true", "human_gt": "PF_CORRECT"},
            {"grasp_active": "false", "human_gt": ""},
            {"grasp_active": "true", "human_gt": ""},
        ]
        report = evaluate_rows(rows)
        self.assertEqual(report["evaluated_count"], 3)
        self.assertEqual(report["excluded_count"], 1)
        self.assertEqual(report["pending_count"], 1)
        self.assertAlmostEqual(report["pf_error_alert_precision"], 2 / 3)
        self.assertAlmostEqual(report["sam_win_rate_when_pf_wrong"], 1 / 2)
        self.assertIs(report["auto_adoption_ready"], False)


if __name__ == "__main__":
    unittest.main()

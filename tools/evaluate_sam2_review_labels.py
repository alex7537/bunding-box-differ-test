#!/usr/bin/env python3
"""Summarize completed human labels from a SAM2 review CSV."""

import argparse
import csv
import json
from pathlib import Path


GT_VALUES = {"PF_CORRECT", "SAM_CORRECT", "BOTH_OK", "BOTH_WRONG", "IGNORE"}


def parse_optional_bool(value):
    normalized = str(value).strip().lower()
    if normalized in {"", "none", "null"}:
        return None
    if normalized in {"1", "true", "yes"}:
        return True
    if normalized in {"0", "false", "no"}:
        return False
    raise ValueError(f"invalid boolean value: {value!r}")


def evaluate_rows(rows):
    counts = {value: 0 for value in sorted(GT_VALUES)}
    pending = 0
    excluded = 0
    evaluated = []
    for row in rows:
        grasp_active = parse_optional_bool(row.get("grasp_active", ""))
        gt = row.get("human_gt", "").strip().upper()
        if grasp_active is False or gt == "IGNORE":
            excluded += 1
            if gt == "IGNORE":
                counts[gt] += 1
            continue
        if not gt:
            pending += 1
            continue
        if gt not in GT_VALUES:
            raise ValueError(f"invalid human_gt: {gt!r}")
        counts[gt] += 1
        evaluated.append(gt)

    pf_error_count = sum(gt in {"SAM_CORRECT", "BOTH_WRONG"} for gt in evaluated)
    sam_error_count = sum(gt in {"PF_CORRECT", "BOTH_WRONG"} for gt in evaluated)
    sam_win_count = sum(gt == "SAM_CORRECT" for gt in evaluated)
    return {
        "row_count": len(rows),
        "evaluated_count": len(evaluated),
        "pending_count": pending,
        "excluded_count": excluded,
        "label_counts": counts,
        "pf_error_alert_precision": None if not evaluated else pf_error_count / len(evaluated),
        "sam_error_rate_on_alerts": None if not evaluated else sam_error_count / len(evaluated),
        "sam_win_rate_when_pf_wrong": None if not pf_error_count else sam_win_count / pf_error_count,
        "auto_adoption_ready": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("review_csv", type=Path)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    with args.review_csv.open(newline="", encoding="utf-8-sig") as handle:
        report = evaluate_rows(list(csv.DictReader(handle)))
    text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output is None:
        print(text, end="")
    else:
        args.output.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()

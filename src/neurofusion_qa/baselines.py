
"""Simple comparison baselines for IdentityGuard-BIDS."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any, Iterable


@dataclass(frozen=True)
class BaselineResult:
    """Output from a deliberately limited baseline."""

    baseline: str
    detected: bool
    details: dict[str, Any]


def basic_duplicate_check(
    records: Iterable[Any],
) -> BaselineResult:
    """Flag exact duplicate full records only."""
    counts = Counter(records)
    duplicate_records = [
        {"record": repr(record), "count": count}
        for record, count in counts.items()
        if count > 1
    ]

    return BaselineResult(
        baseline="basic_duplicate_check",
        detected=bool(duplicate_records),
        details={
            "duplicate_record_groups": len(duplicate_records),
            "duplicate_extra_rows": sum(
                item["count"] - 1 for item in duplicate_records
            ),
            "duplicate_records": duplicate_records,
        },
    )


def naive_inner_join(
    left_records: Iterable[Any],
    right_records: Iterable[Any],
) -> BaselineResult:
    """Inner join on raw participant_id without validation."""
    left = list(left_records)
    right = list(right_records)

    left_ids: dict[str, list[Any]] = {}
    right_ids: dict[str, list[Any]] = {}

    for record in left:
        left_ids.setdefault(record.participant_id, []).append(record)

    for record in right:
        right_ids.setdefault(record.participant_id, []).append(record)

    joined_rows = sum(
        len(left_ids[participant_id]) * len(right_ids[participant_id])
        for participant_id in left_ids.keys() & right_ids.keys()
    )

    matched_left_rows = sum(
        len(left_ids[participant_id])
        for participant_id in left_ids.keys() & right_ids.keys()
    )
    matched_right_rows = sum(
        len(right_ids[participant_id])
        for participant_id in left_ids.keys() & right_ids.keys()
    )

    return BaselineResult(
        baseline="naive_join",
        detected=False,
        details={
            "join_key": "raw participant_id",
            "join_type": "inner",
            "left_input_rows": len(left),
            "right_input_rows": len(right),
            "joined_rows": joined_rows,
            "matched_left_rows": matched_left_rows,
            "matched_right_rows": matched_right_rows,
            "unmatched_left_rows": len(left) - matched_left_rows,
            "unmatched_right_rows": len(right) - matched_right_rows,
            "row_count_inflation_vs_left": joined_rows - len(left),
            "left_unique_participant_ids": len(left_ids),
            "right_unique_participant_ids": len(right_ids),
            "row_count_change_vs_matched_left": (
                joined_rows - matched_left_rows
            ),
        },
    )

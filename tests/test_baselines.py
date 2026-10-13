
from neurofusion_qa.baselines import (
    basic_duplicate_check,
    naive_inner_join,
)
from neurofusion_qa.benchmark import build_synthetic_manifest


def test_basic_duplicate_check_flags_exact_duplicate_rows():
    records = build_synthetic_manifest(
        people=2,
        modalities=2,
        sessions=1,
        runs_per_modality=1,
    )

    result = basic_duplicate_check(records + [records[0]])

    assert result.baseline == "basic_duplicate_check"
    assert result.detected is True
    assert result.details["duplicate_record_groups"] == 1
    assert result.details["duplicate_extra_rows"] == 1


def test_basic_duplicate_check_does_not_flag_distinct_rows():
    records = build_synthetic_manifest(
        people=2,
        modalities=2,
        sessions=1,
        runs_per_modality=1,
    )

    result = basic_duplicate_check(records)

    assert result.detected is False
    assert result.details["duplicate_record_groups"] == 0
    assert result.details["duplicate_extra_rows"] == 0


def test_basic_duplicate_check_does_not_flag_same_person_different_rows():
    records = build_synthetic_manifest(
        people=1,
        modalities=2,
        sessions=1,
        runs_per_modality=1,
    )

    result = basic_duplicate_check(records)

    assert result.detected is False


def test_naive_inner_join_uses_raw_participant_id():
    records = build_synthetic_manifest(
        people=2,
        modalities=2,
        sessions=1,
        runs_per_modality=1,
    )

    left = [record for record in records if record.modality == "mod-01"]
    right = [record for record in records if record.modality == "mod-02"]

    result = naive_inner_join(left, right)

    assert result.baseline == "naive_join"
    assert result.details["join_key"] == "raw participant_id"
    assert result.details["join_type"] == "inner"
    assert result.details["joined_rows"] == 2
    assert result.details["unmatched_left_rows"] == 0
    assert result.details["unmatched_right_rows"] == 0
    assert result.detected is False


def test_naive_inner_join_reports_row_multiplication():
    records = build_synthetic_manifest(
        people=1,
        modalities=2,
        sessions=1,
        runs_per_modality=1,
    )

    left = [records[0], records[0]]
    right = [records[1], records[1]]

    result = naive_inner_join(left, right)

    assert result.details["joined_rows"] == 4
    assert result.details["row_count_inflation_vs_left"] == 2

def test_naive_inner_join_reports_repeated_raw_ids():
    records = build_synthetic_manifest(
        people=1,
        modalities=2,
        sessions=1,
        runs_per_modality=1,
    )

    left = [records[0], records[0]]
    right = [records[1]]

    result = naive_inner_join(left, right)

    assert result.details["left_unique_participant_ids"] == 1
    assert result.details["right_unique_participant_ids"] == 1
    assert result.details["joined_rows"] == 2
    assert result.details["row_count_change_vs_matched_left"] == 0
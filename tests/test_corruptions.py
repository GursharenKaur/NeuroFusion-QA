from dataclasses import replace

from neurofusion_qa.manifest import ManifestRecord
from neurofusion_qa.identity import canonicalize_participant_id
from neurofusion_qa.identity import check_i6_metric_denominator_traceability

from neurofusion_qa.corruptions import inject_corruption
from neurofusion_qa.benchmark import build_synthetic_manifest

def test_c1_namespace_stripping_changes_namespace():
    records = [
        ManifestRecord(
            dataset_namespace="dataset_a",
            dataset_version="1.0",
            participant_id="sub-01",
            modality="bold",
        ),
        ManifestRecord(
            dataset_namespace="dataset_b",
            dataset_version="1.0",
            participant_id="sub-01",
            modality="bold",
        ),
    ]

    corrupted, truth = inject_corruption(
        records,
        corruption="C1_namespace_stripping",
        affected_count=1,
        seed=20270915,
    )

    assert len(corrupted) == len(records)

    assert any(
        record.dataset_namespace is None
        for record in corrupted
    )

    assert truth["corruption"] == "C1_namespace_stripping"


def test_c1_preserves_participant_id():
    records = [
        ManifestRecord(
            dataset_namespace="dataset_a",
            dataset_version="1.0",
            participant_id="sub-01",
            modality="bold",
        ),
        ManifestRecord(
            dataset_namespace="dataset_b",
            dataset_version="1.0",
            participant_id="sub-02",
            modality="bold",
        ),
    ]

    corrupted, _ = inject_corruption(
        records,
        corruption="C1_namespace_stripping",
        affected_count=1,
        seed=20270915,
    )

    assert [
        record.participant_id
        for record in corrupted
    ] == [
        record.participant_id
        for record in records
    ]


def test_c1_does_not_modify_original_records():
    records = [
        ManifestRecord(
            dataset_namespace="dataset_a",
            dataset_version="1.0",
            participant_id="sub-01",
        ),
        ManifestRecord(
            dataset_namespace="dataset_b",
            dataset_version="1.0",
            participant_id="sub-02",
        ),
    ]

    original_namespaces = [
        record.dataset_namespace
        for record in records
    ]

    inject_corruption(
        records,
        corruption="C1_namespace_stripping",
        affected_count=1,
        seed=20270915,
    )

    assert [
        record.dataset_namespace
        for record in records
    ] == original_namespaces


def test_c1_truth_contains_seed_and_affected_keys():
    records = [
        ManifestRecord(
            dataset_namespace="dataset_a",
            dataset_version="1.0",
            participant_id="sub-01",
        ),
        ManifestRecord(
            dataset_namespace="dataset_b",
            dataset_version="1.0",
            participant_id="sub-02",
        ),
    ]

    _, truth = inject_corruption(
        records,
        corruption="C1_namespace_stripping",
        affected_count=1,
        seed=12345,
    )

    assert truth["seed"] == 12345
    assert "affected_keys" in truth
    assert len(truth["affected_keys"]) == 1
    assert truth["expected_violations"] == ["I1.namespace_completeness"]


def test_c1_is_deterministic_for_same_seed():
    records = [
        ManifestRecord(
            dataset_namespace="dataset_a",
            dataset_version="1.0",
            participant_id="sub-01",
        ),
        ManifestRecord(
            dataset_namespace="dataset_b",
            dataset_version="1.0",
            participant_id="sub-02",
        ),
        ManifestRecord(
            dataset_namespace="dataset_a",
            dataset_version="1.0",
            participant_id="sub-03",
        ),
    ]

    corrupted_a, truth_a = inject_corruption(
        records,
        corruption="C1_namespace_stripping",
        affected_count=2,
        seed=20270915,
    )

    corrupted_b, truth_b = inject_corruption(
        records,
        corruption="C1_namespace_stripping",
        affected_count=2,
        seed=20270915,
    )

    assert corrupted_a == corrupted_b
    assert truth_a == truth_b


def test_c1_rejects_invalid_affected_count():
    records = [
        ManifestRecord(
            dataset_namespace="dataset_a",
            dataset_version="1.0",
            participant_id="sub-01",
        ),
    ]

    try:
        inject_corruption(
            records,
            corruption="C1_namespace_stripping",
            affected_count=2,
            seed=20270915,
        )
    except ValueError:
        pass
    else:
        raise AssertionError(
            "Expected ValueError when affected_count exceeds "
            "the number of eligible records."
        )

def test_c2_creates_canonicalization_collision():
    records = [
        ManifestRecord(
            dataset_namespace="dataset_a",
            dataset_version="1.0",
            participant_id="sub-01",
            modality="bold",
        ),
        ManifestRecord(
            dataset_namespace="dataset_a",
            dataset_version="1.0",
            participant_id="sub-02",
            modality="bold",
        ),
    ]

    corrupted, truth = inject_corruption(
        records,
        corruption="C2_canonicalization_collision",
        affected_count=1,
        seed=20270915,
    )

    assert len(corrupted) == len(records)

    canonical_ids = [
        canonicalize_participant_id(record.participant_id)
        for record in corrupted
    ]

    assert len(canonical_ids) != len(set(canonical_ids))
    assert truth["corruption"] == "C2_canonicalization_collision"


def test_c2_preserves_raw_ids_of_unaffected_records():
    records = [
        ManifestRecord(
            dataset_namespace="dataset_a",
            dataset_version="1.0",
            participant_id="sub-01",
            modality="bold",
        ),
        ManifestRecord(
            dataset_namespace="dataset_a",
            dataset_version="1.0",
            participant_id="sub-02",
            modality="bold",
        ),
        ManifestRecord(
            dataset_namespace="dataset_a",
            dataset_version="1.0",
            participant_id="sub-03",
            modality="bold",
        ),
    ]

    corrupted, truth = inject_corruption(
        records,
        corruption="C2_canonicalization_collision",
        affected_count=1,
        seed=20270915,
    )

    affected_indices = {
        operation["target_row_index"]
        for operation in truth["operations"]
    }

    for index, (original, changed) in enumerate(zip(records, corrupted)):
        if index not in affected_indices:
            assert changed.participant_id == original.participant_id

def test_c2_does_not_modify_original_records():
    records = [
        ManifestRecord(
            dataset_namespace="dataset_a",
            dataset_version="1.0",
            participant_id="sub-01",
            modality="bold",
        ),
        ManifestRecord(
            dataset_namespace="dataset_a",
            dataset_version="1.0",
            participant_id="sub-02",
            modality="bold",
        ),
    ]

    original = list(records)

    inject_corruption(
        records,
        corruption="C2_canonicalization_collision",
        affected_count=1,
        seed=20270915,
    )

    assert records == original

def test_c2_selects_collision_pairs_within_namespace_and_version():
    records = build_synthetic_manifest(
        people=8,
        modalities=2,
        sessions=1,
        runs_per_modality=1,
    )

    # Split participants into two namespace groups while keeping each
    # participant's modality records together.
    mixed_records = [
        replace(
            record,
            dataset_namespace=(
                "dataset_b"
                if int(record.participant_id.removeprefix("sub-")) > 4
                else "dataset_a"
            ),
            dataset_version="1.0",
        )
        for record in records
    ]

    corrupted, truth = inject_corruption(
        mixed_records,
        corruption="C2_canonicalization_collision",
        affected_count=2,
        seed=20270915,
    )

    assert len(truth["operations"]) == 2
    assert len(truth["affected_keys"]) == 2
    # Each collision operation must pair records from the same
    # namespace and dataset version.
    for operation in truth["operations"]:
        donor = mixed_records[operation["donor_row_index"]]
        target = mixed_records[operation["target_row_index"]]

        assert donor.dataset_namespace == target.dataset_namespace
        assert donor.dataset_version == target.dataset_version

        # The operation must produce the declared canonical identity.
        assert (
            canonicalize_participant_id(operation["new_target_participant_id"])
            == operation["canonical_participant_id"]
        )

    selected_people = set()

    for operation in truth["operations"]:
        donor = mixed_records[operation["donor_row_index"]]
        target = mixed_records[operation["target_row_index"]]

        assert donor.person_key not in selected_people
        assert target.person_key not in selected_people

        selected_people.add(donor.person_key)
        selected_people.add(target.person_key)

    # Namespace and version must not change during C2.
    for original, changed in zip(mixed_records, corrupted):
        assert changed.dataset_namespace == original.dataset_namespace
        assert changed.dataset_version == original.dataset_version

def test_c2_truth_contains_required_metadata():
    records = [
        ManifestRecord(
            dataset_namespace="dataset_a",
            dataset_version="1.0",
            participant_id="sub-01",
            modality="bold",
        ),
        ManifestRecord(
            dataset_namespace="dataset_a",
            dataset_version="1.0",
            participant_id="sub-02",
            modality="bold",
        ),
    ]

    _, truth = inject_corruption(
        records,
        corruption="C2_canonicalization_collision",
        affected_count=1,
        seed=12345,
    )

    assert truth["seed"] == 12345
    assert "parent_manifest_sha256" in truth
    assert "operations" in truth
    assert "affected_keys" in truth
    assert "expected_violations" in truth

    assert "I1.canonicalization_collision" in truth["expected_violations"]


def test_c2_is_deterministic_for_same_seed():
    records = [
        ManifestRecord(
            dataset_namespace="dataset_a",
            dataset_version="1.0",
            participant_id="sub-01",
            modality="bold",
        ),
        ManifestRecord(
            dataset_namespace="dataset_a",
            dataset_version="1.0",
            participant_id="sub-02",
            modality="bold",
        ),
        ManifestRecord(
            dataset_namespace="dataset_a",
            dataset_version="1.0",
            participant_id="sub-03",
            modality="bold",
        ),
        ManifestRecord(
            dataset_namespace="dataset_a",
            dataset_version="1.0",
            participant_id="sub-04",
            modality="bold",
        ),
    ]

    corrupted_a, truth_a = inject_corruption(
        records,
        corruption="C2_canonicalization_collision",
        affected_count=1,
        seed=20270915,
    )

    corrupted_b, truth_b = inject_corruption(
        records,
        corruption="C2_canonicalization_collision",
        affected_count=1,
        seed=20270915,
    )

    assert corrupted_a == corrupted_b
    assert truth_a == truth_b


def test_c2_rejects_invalid_affected_count():
    records = [
        ManifestRecord(
            dataset_namespace="dataset_a",
            dataset_version="1.0",
            participant_id="sub-01",
            modality="bold",
        ),
        ManifestRecord(
            dataset_namespace="dataset_a",
            dataset_version="1.0",
            participant_id="sub-02",
            modality="bold",
        ),
    ]

    try:
        inject_corruption(
            records,
            corruption="C2_canonicalization_collision",
            affected_count=2,
            seed=20270915,
        )
    except ValueError:
        pass
    else:
        raise AssertionError("Expected ValueError for unsupported affected_count.")

def test_c3_duplicates_selected_row():
    records = [
        ManifestRecord(
            dataset_namespace="dataset_a",
            dataset_version="1.0",
            participant_id="sub-01",
            modality="bold",
            source_path="sub-01_bold.nii.gz",
            source_sha256="hash-01",
        ),
        ManifestRecord(
            dataset_namespace="dataset_a",
            dataset_version="1.0",
            participant_id="sub-02",
            modality="bold",
            source_path="sub-02_bold.nii.gz",
            source_sha256="hash-02",
        ),
    ]

    corrupted, truth = inject_corruption(
        records,
        corruption="C3_duplicate_propagation",
        affected_count=1,
        seed=20270915,
    )

    assert len(corrupted) == len(records) + 1
    assert truth["corruption"] == "C3_duplicate_propagation"

    duplicated = corrupted[-1]
    assert duplicated in records


def test_c3_preserves_original_records():
    records = [
        ManifestRecord(
            dataset_namespace="dataset_a",
            dataset_version="1.0",
            participant_id="sub-01",
            modality="bold",
            source_path="sub-01_bold.nii.gz",
            source_sha256="hash-01",
        ),
        ManifestRecord(
            dataset_namespace="dataset_a",
            dataset_version="1.0",
            participant_id="sub-02",
            modality="bold",
            source_path="sub-02_bold.nii.gz",
            source_sha256="hash-02",
        ),
    ]

    original = list(records)

    inject_corruption(
        records,
        corruption="C3_duplicate_propagation",
        affected_count=1,
        seed=20270915,
    )

    assert records == original


def test_c3_truth_contains_required_metadata():
    records = [
        ManifestRecord(
            dataset_namespace="dataset_a",
            dataset_version="1.0",
            participant_id="sub-01",
            modality="bold",
            source_path="sub-01_bold.nii.gz",
            source_sha256="hash-01",
        ),
        ManifestRecord(
            dataset_namespace="dataset_a",
            dataset_version="1.0",
            participant_id="sub-02",
            modality="bold",
            source_path="sub-02_bold.nii.gz",
            source_sha256="hash-02",
        ),
    ]

    _, truth = inject_corruption(
        records,
        corruption="C3_duplicate_propagation",
        affected_count=1,
        seed=12345,
    )

    assert truth["seed"] == 12345
    assert "parent_manifest_sha256" in truth
    assert "operations" in truth
    assert "affected_keys" in truth
    assert "expected_violations" in truth

    assert truth["expected_violations"] == [
        "I2.cardinality_mismatch",
        "I4.repeated_row",
        "I4.repeated_source_path",
        "I6.denominator_mismatch",
    ]

def test_c3_ignores_records_with_missing_identity_fields():
    eligible = ManifestRecord(
        dataset_namespace="dataset_a",
        dataset_version="1.0",
        participant_id="sub-01",
        modality="bold",
        source_path="sub-01_bold.nii.gz",
        source_sha256="hash-01",
    )
    missing_namespace = ManifestRecord(
        dataset_namespace=None,
        dataset_version="1.0",
        participant_id="sub-02",
        modality="bold",
        source_path="sub-02_bold.nii.gz",
        source_sha256="hash-02",
    )

    corrupted, truth = inject_corruption(
        [eligible, missing_namespace],
        corruption="C3_duplicate_propagation",
        affected_count=1,
        seed=20270915,
    )

    assert len(corrupted) == 3
    assert corrupted[:2] == [eligible, missing_namespace]
    assert corrupted[2] == eligible

    operation = truth["operations"][0]
    assert operation["source_row_index"] == 0
    assert operation["duplicated_row_index"] == 2
    assert operation["affected_person_key"] == eligible.person_key

def test_c3_truth_records_acquisition_key():
    records = [
        ManifestRecord(
            dataset_namespace="dataset_a",
            dataset_version="1.0",
            participant_id="sub-01",
            session_id="ses-01",
            modality="bold",
            source_path="sub-01_ses-01_bold.nii.gz",
            source_sha256="hash-01",
        ),
        ManifestRecord(
            dataset_namespace="dataset_a",
            dataset_version="1.0",
            participant_id="sub-02",
            session_id="ses-01",
            modality="bold",
            source_path="sub-02_ses-01_bold.nii.gz",
            source_sha256="hash-02",
        ),
    ]

    corrupted, truth = inject_corruption(
        records,
        corruption="C3_duplicate_propagation",
        affected_count=1,
        seed=20270915,
    )

    assert len(truth["affected_keys"]) == 1
    assert truth["affected_keys"][0] in [
        record.acquisition_key for record in records
    ]

    operation = truth["operations"][0]

    assert "source_row_index" in operation
    assert "duplicated_row_index" in operation
    assert "affected_acquisition_key" in operation

    assert corrupted[operation["duplicated_row_index"]] == records[
        operation["source_row_index"]
    ]


def test_c3_is_deterministic_for_same_seed():
    records = [
        ManifestRecord(
            dataset_namespace="dataset_a",
            dataset_version="1.0",
            participant_id="sub-01",
            modality="bold",
            source_path="sub-01_bold.nii.gz",
            source_sha256="hash-01",
        ),
        ManifestRecord(
            dataset_namespace="dataset_a",
            dataset_version="1.0",
            participant_id="sub-02",
            modality="bold",
            source_path="sub-02_bold.nii.gz",
            source_sha256="hash-02",
        ),
        ManifestRecord(
            dataset_namespace="dataset_a",
            dataset_version="1.0",
            participant_id="sub-03",
            modality="bold",
            source_path="sub-03_bold.nii.gz",
            source_sha256="hash-03",
        ),
    ]

    corrupted_a, truth_a = inject_corruption(
        records,
        corruption="C3_duplicate_propagation",
        affected_count=2,
        seed=20270915,
    )

    corrupted_b, truth_b = inject_corruption(
        records,
        corruption="C3_duplicate_propagation",
        affected_count=2,
        seed=20270915,
    )

    assert corrupted_a == corrupted_b
    assert truth_a == truth_b


def test_c3_rejects_invalid_affected_count():
    records = [
        ManifestRecord(
            dataset_namespace="dataset_a",
            dataset_version="1.0",
            participant_id="sub-01",
            modality="bold",
        )
    ]

    try:
        inject_corruption(
            records,
            corruption="C3_duplicate_propagation",
            affected_count=2,
            seed=20270915,
        )
    except ValueError:
        pass
    else:
        raise AssertionError(
            "Expected ValueError when affected_count exceeds "
            "available records."
        )

def test_c4_permutates_cross_modal_pairing():
    records = [
        ManifestRecord(
            dataset_namespace="dataset_a",
            dataset_version="1.0",
            participant_id="sub-01",
            session_id="ses-01",
            modality="T1w",
            source_path="sub-01_T1w.nii.gz",
        ),
        ManifestRecord(
            dataset_namespace="dataset_a",
            dataset_version="1.0",
            participant_id="sub-01",
            session_id="ses-01",
            modality="bold",
            source_path="sub-01_bold.nii.gz",
        ),
        ManifestRecord(
            dataset_namespace="dataset_a",
            dataset_version="1.0",
            participant_id="sub-02",
            session_id="ses-01",
            modality="T1w",
            source_path="sub-02_T1w.nii.gz",
        ),
        ManifestRecord(
            dataset_namespace="dataset_a",
            dataset_version="1.0",
            participant_id="sub-02",
            session_id="ses-01",
            modality="bold",
            source_path="sub-02_bold.nii.gz",
        ),
    ]

    corrupted, truth = inject_corruption(
        records,
        corruption="C4_cross_modal_permutation",
        affected_count=1,
        seed=20270915,
    )

    assert len(corrupted) == len(records)
    assert truth["corruption"] == "C4_cross_modal_permutation"
    assert "I3.person_pairing" in truth["expected_violations"]


def test_c4_preserves_raw_records():
    records = [
        ManifestRecord(
            dataset_namespace="dataset_a",
            dataset_version="1.0",
            participant_id="sub-01",
            modality="T1w",
        ),
        ManifestRecord(
            dataset_namespace="dataset_a",
            dataset_version="1.0",
            participant_id="sub-01",
            modality="bold",
        ),
        ManifestRecord(
            dataset_namespace="dataset_a",
            dataset_version="1.0",
            participant_id="sub-02",
            modality="T1w",
        ),
        ManifestRecord(
            dataset_namespace="dataset_a",
            dataset_version="1.0",
            participant_id="sub-02",
            modality="bold",
        ),
    ]

    original = list(records)

    inject_corruption(
        records,
        corruption="C4_cross_modal_permutation",
        affected_count=1,
        seed=20270915,
    )

    assert records == original


def test_c4_does_not_change_number_of_records():
    records = [
        ManifestRecord(
            dataset_namespace="dataset_a",
            dataset_version="1.0",
            participant_id="sub-01",
            modality="T1w",
        ),
        ManifestRecord(
            dataset_namespace="dataset_a",
            dataset_version="1.0",
            participant_id="sub-01",
            modality="bold",
        ),
        ManifestRecord(
            dataset_namespace="dataset_a",
            dataset_version="1.0",
            participant_id="sub-02",
            modality="T1w",
        ),
        ManifestRecord(
            dataset_namespace="dataset_a",
            dataset_version="1.0",
            participant_id="sub-02",
            modality="bold",
        ),
    ]

    corrupted, _ = inject_corruption(
        records,
        corruption="C4_cross_modal_permutation",
        affected_count=1,
        seed=20270915,
    )

    assert len(corrupted) == len(records)


def test_c4_truth_contains_required_metadata():
    records = [
        ManifestRecord(
            dataset_namespace="dataset_a",
            dataset_version="1.0",
            participant_id="sub-01",
            modality="T1w",
        ),
        ManifestRecord(
            dataset_namespace="dataset_a",
            dataset_version="1.0",
            participant_id="sub-01",
            modality="bold",
        ),
        ManifestRecord(
            dataset_namespace="dataset_a",
            dataset_version="1.0",
            participant_id="sub-02",
            modality="T1w",
        ),
        ManifestRecord(
            dataset_namespace="dataset_a",
            dataset_version="1.0",
            participant_id="sub-02",
            modality="bold",
        ),
    ]

    _, truth = inject_corruption(
        records,
        corruption="C4_cross_modal_permutation",
        affected_count=1,
        seed=12345,
    )

    assert truth["seed"] == 12345
    assert "parent_manifest_sha256" in truth
    assert "operations" in truth
    assert "affected_keys" in truth
    assert "expected_violations" in truth
    assert "I3.person_pairing" in truth["expected_violations"]


def test_c4_is_deterministic_for_same_seed():
    records = [
        ManifestRecord(
            dataset_namespace="dataset_a",
            dataset_version="1.0",
            participant_id="sub-01",
            modality="T1w",
        ),
        ManifestRecord(
            dataset_namespace="dataset_a",
            dataset_version="1.0",
            participant_id="sub-01",
            modality="bold",
        ),
        ManifestRecord(
            dataset_namespace="dataset_a",
            dataset_version="1.0",
            participant_id="sub-02",
            modality="T1w",
        ),
        ManifestRecord(
            dataset_namespace="dataset_a",
            dataset_version="1.0",
            participant_id="sub-02",
            modality="bold",
        ),
    ]

    corrupted_a, truth_a = inject_corruption(
        records,
        corruption="C4_cross_modal_permutation",
        affected_count=1,
        seed=20270915,
    )

    corrupted_b, truth_b = inject_corruption(
        records,
        corruption="C4_cross_modal_permutation",
        affected_count=1,
        seed=20270915,
    )

    assert corrupted_a == corrupted_b
    assert truth_a == truth_b


def test_c4_rejects_invalid_affected_count():
    records = [
        ManifestRecord(
            dataset_namespace="dataset_a",
            dataset_version="1.0",
            participant_id="sub-01",
            modality="T1w",
        ),
        ManifestRecord(
            dataset_namespace="dataset_a",
            dataset_version="1.0",
            participant_id="sub-01",
            modality="bold",
        ),
    ]

    try:
        inject_corruption(
            records,
            corruption="C4_cross_modal_permutation",
            affected_count=2,
            seed=20270915,
        )
    except ValueError:
        pass
    else:
        raise AssertionError(
            "Expected ValueError for invalid affected_count."
        )


def test_c4_ignores_people_without_same_namespace_version_targets():
    records = [
        # Only participant in dataset_a: cannot be a C4 source or target.
        ManifestRecord(
            dataset_namespace="dataset_a",
            dataset_version="1.0",
            participant_id="sub-01",
            modality="T1w",
        ),
        # Two participants in dataset_b: eligible for C4.
        ManifestRecord(
            dataset_namespace="dataset_b",
            dataset_version="1.0",
            participant_id="sub-02",
            modality="T1w",
        ),
        ManifestRecord(
            dataset_namespace="dataset_b",
            dataset_version="1.0",
            participant_id="sub-03",
            modality="T1w",
        ),
    ]

    corrupted, truth = inject_corruption(
        records,
        corruption="C4_cross_modal_permutation",
        affected_count=1,
        seed=20270915,
    )

    assert len(corrupted) == len(records)
    assert len(truth["operations"]) == 1

    operation = truth["operations"][0]
    assert operation["original_person_key"][0] == "dataset_b"
    assert operation["new_person_key"][0] == "dataset_b"
    assert operation["original_person_key"] != operation["new_person_key"]


def test_c4_target_identity_comes_from_original_manifest():
    records = [
        ManifestRecord(
            dataset_namespace="dataset_a",
            dataset_version="1.0",
            participant_id="sub-01",
            modality="T1w",
        ),
        ManifestRecord(
            dataset_namespace="dataset_a",
            dataset_version="1.0",
            participant_id="sub-01",
            modality="bold",
        ),
        ManifestRecord(
            dataset_namespace="dataset_a",
            dataset_version="1.0",
            participant_id="sub-02",
            modality="T1w",
        ),
        ManifestRecord(
            dataset_namespace="dataset_a",
            dataset_version="1.0",
            participant_id="sub-02",
            modality="bold",
        ),
        ManifestRecord(
            dataset_namespace="dataset_a",
            dataset_version="1.0",
            participant_id="sub-03",
            modality="T1w",
        ),
        ManifestRecord(
            dataset_namespace="dataset_a",
            dataset_version="1.0",
            participant_id="sub-03",
            modality="bold",
        ),
    ]

    corrupted, truth = inject_corruption(
        records,
        corruption="C4_cross_modal_permutation",
        affected_count=2,
        seed=17,
    )

    for operation in truth["operations"]:
        target_index = operation["target_row_index"]
        source_index = operation["source_row_index"]

        assert corrupted[source_index].participant_id == records[target_index].participant_id
        assert operation["new_person_key"] == corrupted[source_index].person_key


def test_c5_creates_subject_split_leakage():
    records = [
        ManifestRecord(
            dataset_namespace="dataset_a",
            dataset_version="1.0",
            participant_id="sub-01",
            session_id="ses-01",
            modality="T1w",
            run="01",
            split="train",
        ),
        ManifestRecord(
            dataset_namespace="dataset_a",
            dataset_version="1.0",
            participant_id="sub-01",
            session_id="ses-01",
            modality="bold",
            run="01",
            split="train",
        ),
        ManifestRecord(
            dataset_namespace="dataset_a",
            dataset_version="1.0",
            participant_id="sub-02",
            session_id="ses-01",
            modality="T1w",
            run="01",
            split="test",
        ),
    ]

    corrupted, truth = inject_corruption(
        records,
        corruption="C5_subject_split_leakage",
        affected_count=1,
        seed=20270915,
    )

    assert len(corrupted) == len(records)
    assert truth["corruption"] == "C5_subject_split_leakage"
    assert "I5.person_split_leakage" in truth["expected_violations"]


def test_c5_preserves_participant_identity():
    records = [
        ManifestRecord(
            dataset_namespace="dataset_a",
            dataset_version="1.0",
            participant_id="sub-01",
            modality="T1w",
            split="train",
        ),
        ManifestRecord(
            dataset_namespace="dataset_a",
            dataset_version="1.0",
            participant_id="sub-01",
            modality="bold",
            split="train",
        ),
        ManifestRecord(
            dataset_namespace="dataset_a",
            dataset_version="1.0",
            participant_id="sub-02",
            modality="T1w",
            split="test",
        ),
    ]

    corrupted, truth = inject_corruption(
        records,
        corruption="C5_subject_split_leakage",
        affected_count=1,
        seed=20270915,
    )

    for original, changed in zip(records, corrupted):
        assert original.person_key == changed.person_key

    assert len(truth["affected_keys"]) == 1


def test_c5_changes_split_assignment():
    records = [
        ManifestRecord(
            dataset_namespace="dataset_a",
            dataset_version="1.0",
            participant_id="sub-01",
            modality="T1w",
            split="train",
        ),
        ManifestRecord(
            dataset_namespace="dataset_a",
            dataset_version="1.0",
            participant_id="sub-01",
            modality="bold",
            split="train",
        ),
        ManifestRecord(
            dataset_namespace="dataset_a",
            dataset_version="1.0",
            participant_id="sub-02",
            modality="T1w",
            split="test",
        ),
    ]

    corrupted, truth = inject_corruption(
        records,
        corruption="C5_subject_split_leakage",
        affected_count=1,
        seed=20270915,
    )

    changed_indices = [
        index
        for index, (original, changed)
        in enumerate(zip(records, corrupted))
        if original.split != changed.split
    ]

    assert len(changed_indices) == 1

    index = changed_indices[0]
    operation = truth["operations"][0]

    assert operation["source_row_index"] == index
    assert operation["original_split"] == records[index].split
    assert operation["new_split"] == corrupted[index].split


def test_c5_does_not_modify_original_records():
    records = [
        ManifestRecord(
            dataset_namespace="dataset_a",
            dataset_version="1.0",
            participant_id="sub-01",
            modality="T1w",
            split="train",
        ),
        ManifestRecord(
            dataset_namespace="dataset_a",
            dataset_version="1.0",
            participant_id="sub-01",
            modality="bold",
            split="train",
        ),
        ManifestRecord(
            dataset_namespace="dataset_a",
            dataset_version="1.0",
            participant_id="sub-02",
            modality="T1w",
            split="test",
        ),
    ]

    original = list(records)

    inject_corruption(
        records,
        corruption="C5_subject_split_leakage",
        affected_count=1,
        seed=20270915,
    )

    assert records == original


def test_c5_truth_contains_required_metadata():
    records = [
        ManifestRecord(
            dataset_namespace="dataset_a",
            dataset_version="1.0",
            participant_id="sub-01",
            modality="T1w",
            split="train",
        ),
        ManifestRecord(
            dataset_namespace="dataset_a",
            dataset_version="1.0",
            participant_id="sub-01",
            modality="bold",
            split="train",
        ),
        ManifestRecord(
            dataset_namespace="dataset_a",
            dataset_version="1.0",
            participant_id="sub-02",
            modality="T1w",
            split="test",
        ),
    ]

    _, truth = inject_corruption(
        records,
        corruption="C5_subject_split_leakage",
        affected_count=1,
        seed=12345,
    )

    assert truth["seed"] == 12345
    assert "parent_manifest_sha256" in truth
    assert "operations" in truth
    assert "affected_keys" in truth
    assert "expected_violations" in truth
    assert "I5.person_split_leakage" in truth["expected_violations"]


def test_c5_is_deterministic_for_same_seed():
    records = [
        ManifestRecord(
            dataset_namespace="dataset_a",
            dataset_version="1.0",
            participant_id="sub-01",
            modality="T1w",
            split="train",
        ),
        ManifestRecord(
            dataset_namespace="dataset_a",
            dataset_version="1.0",
            participant_id="sub-01",
            modality="bold",
            split="train",
        ),
        ManifestRecord(
            dataset_namespace="dataset_a",
            dataset_version="1.0",
            participant_id="sub-02",
            modality="T1w",
            split="test",
        ),
    ]

    corrupted_a, truth_a = inject_corruption(
        records,
        corruption="C5_subject_split_leakage",
        affected_count=1,
        seed=20270915,
    )

    corrupted_b, truth_b = inject_corruption(
        records,
        corruption="C5_subject_split_leakage",
        affected_count=1,
        seed=20270915,
    )

    assert corrupted_a == corrupted_b
    assert truth_a == truth_b

def test_c6_creates_denominator_mismatch():
    records = [
        ManifestRecord(
            dataset_namespace="dataset_a",
            dataset_version="1.0",
            participant_id="sub-01",
            split="train",
        ),
        ManifestRecord(
            dataset_namespace="dataset_a",
            dataset_version="1.0",
            participant_id="sub-02",
            split="train",
        ),
        ManifestRecord(
            dataset_namespace="dataset_a",
            dataset_version="1.0",
            participant_id="sub-03",
            split="train",
        ),
    ]

    metrics = [
        {
            "metric_name": "accuracy",
            "population_key": "train_population",
            "numerator": 2,
            "denominator": 3,
        }
    ]

    populations = {
        "train_population": {
            "person_keys": [
                record.person_key
                for record in records
            ]
        }
    }

    corrupted_metrics, truth = inject_corruption(
        records,
        corruption="C6_denominator_mismatch",
        affected_count=1,
        seed=20270915,
        metrics=metrics,
        populations=populations,
    )

    assert corrupted_metrics != metrics
    assert truth["corruption"] == "C6_denominator_mismatch"
    assert "I6.denominator_mismatch" in truth["expected_violations"]


def test_c6_preserves_population_members():
    records = [
        ManifestRecord(
            dataset_namespace="dataset_a",
            dataset_version="1.0",
            participant_id="sub-01",
            split="train",
        ),
        ManifestRecord(
            dataset_namespace="dataset_a",
            dataset_version="1.0",
            participant_id="sub-02",
            split="train",
        ),
    ]

    metrics = [
        {
            "metric_name": "accuracy",
            "population_key": "train_population",
            "numerator": 1,
            "denominator": 2,
        }
    ]

    populations = {
        "train_population": {
            "person_keys": [
                record.person_key
                for record in records
            ]
        }
    }

    corrupted_metrics, _ = inject_corruption(
        records,
        corruption="C6_denominator_mismatch",
        affected_count=1,
        seed=12345,
        metrics=metrics,
        populations=populations,
    )

    assert (
        corrupted_metrics[0]["denominator"]
        != metrics[0]["denominator"]
    )

    assert populations["train_population"]["person_keys"] == [
        record.person_key
        for record in records
    ]


def test_c6_changes_only_denominator():
    records = [
        ManifestRecord(
            dataset_namespace="dataset_a",
            dataset_version="1.0",
            participant_id="sub-01",
            split="train",
        ),
        ManifestRecord(
            dataset_namespace="dataset_a",
            dataset_version="1.0",
            participant_id="sub-02",
            split="train",
        ),
    ]

    metrics = [
        {
            "metric_name": "accuracy",
            "population_key": "train_population",
            "numerator": 1,
            "denominator": 2,
            "extra_field": "preserve-me",
        }
    ]

    populations = {
        "train_population": {
            "person_keys": [
                record.person_key
                for record in records
            ]
        }
    }

    corrupted_metrics, _ = inject_corruption(
        records,
        corruption="C6_denominator_mismatch",
        affected_count=1,
        seed=20270915,
        metrics=metrics,
        populations=populations,
    )

    corrupted = corrupted_metrics[0]

    assert corrupted["metric_name"] == metrics[0]["metric_name"]
    assert corrupted["population_key"] == metrics[0]["population_key"]
    assert corrupted["numerator"] == metrics[0]["numerator"]
    assert corrupted["extra_field"] == metrics[0]["extra_field"]
    assert corrupted["denominator"] != metrics[0]["denominator"]


def test_c6_does_not_modify_original_metrics():
    records = [
        ManifestRecord(
            dataset_namespace="dataset_a",
            dataset_version="1.0",
            participant_id="sub-01",
            split="train",
        ),
        ManifestRecord(
            dataset_namespace="dataset_a",
            dataset_version="1.0",
            participant_id="sub-02",
            split="train",
        ),
    ]

    metrics = [
        {
            "metric_name": "accuracy",
            "population_key": "train_population",
            "numerator": 1,
            "denominator": 2,
        }
    ]

    populations = {
        "train_population": {
            "person_keys": [
                record.person_key
                for record in records
            ]
        }
    }

    original_metrics = [dict(metric) for metric in metrics]

    inject_corruption(
        records,
        corruption="C6_denominator_mismatch",
        affected_count=1,
        seed=20270915,
        metrics=metrics,
        populations=populations,
    )

    assert metrics == original_metrics


def test_c6_truth_contains_required_metadata():
    records = [
        ManifestRecord(
            dataset_namespace="dataset_a",
            dataset_version="1.0",
            participant_id="sub-01",
            split="train",
        ),
        ManifestRecord(
            dataset_namespace="dataset_a",
            dataset_version="1.0",
            participant_id="sub-02",
            split="train",
        ),
    ]

    metrics = [
        {
            "metric_name": "accuracy",
            "population_key": "train_population",
            "numerator": 1,
            "denominator": 2,
        }
    ]

    populations = {
        "train_population": {
            "person_keys": [
                record.person_key
                for record in records
            ]
        }
    }

    _, truth = inject_corruption(
        records,
        corruption="C6_denominator_mismatch",
        affected_count=1,
        seed=12345,
        metrics=metrics,
        populations=populations,
    )

    assert truth["corruption"] == "C6_denominator_mismatch"
    assert truth["seed"] == 12345
    assert "parent_manifest_sha256" in truth
    assert "operations" in truth
    assert "affected_keys" in truth
    assert "expected_violations" in truth
    assert "I6.denominator_mismatch" in truth["expected_violations"]


def test_c6_is_deterministic_for_same_seed():
    records = [
        ManifestRecord(
            dataset_namespace="dataset_a",
            dataset_version="1.0",
            participant_id="sub-01",
            split="train",
        ),
        ManifestRecord(
            dataset_namespace="dataset_a",
            dataset_version="1.0",
            participant_id="sub-02",
            split="train",
        ),
        ManifestRecord(
            dataset_namespace="dataset_a",
            dataset_version="1.0",
            participant_id="sub-03",
            split="train",
        ),
    ]

    metrics = [
        {
            "metric_name": "accuracy",
            "population_key": "train_population",
            "numerator": 2,
            "denominator": 3,
        }
    ]

    populations = {
        "train_population": {
            "person_keys": [
                record.person_key
                for record in records
            ]
        }
    }

    corrupted_a, truth_a = inject_corruption(
        records,
        corruption="C6_denominator_mismatch",
        affected_count=1,
        seed=20270915,
        metrics=metrics,
        populations=populations,
    )

    corrupted_b, truth_b = inject_corruption(
        records,
        corruption="C6_denominator_mismatch",
        affected_count=1,
        seed=20270915,
        metrics=metrics,
        populations=populations,
    )

    assert corrupted_a == corrupted_b
    assert truth_a == truth_b

def test_c6_triggers_i6_denominator_mismatch():
    records = [
        ManifestRecord(
            dataset_namespace="dataset_a",
            dataset_version="1.0",
            participant_id="sub-01",
            split="train",
        ),
        ManifestRecord(
            dataset_namespace="dataset_a",
            dataset_version="1.0",
            participant_id="sub-02",
            split="train",
        ),
        ManifestRecord(
            dataset_namespace="dataset_a",
            dataset_version="1.0",
            participant_id="sub-03",
            split="train",
        ),
    ]

    metrics = [
        {
            "metric_name": "accuracy",
            "population_key": "train_population",
            "numerator": 2,
            "denominator": 3,
        }
    ]

    populations = {
        "train_population": {
            "person_keys": [
                record.person_key
                for record in records
            ]
        }
    }

    corrupted_metrics, truth = inject_corruption(
        records,
        corruption="C6_denominator_mismatch",
        affected_count=1,
        seed=20270915,
        metrics=metrics,
        populations=populations,
    )

    findings = check_i6_metric_denominator_traceability(
        records,
        metrics=corrupted_metrics,
        populations=populations,
    )

    rule_ids = {
        finding.rule_id
        for finding in findings
    }

    assert "I6.denominator_mismatch" in rule_ids
    assert "I6.denominator_mismatch" in truth["expected_violations"]

def test_c1_affected_count_is_person_count():
    records = build_synthetic_manifest(
        people=16,
        modalities=2,
        sessions=1,
        runs_per_modality=1,
    )

    corrupted, truth = inject_corruption(
        records,
        corruption="C1_namespace_stripping",
        affected_count=4,
        seed=7,
    )

    assert len(truth["affected_keys"]) == 4
    assert len(set(truth["affected_keys"])) == 4

def test_c3_affected_count_is_person_count():
    records = build_synthetic_manifest(
        people=16,
        modalities=2,
        sessions=1,
        runs_per_modality=1,
    )

    corrupted, truth = inject_corruption(
        records,
        corruption="C3_duplicate_propagation",
        affected_count=4,
        seed=7,
    )

    assert len(truth["affected_keys"]) == 4
    assert len(set(truth["affected_keys"])) == 4
    assert len(corrupted) == len(records) + 4

def test_c4_affected_count_is_person_count():
    records = build_synthetic_manifest(
        people=16,
        modalities=2,
        sessions=1,
        runs_per_modality=1,
    )

    corrupted, truth = inject_corruption(
        records,
        corruption="C4_cross_modal_permutation",
        affected_count=4,
        seed=7,
    )

    assert len(truth["affected_keys"]) == 4
    assert len(set(truth["affected_keys"])) == 4

def test_c2_affected_count_is_collision_instance_count():
    records = build_synthetic_manifest(
        people=16,
        modalities=2,
        sessions=1,
        runs_per_modality=1,
    )

    corrupted, truth = inject_corruption(
        records,
        corruption="C2_canonicalization_collision",
        affected_count=4,
        seed=7,
    )

    assert len(truth["affected_keys"]) == 4
    assert len(set(truth["affected_keys"])) == 4
    assert len(truth["operations"]) == 4
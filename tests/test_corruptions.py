from neurofusion_qa.manifest import ManifestRecord
from neurofusion_qa.identity import canonicalize_participant_id
from neurofusion_qa.corruptions import inject_corruption


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
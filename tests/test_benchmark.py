from neurofusion_qa.benchmark import build_synthetic_manifest


def test_synthetic_manifest_record_count():
    records = build_synthetic_manifest(
        people=16,
        modalities=2,
        sessions=1,
        runs_per_modality=1,
    )

    assert len(records) == 16 * 2 * 1 * 1


def test_synthetic_manifest_has_expected_people():
    records = build_synthetic_manifest(
        people=16,
        modalities=2,
        sessions=1,
        runs_per_modality=1,
    )

    person_keys = {record.person_key for record in records}

    assert len(person_keys) == 16


def test_synthetic_manifest_is_deterministic():
    first = build_synthetic_manifest(
        people=16,
        modalities=2,
        sessions=2,
        runs_per_modality=2,
    )

    second = build_synthetic_manifest(
        people=16,
        modalities=2,
        sessions=2,
        runs_per_modality=2,
    )

    assert first == second


def test_synthetic_manifest_keeps_person_records_in_one_split():
    records = build_synthetic_manifest(
        people=16,
        modalities=2,
        sessions=2,
        runs_per_modality=2,
    )

    splits_by_person = {}

    for record in records:
        splits_by_person.setdefault(record.person_key, set()).add(record.split)

    assert all(len(splits) == 1 for splits in splits_by_person.values())


def test_synthetic_manifest_acquisition_keys_are_unique():
    records = build_synthetic_manifest(
        people=16,
        modalities=3,
        sessions=2,
        runs_per_modality=4,
    )

    acquisition_keys = [record.acquisition_key for record in records]

    assert len(acquisition_keys) == len(set(acquisition_keys))


def test_synthetic_manifest_has_deterministic_provenance():
    records = build_synthetic_manifest(
        people=4,
        modalities=2,
        sessions=1,
        runs_per_modality=1,
    )

    assert all(record.source_sha256 is not None for record in records)
    assert all(len(record.source_sha256) == 64 for record in records)

    assert all(record.derivative_sha256 is not None for record in records)
    assert all(len(record.derivative_sha256) == 64 for record in records)

    assert len({record.source_sha256 for record in records}) == len(records)
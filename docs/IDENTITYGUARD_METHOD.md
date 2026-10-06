## Manifest Metadata Conventions

The research protocol requires each generated manifest to record:

- schema version
- tool version
- dataset metadata hash
- row count
- generation time

The current implementation uses the following provisional conventions:

| Field | Current implementation |
|---|---|
| `schema_version` | `1.0` |
| `tool_version` | `0.1.0`, matching the Python package version |
| `dataset_metadata_hash` | SHA-256 of BIDS `dataset_description.json` |
| `row_count` | Number of generated `ManifestRecord` rows |
| `generation_time` | UTC ISO-8601 timestamp |

These exact implementation values are not presented as requirements of the
research handoff where the handoff is silent. They are implementation
conventions selected to make the manifest deterministic, traceable, and
versioned.

If the research protocol is subsequently amended by the project supervisor,
these conventions can be changed without changing the underlying identity
and provenance model.

### Research-paper reporting note

When describing the methodology, distinguish between:

1. protocol requirements defined by the research handoff; and
2. implementation conventions selected where the handoff does not specify
   an exact representation.

This distinction prevents implementation details from being incorrectly
presented as experimentally validated methodological requirements.

## Manifest Builder Acceptance Criteria

The manifest builder is required to produce deterministic, publication-safe
manifest records.

The current implementation verifies:

1. Rebuilding the manifest from unchanged input produces identical normalized
   `ManifestRecord` objects.
2. Source paths are dataset-relative.
3. Source paths use POSIX separators (`/`).
4. Absolute local filesystem paths are not exposed in manifest records.

The research handoff additionally specifies that unchanged-input rebuilds
should produce byte-identical normalized data or an identical canonical hash.
The current record-level implementation verifies equality of the normalized
records. A canonical serialized representation/hash will be added when the
manifest serialization/output layer is implemented.

Row-order invariance is treated as an audit-level property in accordance with
the handoff and will therefore be tested with the audit engine rather than
being incorrectly attributed to the manifest builder.

### Public-release safety

Public manifests must not expose absolute local storage paths. The manifest
therefore stores dataset-relative POSIX paths rather than machine-specific
filesystem locations.

This prevents local directory structure, usernames, drive letters, and other
machine-specific storage information from entering public research artifacts.

## I1 Canonicalization Convention

The research protocol requires IdentityGuard-BIDS to detect cases where
canonicalization collapses distinct raw participant labels, but it does not
prescribe a specific canonicalization algorithm.

The current implementation therefore defines an explicit canonicalization
convention for participant IDs.

The canonicalization procedure is:

1. Apply Unicode NFKC normalization.
2. Apply Unicode case folding.
3. Remove the leading BIDS `sub` prefix when present.
4. Treat `-`, `_`, `.`, and whitespace separators as equivalent.
5. For numeric participant labels, remove leading zeroes by converting the
   numeric label to its canonical integer representation.
6. Reconstruct the canonical participant representation as `sub-<label>`.

Examples:

| Raw participant ID | Canonical representation |
|---|---|
| `sub-01` | `sub-1` |
| `sub-1` | `sub-1` |
| `SUB-01` | `sub-1` |
| `sub_01` | `sub-1` |
| `sub.01` | `sub-1` |
| `sub-A01` | `sub-a01` |

Collision detection is performed within the namespace-qualified dataset
identity `(dataset_namespace, dataset_version)`. Therefore identical raw
labels occurring in different dataset namespaces are not treated as
identity collisions.

The original `participant_id` is never replaced by its canonical form.
Canonicalization is an audit representation only.

A collision is reported when two or more distinct raw participant IDs within
the same dataset namespace and version produce the same canonical
representation.

This canonicalization procedure is an implementation convention rather than
a requirement explicitly prescribed by the research handoff. It is fixed for
the experiments using this implementation so that the corruption and audit
behavior remain reproducible.

## I3 Cross-Modal Pairing Conventions

The research protocol requires cross-modal pairing to remain within the same
namespace-qualified person key unless an authoritative hashed crosswalk is
supplied. It also requires explicit session/task compatibility and prohibits
identity inference from string similarity.

The current implementation makes the following concrete choices where the
handoff does not specify the representation.

### Explicit pair representation

The pairing checker receives an explicit sequence of record pairs:

`[(left_record, right_record), ...]`

IdentityGuard-BIDS does not generate a Cartesian product of records and does
not infer which records should be paired. The upstream pairing operation must
explicitly provide the proposed pairs to the audit engine.

### Person identity

Without an authoritative crosswalk, the left and right records must have
exactly equal namespace-qualified person keys:

`(dataset_namespace, dataset_version, participant_id)`

Identical participant strings in different namespaces are therefore not
considered sufficient evidence of identity.

### Cross-dataset crosswalk

Cross-dataset pairing is permitted only when an explicit
`AuthoritativeCrosswalk` is supplied.

The implementation requires the crosswalk to contain:

- source
- version
- SHA-256 digest
- approval identity
- approval date
- explicit mapping between namespace-qualified person keys

The mapping is treated as authoritative input. IdentityGuard-BIDS never
constructs it using participant-string similarity.

### Session compatibility

The implementation uses the following deterministic rule:

- equal explicit session identifiers: compatible
- both session identifiers absent: compatible
- one absent and one present: incompatible
- two different explicit session identifiers: incompatible

This is a conservative fail-closed interpretation of missing pairing evidence.

### Task compatibility

Task compatibility follows the same rule:

- equal explicit task identifiers: compatible
- both task identifiers absent: compatible
- one absent and one present: incompatible
- two different explicit task identifiers: incompatible

### Modality requirement

A cross-modal pair must contain two explicit and different modality values.
A pair containing the same modality on both sides is rejected.

### Implementation-status note

These representations and compatibility rules are implementation
conventions selected to operationalize the protocol requirements. They are
not claimed to be literal specifications from the frozen research handoff.
They are fixed for reproducibility unless the research protocol is formally
amended.

## Implementation Conventions for Previously Underspecified Components

### I1 — Canonicalization convention

The research protocol requires that canonicalization must not collapse distinct
raw participant labels, while preserving raw identifiers. The exact
canonicalization algorithm was not specified by the handoff.

IdentityGuard-BIDS therefore uses the following explicit implementation
convention for audit purposes:

1. Unicode normalization uses NFKC.
2. Participant labels are case-folded.
3. Leading/trailing whitespace is removed.
4. A leading `sub`/`sub-`/`sub_`/`sub.` prefix is normalized away before
   canonicalization.
5. Hyphens, underscores, periods, and whitespace within the participant
   label are treated as equivalent separators.
6. Numeric identifiers are normalized by removing leading zeroes.
7. The canonical representation is reconstructed as `sub-<canonical_label>`.
8. Collision detection is performed within the namespace-qualified
   `(dataset_namespace, dataset_version)` scope.
9. Raw participant identifiers are never overwritten.

This canonical representation is an audit representation only; it does not
replace the raw participant identifier in the manifest.

This is an implementation convention rather than a requirement explicitly
specified by the research handoff.

### I3 — Cross-modal pairing convention

The protocol specifies that cross-modal pairing must use the same
namespace-qualified person key unless an authoritative crosswalk is supplied,
and that cross-dataset identity must never be inferred from string similarity.

The following concrete implementation convention is used:

1. Pairing input consists of explicit record pairs.
2. Without an authoritative crosswalk, the two records must have identical
   namespace-qualified person keys.
3. Cross-dataset pairing is permitted only when an explicit
   `AuthoritativeCrosswalk` is supplied.
4. The crosswalk contains:
   - source
   - version
   - SHA-256 hash
   - approver
   - approval date
   - explicit mapping between namespace-qualified person keys.
5. Session compatibility requires either equal explicit session identifiers
   or both values being absent.
6. Task compatibility follows the same rule.
7. A valid cross-modal pair requires two explicit and different modality
   values.
8. Participant-string similarity is never used to infer identity.

These choices make the pairing rule deterministic and auditable.

The exact pair-table representation and session/task compatibility semantics
were not fully specified in the handoff; the rules above are therefore
implementation conventions.

### I4 — Derivative key convention

The protocol states that a derivative key extends the acquisition key with
recipe and output identity but does not define the exact tuple.

IdentityGuard-BIDS uses:

`K_derivative = (K_acquisition, derivative_recipe_sha256, derivative_path)`

where `K_acquisition` is the namespace-qualified acquisition key already
defined by the protocol.

The derivative lineage audit then:

1. Requires derivative records to have both a recipe hash and derivative path.
2. Treats the acquisition key as the derivative's parent.
3. Reports a missing parent when the required identity fields needed to form
   the parent acquisition identity are absent.
4. Reports conflicting derivative hashes under the same derivative key.
5. Reports identical derivative hashes appearing under different acquisition
   keys.
6. Reports repeated source paths and exact repeated rows.

This tuple and the associated missing-lineage handling are implementation
conventions introduced because the handoff did not specify the exact
derivative-key tuple.

### I5 — Split-independence convention

The protocol requires that one person key belongs to exactly one outer split,
that source/derivative hashes must not cross splits, and that analysis grouping
variables be represented in the split audit.

IdentityGuard-BIDS implements these checks as follows:

1. A missing split assignment is reported.
2. A person key appearing in multiple split assignments is reported as
   subject-level split leakage.
3. A retrieved source SHA-256 appearing across splits is reported.
4. A retrieved derivative SHA-256 appearing across splits is reported.
5. `not_retrieved` hash markers are not treated as evidence of leakage.
6. Optional analysis grouping variables are supplied explicitly as
   group-to-person mappings and are checked for membership across splits.

For C5 corruption generation, the implementation selects a participant with
at least two records assigned to the same split and moves exactly one record
to another existing split. This guarantees that the corruption produces
subject-level split leakage while preserving the participant identity.

The grouping-variable representation and C5 record-selection mechanism are
implementation conventions because the handoff did not prescribe their exact
data structures.

### I6 — Metric denominator convention

The protocol requires every metric to identify its population and exact count,
with aggregation from rows/trials/runs to subjects being explicit and
replayable.

IdentityGuard-BIDS represents a metric using a `population_key` and a declared
denominator. The associated population contains explicit person keys.

The implementation checks:

1. Every metric has a population key.
2. The referenced population exists.
3. The declared denominator is positive.
4. The numerator is present and lies between zero and the denominator.
5. Every population member is represented in the audited records.
6. The declared denominator equals the number of unique person keys in the
   declared population.

For C6, the corruption generator selects a traceable metric and changes only
its declared denominator. Population membership, numerator, metric identity,
and population key remain unchanged. The resulting mismatch is therefore
detected by `I6.denominator_mismatch`.

The exact metric/population table representation and denominator calculation
were implementation conventions introduced because the handoff did not
specify a concrete analysis-output schema.

## Corruption Generation Conventions

The protocol defines the six corruption mechanisms and their expected detector
families. The following implementation choices make those mechanisms
deterministic and reproducible without changing their intended meaning.

### C1 — Namespace stripping

C1 removes the dataset namespace from selected manifest records rather than
replacing it with an alternative namespace.

This choice directly produces the protocol-defined missing-namespace condition
and therefore exercises `I1.namespace_completeness`. The original manifest is
not modified in place.

This is an implementation convention because the protocol permits either
removal or replacement.

### C2 — Canonicalization collision

C2 creates collision instances by selecting distinct records within the same
dataset namespace/version and changing a selected participant label to a
distinct raw representation that collapses to the same canonical identifier
under the IdentityGuard canonicalization convention.

Raw labels remain represented in the corrupted manifest so that the collision
can be localized.

For `affected_count = k`, the generator creates `k` collision instances, with
two records participating in each instance.

### C3 — Duplicate propagation

C3 duplicates selected manifest/acquisition rows exactly.

For `affected_count = k`, exactly `k` existing records are duplicated. The
duplicate contains the same identity, source, derivative, and analysis
attributes as the selected original.

The generator does not fabricate downstream metric results. The expected I6
violation records the downstream consequence that can occur when duplicated
analysis units are incorporated into a metric population.

### C4 — Cross-modal permutation

C4 operates directly on the manifest representation.

A modality-bearing record is reassigned to another participant within the same
dataset namespace/version by changing its participant identifier while
preserving its underlying acquisition/source evidence.

The operation is recorded in hidden corruption truth, including the original
and new person keys.

This produces an explicit person-pairing inconsistency for I3 without requiring
the corruption generator to infer biological identity.

### C5 — Subject split leakage

C5 selects a participant having at least two records in the same split and
moves exactly one of those records to another existing split.

This preserves the participant identity while ensuring that the participant
appears in multiple outer splits.

The resulting primary detector is `I5.person_split_leakage`.

### C6 — Denominator mismatch

C6 operates on the analysis metric representation rather than modifying
participant identity.

A traceable metric is selected and only its declared denominator is changed.
The associated population membership and numerator remain unchanged.

The resulting mismatch between the declared denominator and the number of
unique person keys in the declared population is detected as
`I6.denominator_mismatch`.

All C1–C6 generators preserve the clean input and emit hidden truth containing
the parent manifest hash, seed, operations, affected keys, and expected
violations.

## Implementation Status at Pre-CLI Checkpoint

All invariant families I1–I6 and corruption generators C1–C6 have been
implemented and covered by automated tests.

Current verification checkpoint:

- `tests/test_corruptions.py`: 37 passed
- Full test suite: 104 passed

The C6 generator has additionally been verified end-to-end against the
`I6.denominator_mismatch` detector.

No benchmark summary results are represented by these tests; benchmark
evaluation remains a separate stage.

## Synthetic Benchmark Implementation Conventions

The research protocol specifies the synthetic benchmark grid, corruption
types, severity levels, and repetition requirements, but does not prescribe
the concrete serialization of synthetic manifest fields. The following
conventions are therefore implementation choices for the IdentityGuard-BIDS
benchmark and are not additional protocol requirements.

### Synthetic Dataset Identity

- `dataset_namespace`: `synthetic:identityguard`
- `dataset_version`: `1.0`
- `participant_id`: `sub-00001`, `sub-00002`, ...
- Synthetic identifiers are generated solely for benchmark purposes and are
  not derived from private or protected datasets.

### Synthetic Acquisition Representation

Synthetic records use the existing `ManifestRecord` fields:

- `session_id`: `ses-01`, `ses-02`, ...
- `modality`: `mod-01`, `mod-02`, ...
- `task`: `task-synthetic`
- `acquisition`: `acq-01`
- `run`: `01`, `02`, ...
- `analysis_role`: `primary`

### Synthetic Provenance

Synthetic source and derivative paths and hashes are generated
deterministically from the synthetic record identity. They do not represent
real imaging files.

### Synthetic Split Assignment

The protocol requires subject-level split independence but does not prescribe
specific split proportions. For benchmark generation, participants are
deterministically assigned to the existing `train`, `validation`, and `test`
split labels, and all records belonging to a participant inherit that
participant's split.

This split assignment is an implementation convention rather than a
protocol requirement.

### Benchmark Truth Separation

For each corruption experiment, the corrupted manifest is supplied to the
detector while corruption truth is retained separately by the benchmark
evaluator. The detector must not receive the hidden corruption truth.

### Benchmark Localization and Failure-Type Evaluation

The corruption truth records affected keys from the clean parent manifest.
Some corruptions intentionally modify identity-bearing fields, so the affected
key in hidden truth may differ from the key observed by the detector after
corruption.

For benchmark localization, the corruption operation's row-level evidence is
used to establish correspondence between the clean affected record and the
detector's observed record when an identity-bearing field has been modified.
Literal equality between the clean affected key and the detector-observed key
is therefore not required for such corruptions.

For corruptions whose identity-bearing fields are unchanged, detector
localization is evaluated by direct affected-key correspondence.

Failure-type accuracy is evaluated against the corruption generator's
`expected_violations`. Secondary findings produced as downstream consequences
of a corruption are not treated as additional expected failure types.

A corruption is classified as correctly identified only when all of its
declared expected violation rules are detected by the benchmark detector.

These localization and failure-type evaluation rules are implementation
conventions for the synthetic benchmark. They are not additional requirements
of the research protocol.
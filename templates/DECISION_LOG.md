# Decision Log

Copy this block for every scientific, data, model, authorship, or submission decision.

## D-001 - Benchmark localization evaluator correction

- **Date/time:** 2026-10-12; exact decision time not recorded.
- **Requested/decided by:** Student implementation decision; PI approval pending.
- **Decision:** Prevent localization true positives from being credited to unrelated affected keys when detector evidence matches only one corruption operation. For C4, award localization credit only when an I3 person-pairing finding includes an affected person in its observed pair.
- **Options considered:** Retain broad operation-level credit; attribute evidence to individual operations; use the C4 source identity from hidden truth regardless of detector findings.
- **Evidence available at decision time:** A regression test demonstrated that evidence for one C1 operation could incorrectly credit multiple affected keys. A C4 regression test demonstrated that an empty finding set could still receive localization credit from hidden truth. The truth generator records operation-specific fields, including row indices and affected-key fields, with schemas that vary by corruption type.
- **Reason:** Localization metrics must reflect detector evidence rather than crediting unrelated affected keys or awarding credit when no detector finding exists.
- **Made before or after seeing affected results:** After the earlier six-job smoke run using the previous evaluator; before the six `smoke_evalfix` jobs. The correction was therefore made before those six updated smoke results, but not before all prior smoke results.
- **Effect on protocol/interpretation:** Corrects evaluation of localization rather than changing the corruption definitions or detector rules. For C4, the current metric indicates that an affected person appears in a detected mismatched pair; it does not establish exact attribution to the original source person. Results from different evaluator revisions must be distinguished.
- **Files/configs changed:** `src/neurofusion_qa/benchmark.py`, `tests/test_benchmark.py`; this decision-log entry documents the correction.
- **Owner and due date:** Student maintainer; before the full benchmark grid.
- **PI approval:** Pending.

## D-002 - C0 clean-control implementation and evidence convention

- **Date/time:** 2026-10-12; exact decision time not recorded.
- **Requested/decided by:** Student implementation decision; PI approval pending.
- **Decision:** Implement `C0_clean` as a no-op corruption. Its truth record contains empty `operations`, `expected_violations`, and `affected_keys` lists. The C0 benchmark executor supplies synthetic cross-modal join checks, cross-modal pairing evidence, and metric/population evidence using the existing benchmark evidence builders.
- **Options considered:** Leave C0 unsupported by the benchmark executor; implement C0 as a no-op with default audit inputs only; implement C0 as a no-op with supplemental synthetic audit evidence.
- **Evidence available at decision time:** The benchmark executor supported C1–C6 but did not support C0. A default synthetic clean-manifest audit produced zero findings. The existing benchmark module provided evidence builders for cross-modal pairs, join checks, and metric/population evidence.
- **Reason:** Enable a reproducible clean-control benchmark job and exercise the relevant audit paths without injecting a corruption or changing the clean manifest.
- **Made before or after seeing affected results:** The implementation convention was selected before the standalone C0 smoke result recorded below. The default clean-manifest audit and existing C1–C6 smoke results had already been observed.
- **Effect on protocol/interpretation:** Establishes a clean-control execution path with supplemental evidence. It does not change C1–C6 corruption definitions. The evidence-building convention is an implementation choice, not an explicitly specified protocol requirement. One successful synthetic smoke job does not establish a general zero-false-alarm rate.
- **Validation evidence:** Experiment `smoke_C0_clean_454ccad`; 16 people, 2 modalities, 1 session, 1 run per modality, seed 7. Zero audit findings and no detection or localization credit. All ten artifact hashes independently verified.
- **Output directory:** `C:\Users\DELL\Downloads\IdentityGuard-smoke-C0-454ccad-20261012\smoke_C0_clean_454ccad`
- **Code commit:** `454ccad0aab06838e8b17dfa1595a787efde808d`
- **Source-tree SHA-256:** `7116dfc1b3380682eca0a99395be2d1a068b7a2986a1e744e5c054602df542a3`
- **Files/configs changed:** `src/neurofusion_qa/corruptions.py`, `src/neurofusion_qa/benchmark.py`, `tests/test_benchmark.py`.
- **Owner and due date:** Student maintainer; before the full benchmark grid.
- **PI approval:** Pending.

### D-003 - I1 canonicalization convention

- **Decision date:** Exact date of initial decision not established; implementation documented by 2026-09-22.
- **Decision status:** Student implementation convention; PI approval pending.
- **Protocol basis:** The protocol requires detection of canonicalization collisions and preservation of raw identifiers but does not prescribe the exact canonicalization algorithm.
- **Convention implemented:** Unicode NFKC normalization, case folding, trimming, normalization of leading `sub` prefixes, equivalence of hyphen/underscore/period/whitespace separators, removal of leading zeroes in numeric identifiers, and collision detection within the dataset namespace/version scope. Raw participant identifiers remain unchanged.
- **Rationale:** Make canonicalization deterministic and reproducible while retaining the original identifiers for audit and localization.
- **Alternatives considered at the time:** Not established by the available historical record. Do not retrospectively claim a formal comparison.
- **Evidence:** `docs/IDENTITYGUARD_METHOD.md`; commit `87a4374` (2026-09-22). The later consolidated methodology is recorded in `8ba7797` (2026-09-30).
- **Scope:** I1 canonicalization and the corresponding synthetic collision behavior.
- **Approval:** PI approval pending.

### D-004 - I3 explicit cross-modal pairing convention

- **Decision date:** Exact date of initial decision not established; implementation documented by 2026-09-22.
- **Decision status:** Student implementation convention; PI approval pending.
- **Protocol basis:** The protocol requires namespace-qualified identity matching unless an authoritative crosswalk is provided, explicit session/task compatibility, and no identity inference from participant-string similarity. The exact pair representation and compatibility semantics were not fully specified.
- **Convention implemented:** Pairing operates on explicit record pairs. Without an authoritative crosswalk, namespace-qualified person keys must match. Cross-dataset pairing requires an explicit crosswalk with provenance, version, hash, approval identity/date, and mappings. Session/task values are compatible when both are absent or equal; one absent and one present, or two different explicit values, are incompatible. Modalities must be explicit and different.
- **Rationale:** Make pairing checks deterministic and auditable without inferring identity from string similarity.
- **Alternatives considered at the time:** Not established by the available historical record.
- **Evidence:** `docs/IDENTITYGUARD_METHOD.md`; commit `0ee9a68` (2026-09-22).
- **Scope:** I3 cross-modal pairing validation and associated evidence.
- **Approval:** PI approval pending.

### D-005 - I4 derivative identity and lineage convention

- **Decision date:** Exact date of initial decision not established; the convention appears in the consolidated methodology committed on 2026-09-30.
- **Decision status:** Student implementation convention; PI approval pending.
- **Protocol basis:** The protocol requires derivative identity and lineage checks but does not specify the exact derivative-key tuple or all missing-lineage handling.
- **Convention implemented:** `K_derivative = (K_acquisition, derivative_recipe_sha256, derivative_path)`. The audit checks required recipe/path fields, parent acquisition identity, conflicting derivative hashes under the same key, identical derivative hashes across different acquisition keys, repeated source paths, and exact repeated rows.
- **Rationale:** Provide an explicit derivative identity representation and reproducible lineage checks.
- **Alternatives considered at the time:** Not established by the available historical record.
- **Evidence:** `docs/IDENTITYGUARD_METHOD.md`; consolidated implementation conventions in commit `8ba7797` (2026-09-30).
- **Scope:** I4 derivative identity and lineage audit.
- **Approval:** PI approval pending.

### D-006 - I5 split-independence convention

- **Decision date:** Exact date of initial decision not established; the convention appears in the consolidated methodology committed on 2026-09-30.
- **Decision status:** Student implementation convention; PI approval pending.
- **Protocol basis:** The protocol requires person-level split independence, source/derivative hash independence across splits, and explicit analysis-group checks, but does not prescribe every input representation or corruption-selection detail.
- **Convention implemented:** Report missing split assignments, person keys across splits, retrieved source/derivative hashes across splits, and explicit analysis-group membership across splits. Treat `not_retrieved` markers as non-evidence. For C5, select a participant with at least two records in one split and move exactly one record to another existing split.
- **Rationale:** Operationalize split-independence checks while preserving person identity during the synthetic leakage corruption.
- **Alternatives considered at the time:** Not established by the available historical record.
- **Evidence:** `docs/IDENTITYGUARD_METHOD.md`, consolidated implementation conventions in commit `8ba7797` (2026-09-30).
- **Scope:** I5 split audit and C5 generation.
- **Approval:** PI approval pending.

### D-007 - I6 metric-denominator convention

- **Decision date:** Exact date of initial decision not established; the convention appears in the consolidated methodology committed on 2026-09-30.
- **Decision status:** Student implementation convention; PI approval pending.
- **Protocol basis:** The protocol requires traceable metric populations and explicit denominators but does not define a concrete serialized analysis-output schema.
- **Convention implemented:** Metrics reference a `population_key` and declared denominator; populations contain explicit person keys. Checks cover population-key presence and existence, positive denominator, numerator bounds, population-member representation in audited records, and equality between the declared denominator and the number of unique person keys. C6 changes only the declared denominator.
- **Rationale:** Make denominator validation deterministic and allow the C6 corruption to isolate the denominator mismatch.
- **Alternatives considered at the time:** Not established by the available historical record.
- **Evidence:** `docs/IDENTITYGUARD_METHOD.md`, consolidated implementation conventions in commit `8ba7797` (2026-09-30).
- **Scope:** I6 metric traceability and C6 generation.
- **Approval:** PI approval pending.

### D-008 - Synthetic benchmark representation and corruption conventions

- **Decision date:** Benchmark implementation documented across 2026-10-06 to 2026-10-09; exact dates of individual convention decisions are not established by the available history.
- **Decision status:** Student implementation conventions; PI approval pending.
- **Protocol basis:** The protocol specifies the benchmark grid, corruption families, severity levels, and repetitions, but does not prescribe every synthetic manifest field, serialized evidence representation, or corruption-generation detail.
- **Convention implemented:** Use deterministic synthetic identifiers and metadata, preserve a clean parent manifest, generate seeded corruption truth separately from detector-visible inputs, and implement C1–C6 as documented in `docs/IDENTITYGUARD_METHOD.md`. The specific conventions include namespace removal for C1, paired collision instances for C2, exact row duplication for C3, manifest-level cross-modal permutation for C4, one-record split movement for C5, and denominator-only modification for C6.
- **Rationale:** Make benchmark jobs reproducible, auditable, and consistent with the intended corruption definitions.
- **Alternatives considered at the time:** Not established by the available historical record.
- **Evidence:** `docs/IDENTITYGUARD_METHOD.md`; commits `763b324` (C2, 2026-10-06), `82df22e` (C3, 2026-10-07), `81ecb03` (C4, 2026-10-07), `f85f23f` (C1–C6 implementation checkpoint, 2026-10-07), and `5bf7ef7` (reproducible executor, 2026-10-09).
- **Scope:** High-level summary of synthetic benchmark representation and C1–C6 generation conventions. This entry does not replace D-002 or the protocol's specified benchmark grid, and it does not authorize the full experiment run.
- **Approval:** PI approval pending.

### D-009 - Baseline prediction and scoring convention

- **Decision date:** 2026-10-13.
- **Decision status:** Student implementation convention; PI approval pending.
- **Protocol basis:** The protocol defines three comparison baselines: a naive inner join on raw `participant_id` without validation, an exact-full-row duplicate check, and a dataset-level BIDS-valid metadata assumption without cross-dataset/join/split provenance checks. The protocol requires instance-level detection sensitivity and clean false-alarm rate, with explicit numerators and denominators.
- **Convention selected:** Keep baseline predictions separate from hidden-truth evaluation. `baselines.json` records observable baseline outputs; a separate `baseline_evaluation.json` records truth-based scores. The naive join reports join statistics but does not alert, so those statistics alone receive no detection credit. An exact-full-row duplicate alert is mapped to `I4.repeated_row` for primary-violation scoring. The BIDS-validation baseline is `not_run` until an actual validator result is supplied. Row-only baselines are `not_applicable` for C6.
- **Rationale:** Prevent evaluation from leaking hidden truth into baseline predictions, avoid crediting descriptive statistics as alerts, and keep unavailable or inapplicable baselines out of scored denominators.
- **Alternatives considered:** Treat changed join statistics as an alert; score an unavailable BIDS-validation result as a negative prediction; combine prediction and evaluation in one artifact.
- **Evidence available at decision time:** The benchmark evaluator receives hidden truth separately from detector findings. The current baseline artifact records duplicate-check and naive-join outputs, while BIDS validation is marked `not_run`. The protocol specifies the baseline definitions and instance-level endpoints.
- **Made before or after seeing affected results:** After observing the six-job baseline integration smoke run; before implementing this scoring convention and before full-grid evaluation.
- **Effect on protocol/interpretation:** This is an explicit scoring convention, not a change to the protocol's corruption definitions. Duplicate-check credit is limited to the declared `I4.repeated_row` mapping. Naive-join statistics remain descriptive unless a separate alert rule is prospectively defined. `not_run` and `not_applicable` results are excluded from scored denominators. Full-grid results remain gated on required approval.
- **Files/configs changed:** `templates/DECISION_LOG.md`; planned evaluator and tests in `src/neurofusion_qa/benchmark.py` and `tests/`.
- **Owner and due date:** Student maintainer; before the full benchmark grid.
- **PI approval:** Pending.

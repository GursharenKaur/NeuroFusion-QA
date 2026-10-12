# Decision Log

Copy this block for every scientific, data, model, authorship, or submission decision.

## D-001 — Benchmark localization evaluator correction

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

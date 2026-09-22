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
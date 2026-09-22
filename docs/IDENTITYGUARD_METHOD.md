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
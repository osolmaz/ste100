# Development guide

- Use Python 3.12 and `uv`.
- Keep runtime analysis deterministic and offline. Do not add custom learned detectors, rewriters, training pipelines, or model-release machinery. A pinned, optional spaCy pipeline is permitted for deterministic linguistic checks.
- Do not claim official ASD-STE100 compliance.
- Ship a practical bundled dictionary. Target the published counts; a difference of up to five entries in either list is acceptable without further count investigation.
- A larger difference can ship only when every extra row remains directly traceable to the source table, the pack has no duplicate status/headword/part-of-speech keys, and the manifest documents the difference. Never delete a valid source row only to force count agreement.
- Every bundled dictionary row must have a valid headword and status, pass schema and duplicate/conflict checks, and remain traceable to the source extraction. Do not load malformed or unresolved draft rows in production.
- Preserve half-open UTF-8 byte offsets and protected content.
- Add positive, negative, exception, boundary, Unicode, and protected-content tests for each implemented checker, with many realistic examples rather than one token fixture.
- Add sanitized or synthetic regression examples derived from the private response-style dataset, but never commit verbatim private conversation text or identifying provenance.
- Give every spaCy-backed checker sanity tests over manually verified sentences, including cases where the linguistic analysis is expected to abstain.
- Regenerate schemas with `uv run python scripts/generate-schemas.py`.
- Run the checks in `.github/workflows/ci.yml` plus the private aggregate regression before committing.
- Do not add private conversations, generated datasets, checkpoints, or model artifacts.

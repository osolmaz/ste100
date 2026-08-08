# Development guide

- Use Python 3.12 and `uv`.
- Keep runtime analysis deterministic and offline. Do not add custom learned detectors, rewriters, training pipelines, or model-release machinery. A pinned, optional spaCy pipeline is permitted for deterministic linguistic checks.
- Do not claim official ASD-STE100 compliance. `passed` means only that implemented checks found no issue.
- Analysis output contains only source-backed findings. Do not add human-review, coverage, applicability, confidence, review-state, or release-gate results.
- Unsupported or ambiguous checks emit nothing. Document the boundary instead of inventing a result.
- Emit one finding per source span and list all applicable official rule IDs on that finding.
- Ship a practical bundled dictionary. Treat it as an internal extraction, not an official machine-readable ASD dictionary.
- Do not claim that extracted part-of-speech rows equal the word totals printed in Issue 9. Keep every shipped row traceable to the source table and reject duplicate status/headword/part-of-speech keys.
- Every bundled dictionary row must have a valid headword and status, pass schema and duplicate/conflict checks, and remain traceable to the source extraction. Do not load malformed or unresolved draft rows in production.
- Preserve half-open UTF-8 byte offsets and protected content.
- Add positive, negative, exception, boundary, Unicode, and protected-content tests for each implemented checker, with many realistic examples rather than one token fixture.
- Add sanitized or synthetic regression examples derived from the private response-style dataset, but never commit verbatim private conversation text or identifying provenance.
- Give every spaCy-backed checker sanity tests over manually verified sentences. A spaCy check can emit a finding only when the tested parse establishes the condition in its message.
- Regenerate schemas with `uv run python scripts/generate-schemas.py`.
- Run the checks in `.github/workflows/ci.yml` plus the private aggregate regression before committing.
- Do not add private conversations, generated datasets, checkpoints, or model artifacts.

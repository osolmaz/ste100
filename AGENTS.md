# Development guide

- Use Python 3.12 and `uv`.
- Keep runtime analysis deterministic and offline. Do not add learned detectors, rewriters, training pipelines, or model-release machinery.
- Do not claim official ASD-STE100 compliance.
- Ship a practical bundled dictionary. Target the published counts, but a difference of up to five entries in either the approved or unapproved list is acceptable.
- Do not block runtime use solely because a valid dictionary differs from the published totals within that tolerance.
- Every bundled dictionary row must have a valid headword and status, pass schema and duplicate/conflict checks, and remain traceable to the source extraction. Do not load malformed or unresolved draft rows in production.
- Preserve half-open UTF-8 byte offsets and protected content.
- Regenerate schemas with `uv run python scripts/generate-schemas.py`.
- Run the checks listed in `README.md` before committing.
- Do not add private conversations, generated datasets, checkpoints, or model artifacts.

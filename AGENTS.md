# Development guide

- Use Python 3.12 and `uv`.
- Keep runtime analysis deterministic and offline.
- Do not claim official ASD-STE100 compliance.
- Do not load draft standard records in production.
- Preserve half-open UTF-8 byte offsets and protected content.
- Keep deterministic findings separate from learned, report-only findings.
- Keep detector and rewriter artifacts and releases independent.
- Regenerate schemas with `uv run python scripts/generate-schemas.py`.
- Run the checks listed in `README.md` before committing.
- Do not add private conversations, generated datasets, checkpoints, or model artifacts.

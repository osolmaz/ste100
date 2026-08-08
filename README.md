# ste100

`ste100` is an offline, auditable foundation for checking English against ASD-STE100 Issue 9 and preparing controlled-language rewrite candidates.

It does not certify official ASD-STE100 compliance. Every analysis reports coverage for all 61 numbered rules and general recommendations. Rules that the software cannot check conclusively remain `not_checked` or `human_review`.

## Current capabilities

- Lossless document parsing with half-open UTF-8 byte offsets
- Deterministic checks for semicolons, contractions, paragraph length, and mechanical sentence counts, with Rule 8.6 grouping ambiguity sent to review
- Reviewed standard-pack validation with digests, expected counts, references, and path-containment checks
- Project terminology validation and longest-match term handling
- Protected spans for terms, numbers, units, identifiers, URLs, code, and caller-supplied ranges
- Separate detector and rewriter interfaces, manifests, release evidence, and tests
- Dataset provenance, synthetic-parent, protected-content, complete-group split, model-family holdout, and time-holdout checks
- Optional spaCy weak-label bootstrapping that is never runtime authority
- JSON Schemas for all portable contracts

The repository includes a deterministic draft extraction of the Issue 9 rules and dictionary rows. It is not a runtime standard pack. The draft has all 53 numbered rules and 8 general recommendations, but its dictionary candidates do not reconcile with the published counts. The audit records 876 approved and 1,318 unapproved candidates, compared with the published 875 and 1,274 words. Human row review is required before a reviewed pack can be released.

No learned model is bundled. The detector and rewriter contracts are ready for separately reviewed model releases.

## Install

`ste100` requires Python 3.12 or later.

```sh
uv tool install .
```

For development:

```sh
uv sync --dev
```

## Analyze text

```sh
ste100 analyze manual.txt
```

Use JSON output for integrations:

```sh
ste100 analyze manual.txt --format json
```

Analysis without `--standard-pack` runs the reviewed-independent structural checks. Vocabulary checks require a complete reviewed pack:

```sh
ste100 analyze manual.txt \
  --standard-pack /path/to/issue-9-pack \
  --project-dictionary project-terms.json \
  --format json
```

The exit code is `1` when a conclusive deterministic violation is present and `2` when input or configuration is invalid.

## Validate data

Validate a reviewed standard pack:

```sh
ste100 validate-standard /path/to/issue-9-pack
```

Validate project terminology or model data:

```sh
ste100 validate-project-dictionary project-terms.json
ste100 validate-dataset records.jsonl
```

Explain one rule and its current automatic coverage. Without a reviewed pack, the command omits the standard requirement text:

```sh
ste100 explain 8.1
```

Create review-required extraction drafts from the checked-in exact text:

```sh
ste100 extract-standard docs/ASD-STE100_ISSUE9.txt build/issue-9-draft
```

See [`schemas/`](schemas/) for the JSON contracts and [`docs/STE100_SYSTEM.md`](docs/STE100_SYSTEM.md) for the system boundaries.

## Development checks

```sh
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest --cov --cov-report=term-missing
uv run pip-audit
uv run python scripts/check-mutation.py
npx --yes simpledoc@latest check README.md docs/*.md
uvx slophammer-py@0.4.0 dry .
uvx slophammer-py@0.4.0 check . --execute
```

The private response-style corpus is not part of this repository. A local regression script can exercise the parser, coverage, and protected-content round trip without printing conversation text:

```sh
uv run python scripts/check-response-style-private.py /path/to/response-style-private
```

## Design documents

- [Detection and rewriting specification](docs/STE100_SYSTEM.md)
- [Implementation plan](docs/2026-08-07-ste100-system-plan.md)
- [Detection and rewriting research](docs/2026-08-07-detection-and-rewrite-inspirations.md)

## Standard and license

The source specification is [ASD-STE100 Issue 9](https://www.asd-ste100.org/assets/files/ASD-STE100_ISSUE9.pdf), published by ASD. The searchable text copy is [`docs/ASD-STE100_ISSUE9.txt`](docs/ASD-STE100_ISSUE9.txt).

The MIT license covers this repository's original code and documentation. ASD source material remains under the terms in [`NOTICE`](NOTICE).

[MIT](LICENSE)

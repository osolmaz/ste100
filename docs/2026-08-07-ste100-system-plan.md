---
title: Build the deterministic STE100 checker
author: Onur Solmaz <2453968+osolmaz@users.noreply.github.com>
date: 2026-08-07
---

# Build the deterministic STE100 checker

This plan produces a deterministic offline checker for ASD-STE100 Issue 9. It does not train, load, or release a custom detector or rewriter. It never claims official compliance.

The checker reports `passed`, `failed`, `human_review`, or `not_applicable` for all 53 numbered rules and eight general recommendations. A result is conclusive only when the implemented check covers the applicable clause. Contextual requirements remain visible as human-review work.

## Standard pack

Bundle a practical Issue 9 pack with the package. It contains:

- `standard.json`
- `rules.json`
- `dictionary.json`
- `examples.json`
- `conformance.json`

Target the published totals of 875 approved and 1,274 unapproved words. A difference of up to five entries in either list is acceptable without further count investigation. A larger difference can ship only when each extra row is valid and directly traceable to the exact source table, duplicate keys are absent, and the manifest records the published baseline, extracted counts, and reconciliation. Never delete a valid row only to force count agreement.

Each dictionary row must have a normalized headword, status, part of speech, permitted forms or alternatives where available, source page, source digest, and review state. Split words and wrapped table cells must be repaired. Duplicate and conflicting entries are errors.

Store the exact requirement text and source page for all 61 requirements. Include reviewed examples for deterministic clauses. Generate all runtime files from one structured source and remove parallel handwritten copies.

`ste100 analyze FILE` uses the bundled pack by default. Callers can select another validated local pack explicitly.

## Coverage audit

Review every requirement and assign one scope:

- `full`: the complete requirement is mechanically decidable
- `partial`: a documented clause is mechanically decidable
- `none`: the requirement needs human judgment

Each full or partial record names its checker and states exactly what it proves. Unsupported requirements use human review.

## Deterministic checks

Implement every conclusive mechanical clause found in the audit. Expected families include:

- approved and unapproved vocabulary
- permitted forms and configured project terminology
- contractions and omitted-word patterns that can be recognized conclusively
- American spelling mappings that are explicitly enumerated
- mechanical noun and verb form restrictions
- sentence and paragraph limits
- procedure, warning, caution, note, and vertical-list structure
- semicolons and mechanically invalid punctuation patterns
- parentheses, colons, hyphens, and Issue 9 word-count rules
- consistent configured terminology

A pinned optional spaCy pipeline can support part-of-speech and morphology checks. The deterministic rule uses spaCy output as evidence and retains its own decision logic. Ambiguous analysis must abstain and request human review. The default runtime remains useful without spaCy.

## Tests and examples

Each implemented checker needs:

- positive examples
- negative examples
- permitted exceptions
- exact boundary cases
- malformed input
- Unicode and UTF-8 offset checks
- protected terms, numbers, units, identifiers, URLs, and code
- applicable examples from Issue 9
- several realistic prose examples

Add sanitized or synthetic examples derived from patterns observed in the private response-style dataset. Do not copy private conversation text, session identifiers, file paths, timestamps, models, or provenance into this repository.

Every spaCy-backed checker needs sanity tests over manually verified sentences. Include clear positive and negative cases, ambiguous cases that must abstain, and behavior when spaCy or its pinned language pipeline is unavailable.

Run the local private regression script before release. It may report aggregate counts but must not print private prose.

## Remove unused scope

Delete custom detector and rewriter interfaces, training-dataset contracts, model manifests, model-release gates, rewrite sentinels used only for generation, and learned-system documentation. Remove optional code that has no deterministic runtime use. Do not retain compatibility aliases or placeholder model APIs.

Protected-content recognition remains because deterministic findings and future caller operations must preserve exact values and offsets.

## CLI and library

The supported commands are:

```text
ste100 analyze FILE
ste100 explain RULE
ste100 validate-standard PATH
ste100 validate-project-dictionary FILE
ste100 extract-standard SOURCE OUTPUT
```

JSON output is stable and includes the standard digest, findings, per-rule coverage, byte ranges, excerpts, checker IDs, and reasons for human review. Invalid configuration returns exit code 2. Conclusive violations return exit code 1.

## Release evidence

Before release:

- validate the bundled pack and its digests
- test every dictionary row through lookup and normalization
- test every deterministic standard example
- run Ruff, formatting, strict mypy, pytest with branch coverage, pip-audit, mutation testing, Slophammer, and SimpleDoc
- build and inspect the wheel and source distribution
- install the wheel in a clean environment and run offline CLI smoke tests
- run Pi Reviewer until no P0 or P1 findings remain
- pass CI

The release report records the package version, code revision, source digest, bundled-pack digest, dictionary counts, coverage counts, test counts, and known human-review boundaries.

## Completion criteria

The deterministic release is complete when:

- the bundled dictionary is valid and practical
- all 61 requirements have reviewed coverage scopes
- every full and partial checker has broad tests
- analysis works without an external pack
- no custom learned-system surface remains
- unsupported clauses are clearly assigned to human review
- all quality and release checks pass
- the package makes no official compliance claim

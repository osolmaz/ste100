---
title: Remove invented checker results
author: Onur Solmaz <2453968+osolmaz@users.noreply.github.com>
date: 2026-08-08
---

# Remove invented checker results

The checker must stay useful without presenting internal guesses as ASD-STE100 concepts. It must remove invented review results, rule coverage scores, review-state labels, and claims that an extracted pack or synthetic test proves compliance.

## Result contract

An analysis result has two parts:

- `passed`: `true` when the implemented checks found no issue, otherwise `false`
- `findings`: source-backed issues found by implemented checks

Each finding contains the applicable official rule IDs, message, UTF-8 byte range, and source excerpt. It does not contain a severity, checker ID, review state, or coverage state.

`passed` means only that the implemented checks found no issue. It never means that the document complies with all of ASD-STE100.

One source span gets one finding. When the same issue refers to more than one rule, the finding lists all of those rule IDs.

## Check policy

A check can emit a finding only when its evidence establishes the condition named in the message.

- A word or phrase listed as unapproved emits one finding with its alternatives and applicable rule IDs.
- A word absent from both the bundled dictionary and the supplied project dictionary emits one factual finding. The message does not guess whether it could become project terminology.
- A word with both approved and unapproved entries emits one factual finding unless linguistic evidence selects an approved entry.
- Exact punctuation, spelling, and list checks remain. Sentence length, paragraph length, and protected content checks also remain.
- Optional spaCy checks remain only where their tested parse establishes the reported form, part of speech, imperative, note instruction, or project-term misuse.
- Ambiguous constructions and unsupported rules emit nothing. The tool documents that it does not check them.
- General recommendations remain available through `ste100 explain`, but they do not produce violations.

## Standard pack

The bundled pack remains an internal machine-readable extraction of Issue 9. Its schema keeps only source data needed at runtime:

- source identity and file digests
- official rule and general-recommendation IDs with exact extracted requirements
- dictionary headwords, status, parts of speech, and forms
- dictionary alternatives and qualifiers with source locations

The pack removes internal review labels, rule treatment, conformance coverage, release gates, count reconciliation, and generated standard examples. Documentation calls the dictionary an extraction and does not call it an official structured dictionary.

## CLI

Text output starts with `PASS` or `FAIL`. It lists each finding once and does not print coverage totals.

JSON output uses the new result contract. Exit status remains `0` when `passed` is true, `1` when it is false, and `2` for invalid input or configuration.

`ste100 explain RULE` returns the extracted source requirement and source location only.

## Version

This changes the documented JSON and CLI output contracts. The next release is `0.2.0`, a pre-1.0 minor release. Version `0.1.0` remains immutable and its release notes receive a warning that its result model was replaced.

## Tests

Tests must prove:

- no schema, model, JSON artifact, CLI output, or documentation contains an invented review result
- analysis has no coverage records or review states
- one unapproved word produces one finding with all applicable rule IDs
- unknown words fail without speculative wording
- approved and project-approved terms do not fail
- unsupported or ambiguous heuristics emit nothing
- UTF-8 offsets, protected content, line endings, dictionary expressions, and optional spaCy checks still work
- generated schemas and bundled files reproduce byte for byte
- wheel contents contain the reduced runtime pack and no removed artifacts

Run Ruff, formatting, strict mypy, pytest with branch coverage, pip-audit, the mutation gate, Slophammer, SimpleDoc, wheel checks, the aggregate-only private regression, Pi Reviewer, and CI before release.

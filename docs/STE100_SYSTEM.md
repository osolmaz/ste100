# STE100 checker

This document defines the `ste100` result format, extracted standard data, and check boundaries.

## Purpose

The checker finds issues that its code can establish from the supplied text, extracted Issue 9 data, and optional project terms. It runs offline and returns exact UTF-8 byte ranges.

The checker does not determine full ASD-STE100 compliance. It does not return a result for a rule when the available evidence cannot establish an issue.

## Result

`AnalysisResult` contains:

- `standard_id`: `ASD-STE100`
- `standard_issue`: `9`
- `standard_digest`: SHA-256 digest of the source text used to build the extracted data
- `passed`: whether the implemented checks found no issue
- `findings`: issues found by the implemented checks

`passed` is `true` exactly when `findings` is empty. It describes this tool run only.

A finding contains:

- `rule_ids`: one or more official Issue 9 rule numbers
- `message`: the condition found by the check
- `byte_range`: half-open UTF-8 byte offsets
- `excerpt`: the exact text at that range

One byte range produces one finding. If two checks find conditions at the same range, the result combines their rule IDs and messages.

The result has no confidence, severity, coverage, applicability, review, or compliance fields.

## Vocabulary

The checker uses the extracted dictionary and an optional project dictionary.

A word or phrase passes the vocabulary check when one of these conditions is true:

- the extracted dictionary lists it as approved
- the supplied project dictionary contains it
- a longer approved dictionary expression contains it
- it is protected content such as code, a URL, an identifier, a number, or a unit value

A word listed as unapproved produces one finding for Rules 1.1 and 1.6. The finding includes extracted alternatives when available.

A word with both approved and unapproved entries produces one finding unless optional linguistic evidence selects an approved part of speech and form.

A word absent from the extracted dictionary and project dictionary produces one Rule 1.1 finding. The checker does not guess whether the word could become an approved project term.

## Project dictionary

A project dictionary is caller-owned configuration. It is not an ASD file format.

Each term has:

- `term`
- `category`: `technical_noun` or `technical_verb`
- optional `approved_forms`
- `meaning`
- `source`

The validator rejects malformed entries, one form assigned to different terms, and technical nouns longer than three words. Matching is case-insensitive and uses the longest term first.

## Implemented checks

The default checker can report these conditions:

- approved, unapproved, mixed-status, and missing vocabulary
- selected British spellings listed in the checker's fixed American-spelling map
- contractions
- semicolons
- unmatched parentheses
- a missing colon before a detected vertical list
- procedure sentences over 20 words when grouped-element counting is not ambiguous
- descriptive sentences over 25 words when grouped-element counting is not ambiguous
- descriptive paragraphs over six sentences

The optional pinned spaCy pipeline can also report:

- a dictionary word used with an unapproved part of speech
- a verb or adjective form absent from the extracted approved forms
- a project technical noun used as a verb
- a project technical verb used as a noun
- a procedure step whose parsed root is not imperative
- passive voice in a procedure
- an instruction in a note
- a warning or caution whose parse has neither a command nor an initial condition

The spaCy checks run only when the caller uses `--spacy`. The checker suppresses a linguistic sentence check when protected code removes required parse evidence.

## Unsupported checks

The checker emits nothing for conditions it cannot establish. This includes:

- word meaning
- whether an absent word qualifies as a technical noun or technical verb
- topic structure and paragraph order
- ambiguity and ease of comprehension
- simultaneous actions
- general recommendations
- descriptive passive voice
- uncertain `-ing` uses
- phrasal-verb meaning
- a missing comma when the checker cannot establish both the condition and instruction

`ste100 explain` still returns the extracted text for all 53 numbered rules and eight general recommendations.

## Protected content

The checker protects:

- caller-approved project terms
- URLs
- fenced and inline code
- identifiers with separators
- numbers and attached units

Protected values do not produce vocabulary, spelling, contraction, semicolon, or linguistic findings. Numbers still count as words where Issue 9 requires that count. Code does not affect structural checks.

## Document model

Input is UTF-8 text. The parser preserves:

- original text
- line endings
- half-open UTF-8 byte ranges
- paragraphs
- procedure steps
- notes
- warnings
- cautions
- vertical lists
- sentences and tokens

The checker does not normalize the source text before it creates findings.

## Extracted Issue 9 data

The runtime data directory contains:

```text
standard.json
rules.json
dictionary.json
```

`standard.json` identifies the source and stores SHA-256 digests for the two extracted artifacts.

`rules.json` contains the official rule or general-recommendation ID, extracted summary text, and source location.

`dictionary.json` contains extracted headwords, status, part of speech, forms, alternatives, qualifiers, and source locations.

This is an internal extraction from the checked-in Issue 9 text export. It is not an official structured dictionary. Pack validation checks schema validity, file digests, the 61-entry rule catalog, duplicate dictionary keys, and source digests. It does not label the extraction as approved or reviewed.

## Determinism

For fixed input bytes, extracted data, project terms, and optional spaCy version, the checker returns the same ordered result.

Runtime checks do not use network calls, model APIs, learned custom detectors, or generated rewrites. The optional spaCy package and model must be installed before offline use.

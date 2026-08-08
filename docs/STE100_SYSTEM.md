# Deterministic STE100 checker

This specification defines an offline checker for mechanically decidable parts of ASD-STE100 Issue 9. The checker uses a bundled standard pack, exact source offsets, project terminology, and an optional pinned spaCy pipeline.

The checker never certifies official compliance. It gives conclusive results only for the clauses named in its coverage matrix.

## Runtime flow

```text
UTF-8 text
    |
lossless document parser
    |
bundled Issue 9 pack + optional project dictionary
    |
deterministic checks + optional pinned spaCy evidence
    |
findings and 61 per-rule coverage records
```

The runtime does not download data, models, code, or standards. The same text, configuration, pack, code revision, and spaCy revision produce the same result.

## Bundled standard pack

The installed pack is under `ste100.data.issue9` and contains:

```text
standard.json
rules.json
dictionary.json
examples.json
conformance.json
```

`standard.json` records the source digest, Issue 9 identifier, review state, artifact digests, extracted counts, published counts, and a reconciliation note. Runtime loading checks every digest and rejects missing, extra, malformed, duplicate, unreviewed, or path-escaping artifacts.

Issue 9 prints totals of 875 approved and 1,274 unapproved words. The source table parser produces 876 approved and 1,320 unapproved part-of-speech rows after repairing wrapped headwords. The runtime keeps valid source rows instead of deleting entries to force count agreement. Pack validation reports the difference as a warning and checks that the manifest agrees with the artifacts.

Each dictionary entry contains:

- a stable ID
- normalized headword
- approved or unapproved status
- part of speech
- listed forms
- approved alternatives when the table column is unambiguous
- source page, row ID, and source digest
- reviewed state

An entry key consists of status, headword, and parts of speech. Duplicate keys are invalid. A headword can have approved and unapproved uses when Issue 9 distinguishes meaning or part of speech. Without sufficient linguistic evidence, the checker sends that use to human review. Approved meanings are not copied into the runtime pack because fixed-column text extraction can mix them with the example column; Rule 1.3 therefore stays in human review.

## Document model

The parser preserves the input text and uses half-open UTF-8 byte ranges. It identifies:

- paragraphs
- sentences
- procedure steps
- vertical-list items
- notes
- cautions
- warnings
- tokens and punctuation

The word counter treats parenthesized text, quoted text, numbers with units, URLs, identifiers, and hyphenated units as one element where Issue 9 requires it. Parenthesized prose counts as one word in its enclosing sentence and as a separate sentence for its own length check. A colon before a vertical list ends the introductory sentence for word counting.

The applicable interface rejects over-limit text and does not truncate it. Findings preserve the exact source excerpt at their byte range.

## Project dictionary

A project dictionary supplies approved technical nouns and verbs. Validation rejects:

- empty or malformed entries
- one form assigned to different terms
- technical nouns longer than three words
- direct conflicts with unapproved standard entries

Matching is case-insensitive and uses the longest approved term first. A matched project term is not reported as unknown vocabulary.

## Deterministic checks

The conformance matrix contains all 53 numbered rules and eight general recommendations. Each record has `full`, `partial`, or `none` scope.

Full scope means the complete mechanical requirement is checked. Partial scope means only the named clause is checked and the remaining requirement stays in human review. None means the complete requirement needs judgment.

The runtime includes checks for:

- approved, unapproved, ambiguous, and unknown vocabulary
- listed word forms and parts of speech when spaCy evidence is available
- configured technical nouns and verbs
- selected American English spellings
- contractions
- selected complex verb, `-ing`, and passive constructions
- procedure imperatives and possible multiple actions
- note instructions
- sentence and paragraph limits
- condition commas and vertical-list colons
- semicolons and balanced parentheses
- Issue 9 word-count rules
- unapproved phrasal verbs in the dictionary
- selected general recommendations for `that`, Latin abbreviations, and inclusive wording

A checker abstains when its evidence cannot prove a violation. Unapproved nouns and verbs remain in human review until configured terminology or linguistic context resolves their use because they can be technical terms. Absence of a partial-check finding never becomes a pass for the complete rule.

## Optional spaCy checks

The optional analyzer is pinned to spaCy 3.8.11 and `en_core_web_sm` 3.8.0. It supplies tokenization, lemmas, part-of-speech tags, morphology, dependency relations, and sentence boundaries. The CLI does not accept another model name or path, and startup rejects a different model version or a pipeline without both dependency parsing and part-of-speech analysis.

spaCy does not decide compliance. Checker code applies explicit rules to its evidence. Ambiguous cases produce `human_review`. Examples include descriptive passive voice with an unknown agent, an `-ing` form that can be a technical noun, and two procedure actions that can occur at the same time.

The adapter merges list markers and `NOTE:`, `WARNING:`, and `CAUTION:` labels with the sentence that follows. Tests use manually verified sentences for imperative, passive, note, safety, word-form, and abstention behavior.

The default runtime works without spaCy. Rules that require linguistic evidence remain in human review when no analyzer is supplied.

## Findings

A finding contains:

- stable finding ID
- Issue 9 rule ID
- `violation` or `human_review`
- checker ID
- message
- optional UTF-8 byte range and exact excerpt

Findings from deterministic clauses are conclusive only when their kind is `violation`. Human-review findings explain the uncertainty. General recommendations can only produce human-review findings and never change the process exit status.

## Coverage

Every analysis returns exactly 61 coverage records with one of these states:

- `passed`
- `failed`
- `human_review`
- `not_applicable`

A full check can pass when it ran and found no violation. A partial check cannot pass the complete rule. Rules with no mechanical treatment always require human review.

## CLI behavior

`ste100 analyze` uses the bundled pack unless `--standard-pack` selects another validated local pack. JSON output includes the source digest so integrations can identify the exact standard data.

Exit codes are:

- `0`: no conclusive violation
- `1`: one or more conclusive violations
- `2`: invalid input, pack, project dictionary, or spaCy configuration

Raw source text is not logged by the library. Text output prints only the finding excerpts that the caller asked it to analyze.

## Tests and private data

Tests include standard-derived examples, synthetic boundaries, malformed input, Unicode, project terms, values, identifiers, URLs, code, and sanitized response-style patterns.

The private response-style corpus is never committed. A local script runs aggregate regression checks over it without printing prose, paths, session IDs, timestamps, or model names. Public fixtures are newly written synthetic sentences that contain no private provenance.

## Security and licensing

Artifact paths must remain inside the selected pack. Pack and source digests use SHA-256. JSON contracts reject undeclared fields.

The repository's MIT license covers original code and documentation. ASD source material retains the terms in [`../NOTICE`](../NOTICE).

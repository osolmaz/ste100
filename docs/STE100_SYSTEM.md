# STE100 detection and rewriting specification

This specification defines an offline system that finds ASD-STE100 Issue 9 violations and prepares rewrite candidates. It combines reviewed standard data, deterministic checks, a learned violation detector, and a separate learned rewriter.

The system never certifies official compliance. It reports which checks ran, which findings are conclusive, and which requirements remain unchecked or need human review.

## Architecture

```text
                         Reviewed Issue 9 pack
                                  |
                    deterministic STE100 checker
                                  |
          +-----------------------+----------------------+
          |                                              |
  violation detector                              STE100 rewriter
          |                                              |
          +------------- check candidate ---------------+
```

The detector and rewriter are separate releases. They share contracts, protected-span handling, standard revisions, and benchmark split identities. They do not share selection authority. A detector release cannot promote a rewriter, and a rewriter release cannot change detector thresholds.

## Repository boundary

The production repository contains:

```text
schemas/                    Portable JSON Schemas
standard/issue-9/drafts/    Review-required extraction artifacts
src/ste100/                 Parser, checker, contracts, and CLI
tests/                      Standard, unit, integration, and regression tests
```

Training code, generated datasets, checkpoints, predictions, and experiment journals belong in a separate research repository. Published datasets and models use revision-pinned repositories. The production runtime does not download standards, models, code, or project data.

The checked-in draft extraction is not a runtime standard pack. It contains all 53 numbered rules and 8 general recommendations. Its dictionary extraction produces 876 approved and 1,318 unapproved candidates, while Issue 9 states 875 and 1,274 words. The extraction audit marks these rows as drafts and `runtime_eligible: false` until a reviewer resolves every discrepancy.

## Standard pack

A reviewed pack is a local directory with these files:

```text
standard.json
rules.json
dictionary.json
examples.json
conformance.json
```

`standard.json` gives the format version, standard ID, issue, review state, source identity, expected counts, and the SHA-256 digest of every other file. Artifact names are fixed. Paths must stay inside the pack after symbolic links are resolved.

The loader rejects:

- malformed or unknown fields
- a draft pack unless a validation-only caller opts in
- missing or extra artifacts
- absolute paths, parent traversal, and symbolic-link escapes
- digest mismatches
- duplicate rule, dictionary, example, or conformance IDs
- a rule catalog that differs from the canonical 61 Issue 9 IDs
- unknown rule references
- missing conformance records
- count mismatches
- draft records under a reviewed manifest

The published Issue 9 counts are 53 numbered rules, 8 general recommendations, 875 approved words, and 1,274 unapproved words.

The exact contracts are in [`../schemas/`](../schemas/). Pydantic models in `src/ste100/models.py` are the implementation authority. Generated JSON Schemas must reproduce byte for byte in tests.

## Rule and conformance records

A rule record contains:

- `rule_id`
- the reviewed requirement
- its primary treatment: `deterministic`, `learned`, `human_review`, or `not_checked`
- review state
- page and source-digest provenance
- optional implementation notes

A separate conformance record contains:

- deterministic checker IDs
- learned role, when applicable
- `full`, `partial`, or `none` automatic coverage
- `blocking`, `report_only`, or `human_review` release authority
- the reason for that treatment

This separation prevents a partial checker from silently claiming the complete rule. For example, contraction detection is a conclusive part of Rule 4.2, but it does not detect every omitted word. A clean contraction result therefore remains `not_checked` for the complete rule.

## Dictionary records

A reviewed dictionary record contains the displayed word, approval status, parts of speech, approved meanings, approved forms, alternatives, review state, and source provenance.

The deterministic checker can conclude that a reviewed unapproved entry is a violation. It can also recognize a reviewed approved form. It cannot conclude that an approved word has the correct part of speech or meaning from spelling alone. Those questions remain learned or human-review work unless a later deterministic implementation proves the context.

OCR and layout extraction can propose rows, but they are never controlled-vocabulary authority. Exact PDF text and human row review decide the word, punctuation, form, part of speech, meaning, and alternative.

## Document model

The parser preserves the caller's text and creates:

```text
Document
  Block
    Paragraph | List | Procedure | Note | Caution | Warning
      Sentence
        Token
```

All ranges are half-open byte offsets into the original UTF-8 text. The parser does not normalize Unicode or line endings. A returned range must decode at a UTF-8 character boundary and reproduce the source excerpt.

The deterministic word counter treats parenthesized text, quoted text, numbers with units, URLs, identifiers, and hyphenated units as single countable elements where the applicable Issue 9 rules require it. Under the full text of Rule 8.5, parenthesized prose counts as one word in the enclosing sentence and as a separate sentence for its own length check. A colon terminates a sentence in a vertical list. Procedure markers are not treated as separate prose sentences.

## Project terminology

A project dictionary contains `technical_noun` and `technical_verb` entries with canonical terms, approved forms, meanings, and provenance.

Validation rejects ambiguous forms, conflicting owners, technical nouns longer than three words, and reviewed standard conflicts. Matching is case-insensitive and longest first. A matched project term is exempt from unknown-vocabulary findings and becomes a protected span during rewriting.

## Protected content

Before learned rewriting, the runtime replaces these spans with ordered sentinels:

- project terms
- numbers and units
- identifiers and part numbers
- URLs
- inline and fenced code
- caller-supplied ranges

A candidate is invalid if a sentinel is missing, changed, duplicated, unknown, or reordered. The runtime restores the exact original text only after validation. Dataset targets must also contain each protected source value exactly once and in source order.

Protected-span success is a hard gate. It does not prove that unprotected meaning is unchanged.

## Findings and coverage

A finding contains a stable ID, rule ID, kind, message, optional byte range and excerpt, and either a checker ID or model ID. Learned findings also include a score.

Finding kinds are:

- `violation`: conclusive deterministic evidence
- `probable_violation`: report-only learned evidence
- `human_review`: evidence that cannot decide the rule
- `not_checked`: an explicit unavailable check

Coverage contains all 61 Issue 9 rule IDs for every analysis. Statuses are `passed`, `failed`, `probable_violation`, `human_review`, `not_checked`, and `not_applicable`.

Only a fully implemented deterministic requirement can return `passed`. No finding from a learned detector is not a pass. No vocabulary finding without a reviewed standard pack is not a pass.

## Deterministic checks

The initial vertical slice implements:

- reviewed approved and unapproved vocabulary lookup for the mechanical part of Rule 1.1
- contraction detection for the mechanical part of Rule 4.2
- the 20-word procedure and safety-instruction sentence limit in Rule 5.1
- the 25-word descriptive sentence limit in Rule 6.3
- the six-sentence paragraph limit in Rule 6.6
- the semicolon prohibition in Rule 8.1
- complete mechanical behavior for Rules 8.4, 8.5, and 8.7
- partial Rule 8.6 handling for numbers, measurements, abbreviations, identifiers, and quoted text

Rule 8.6 remains partial because unquoted titles, headings, labels, and multiword proper nouns need document context. It cannot return `passed` in the initial release. Rules 5.1 and 6.3 also remain partial in the conformance matrix because they depend on that grouping. An over-limit sentence with a possible grouped element returns `human_review` instead of a conclusive violation.

The conformance matrix exposes every other rule even when no checker exists.

## Shared dataset contract

Detector and rewriter data use one record with:

- deterministic `record_id`
- source kind, stable source ID, and source digest
- parent record IDs for generated data
- source text
- rule IDs and span-aware annotations
- protected spans
- complete-group split membership
- annotation state
- observed conversation outcome, when applicable
- optional rewrite target
- `inferred_approval`, fixed to `false`

Source kinds are `standard_example`, `technical_document`, `conversation_revision`, and `synthetic`. Annotation states are `weak`, `reviewed`, and `adjudicated`.

Complete documents and conversations stay in one split. The validator also prevents a source ID, exact text, model family, or time bucket from crossing splits. Synthetic children stay in the same split as their parents. Self references and lineage cycles are invalid. Synthetic records must cite a reviewed clean standard example or an adjudicated `no_violation` or exception parent. Checker-clean text is not sufficient synthetic truth.

Conversation outcomes are observed labels: `revision_requested`, `continued_without_revision`, `conversation_ended`, or `explicit_approval`. Silence is never converted to acceptance. Conversation revisions remain weak preference evidence until a reviewer assigns STE100 labels.

## Source corpus decisions

Learned-data work can use these sources only under the stated conditions:

1. Reviewed Issue 9 examples can provide rule fixtures and standard-derived training records.
2. The private response-style corpus can support a private pilot after authorization, conversion to the shared contract, protected-content checks, and human STE100 review. It cannot be redistributed publicly and is not automatically an STE100 rewrite corpus.
3. A technical-document corpus needs a recorded license, stable source identity, and document-level split before use. No public technical corpus is selected yet.
4. Synthetic transformations can start only from reviewed standard positives or adjudicated clean records.
5. Open Pangram and EditLens artifacts remain excluded until a separate decision accepts their CC BY-NC-SA 4.0 obligations.

Large-scale mining, teacher generation, or training remains blocked until a 300-to-500-unit pilot establishes annotation quality, natural-passage evaluation, and teacher viability.

## Detector

The detector predicts rule IDs, scores, and optional UTF-8 byte spans. It is calibrated by rule. Invalid rule IDs, scores outside zero to one, and out-of-document spans are rejected.

The first detector release treats spans as report-only. A model manifest can record span gating, but changing it to blocking requires separate reviewed evidence. Detector evaluation reports raw support, precision, recall, false positives, false negatives, false alarms per 1,000 words, span results, calibration, and collection-level results.

## Rewriter

The rewriter receives sentinel-masked text and optional findings. It returns one untrusted candidate. The runtime restores protected text, parses the candidate, reruns deterministic checks, and rejects candidates that introduce a new deterministic violation.

The output status is review-required or rejected. There is no automatic approved status.

Detector hints are an ablation, not a default assumption. The same frozen natural evaluation set must compare the rewriter with and without hints. Hints can become the default only when they improve human-accepted rewrites by at least 3 absolute percentage points, uncertainty does not include no improvement, and protected-content and fact-error results do not regress. Otherwise, the simpler no-hint path wins.

## Natural rewrite evaluation

Checker delta is diagnostic. It cannot establish meaning preservation.

The first natural rewrite release uses at least 200 held-out technical passages. Two reviewers independently judge whether each candidate preserves all facts, intent, conditions, warnings, and procedure order. Disagreements are adjudicated. Reports include raw accepted and rejected counts, absolute rates, Wilson intervals, omissions, additions, protected-content errors, and deterministic violations introduced.

Release gates are:

- 100% protected-content preservation
- zero safety-sensitive omissions or changed conditions
- at least 95% adjudicated meaning acceptance
- a Wilson lower bound of at least 90% for meaning acceptance
- no increase in deterministic violations on previously clean input

When two candidates differ by less than 3 absolute percentage points in meaning acceptance, or uncertainty includes that difference, they are tied. The smaller, faster, simpler, and safer candidate wins.

## Pretraining contamination

Every model manifest records the base model and immutable revision plus `known_absent`, `known_present`, or `unknown` pretraining contamination. Unknown contamination is disclosed as a warning.

Standard examples cannot be the sole release evidence for a model with known or unknown exposure to the standard. Natural technical passages, document-held splits, time holdouts, and model-family holdouts remain separate result strata. A contaminated diagnostic result cannot promote a model by itself.

## Model releases

Detector and rewriter manifests independently pin:

- model ID, role, and semantic release
- artifact and evaluation digests
- standard issue
- base model ID and revision
- contamination assessment
- dataset digests
- registered thresholds
- protected-content, span, and detector-hint settings
- maintainer selection authority

Detector releases require rule macro F1, span F1, and calibration thresholds. Rewriter releases require meaning-preservation, protected-content, and deterministic non-regression thresholds. Models do not select or approve themselves.

## Runtime and security

All analysis is deterministic when the text, project dictionary, reviewed pack, checker revision, detector revision, and thresholds are fixed.

The runtime applies bounded input and output limits. It does not truncate over-limit technical content. Raw text is not logged by default. Model output is handled as text and is never parsed as markup.

## Boundaries

This system assists authors and reviewers. It does not replace the ASD-STE100 standard, an organization's terminology process, or human approval of technical content.

The repository's MIT license covers original code and documentation. ASD source material retains the terms described in [`../NOTICE`](../NOTICE).

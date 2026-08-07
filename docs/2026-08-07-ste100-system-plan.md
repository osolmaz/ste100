---
title: Build STE100 detection and rewriting
author: Onur Solmaz <2453968+osolmaz@users.noreply.github.com>
date: 2026-08-07
---

# Build STE100 detection and rewriting

This plan covers two products that share one standard and data program. The first detects ASD-STE100 violations and identifies the applicable rules and source spans. The second converts complicated English into an STE100 candidate. The system must preserve technical meaning, show its evidence, and leave document approval to a person.

The system contract is defined in [`STE100_SYSTEM.md`](STE100_SYSTEM.md). Adjacent methods and possible data sources are recorded in [`2026-08-07-detection-and-rewrite-inspirations.md`](2026-08-07-detection-and-rewrite-inspirations.md).

## Requirements

The completed system must:

- represent Issue 9 as reviewed structured data
- run conclusive checks without a learned model
- train a span-aware, multi-rule violation detector
- train a direct English-to-STE100 rewriter
- preserve configured terms, all numbers and units, and every identifier
- report rule coverage and remaining human-review work
- keep training and validation separate from the sealed test
- reproduce every released model and evaluation from pinned artifacts

The public repository and outputs must distinguish original MIT-licensed work from ASD source material covered by [`NOTICE`](../NOTICE).

## Assumptions

The project has permission to reproduce the standard. The official PDF contains usable embedded text. OCR can help inspect layout, but OCR output will not become authoritative vocabulary or rule text.

The first target is English technical documentation. Other English text can be rewritten, but terms that cannot be safely simplified remain unchanged and are marked for review.

A learned model can propose a violation or rewrite. It cannot approve a document or override a conclusive deterministic finding.

## Scope

This program includes the standard pack, document parser, deterministic checker, detector dataset and model, rewrite dataset and model, benchmark, native runtime, model export, and release qualification.

Browser packaging follows native qualification. An editor plugin, hosted writing service, and organization-specific terminology workflow are outside the first release.

## Repository boundaries

The public `ste100` repository contains:

- standard-pack schemas and reviewed Issue 9 records
- parser and checker, including the reporting contracts and CLI together with the library
- benchmark schemas and public fixtures
- model-loading and evaluation contracts
- user and maintainer documentation

A separate research repository will contain annotation tools, spaCy bootstrap rules, synthetic-data workers, training code, experiment plans, and evaluation code. Large data and model artifacts will use revision-pinned Hugging Face repositories. The research repository will import the standard pack from an exact `ste100` commit and will not copy rule data.

No new repository is created until its visibility and ownership are approved. Its artifact boundary must also be approved.

## Work sequence

### Standard data

Define JSON Schemas for the manifest, rule records, dictionary entries, examples, project dictionaries, findings, dataset records, and model manifests.

Extract Issue 9 into reviewed records. Preserve the original extracted text. Record the page and section, with row provenance where applicable. Reconcile every count against the expected 53 numbered rules, 8 general rules, 875 approved words, and 1,274 unapproved words.

Generate human-readable reference pages and checker tables from the structured data. Do not maintain separate handwritten copies of a rule.

**Completion evidence:** schema validation, count checks, source digests, and a signed-off review ledger for every rule and dictionary row.

### Document parser

Implement one parser for analysis and rewriting. It must identify sentences, paragraphs, lists, procedure steps, notes, cautions, warnings, tokens, punctuation, source offsets, and protected spans.

Implement the sentence-boundary behavior required by Issue 9 before adding sentence-length checks. Preserve original offsets and line endings. Reject over-limit units instead of truncating them.

**Completion evidence:** fixtures for standard examples, abbreviations, measurements, lists, procedures, malformed input, and Unicode text; property tests for stable offsets and lossless reconstruction.

### Deterministic checker

Create a conformance matrix for every Issue 9 rule. Mark each treatment as deterministic, learned, configured, or human review.

Implement high-confidence checks first. These include dictionary lookup, parts of speech where unambiguous, punctuation, contractions, sentence and paragraph limits, list structure, and project terminology. Findings must cite a rule and checker. They must also include the location and evidence together with the assigned treatment.

**Completion evidence:** STE and non-STE fixtures for every implemented check, no unclaimed rule in the conformance matrix, and explicit `not_checked` or `human_review` results for uncovered requirements.

### Benchmark

Build shared records for detector and rewrite evaluation. Include standard examples, targeted single-rule cases, natural technical prose, obscure prose, mixed-rule passages, valid identity cases, and protected-content guards.

Split by source document. Remove normalized source overlap across training, development, validation, sealed test, and public benchmark material. Set minimum worthwhile effects and safety vetoes before final comparisons.

**Completion evidence:** immutable split manifests, leakage audit, rule-coverage report, human annotation guide, and frozen release metrics.

### Dataset bootstrap

Run source text through deterministic checks and a pinned spaCy pipeline. Use POS tags and morphology to propose spans for context-dependent rules. Dependency relations can supply more evidence. Keep these annotations as weak labels.

Create controlled transformations that insert one known violation into valid text. Add mixed-rule transformations only after single-rule generators pass human review. Store the generator version and label provenance on every annotation.

Do not treat an unlabeled rule as a negative label. Do not use rule-generated cases as the only validation of the same rule family.

**Completion evidence:** per-rule candidate counts, transformation tests, sampled human error rates, and complete provenance.

### Human gold data

Write a rule-specific annotation guide. Review natural text and generated candidates with two independent reviewers. Adjudicate disagreements in development and validation data, then apply the same process to test data.

Each record includes rule applicability, violation labels, exact spans, accepted rewrites, protected content, document context, provenance, reviewer state, and split role. Use per-rule quotas so common vocabulary findings do not hide rare grammar and document rules.

**Completion evidence:** agreement report, adjudication ledger, per-rule support, source-document split audit, and dataset digest.

### Violation detector

Train a pretrained English encoder with outputs for rule applicability, sentence-level multi-label detection, and per-rule token spans. Train first on verified examples and minimal pairs, then mixed examples, natural prose, and hard negatives.

Calibrate each rule independently. Compare the model with deterministic and spaCy baselines. Keep model findings separate from deterministic results in stored output.

**Promotion evidence:** raw precision and recall by rule, span results, false alarms per 1,000 words, calibration, unseen-document results, and a worthwhile improvement over the simpler baseline. Rules that do not meet their gate remain human-review checks.

### Human rewrite data

Create accepted rewrites for standard examples, technical passages, deliberately obscure English, and procedures. Include warnings and already-valid text. Mark all protected names and values. Also mark units and identifiers. Mark URLs and code separately.

A rewrite can have multiple accepted targets. Reviewers judge meaning preservation separately from STE100 rule treatment.

**Completion evidence:** accepted-target audit, protected-span audit, document-level split audit, and reviewer agreement.

### Teacher qualification

Select a strong teacher through a bounded comparison on human data. Pin the model, prompt or fine-tuning code, decoding settings, standard revision, and project terminology behavior.

The teacher must improve checker findings while preserving meaning and protected content. Its output remains synthetic data with teacher provenance, even when it passes automatic checks.

**Promotion evidence:** human evaluation on held-out documents, rule-level results, and protected-content results. Report latency and estimated generation cost with them.

### Synthetic rewrite pilot

Generate a durable pilot of 50,000 to 250,000 source-target pairs. Publish recoverable chunks and audit them before merge. Keep rejected rows and rejection reasons.

Train one compact student at several data sizes. Expand generation only if more synthetic data improves natural held-out examples by more than the registered worthwhile threshold.

Any substantial paid launch requires measured throughput, low and high cost estimates, a cost ceiling, a tested pause-resume path, and explicit approval under the paid-compute policy.

**Promotion evidence:** data-scaling curve, teacher-noise audit, full generation cost estimate, and a decision to stop or expand.

### Rewriter students

Train direct encoder-decoder candidates near 20 million, 50 million, and 100 million parameters. Use human targets, synthetic targets, identity rows, correct detector hints, predicted hints, and missing hints.

Audit the tokenizer over the complete corpus before training. Byte fallback and round trips must work for all input. Stop on an over-limit field. Do not drop or truncate the row.

Start with greedy decoding. Compare a more expensive decoder only through a registered paired test. Select the smallest model that clears the quality and safety gates as well as the latency and package gates.

**Promotion evidence:** violations removed and introduced, human meaning judgments, omitted and added facts, protected-content results, identity stability, and document structure. Report latency, memory use, and artifact size separately.

### Runtime integration

Implement analysis and rewriting in the order defined by the system specification. Replace protected spans with sentinels before generation. Reject candidates with missing, duplicated, or invalid sentinels. Check every candidate again before returning it.

Expose transport-independent library operations first, followed by a CLI and machine-readable output. The runtime must work offline with preinstalled, revision-pinned artifacts. It must not log source text by default.

**Completion evidence:** end-to-end fixtures, bounded-resource tests, malformed-model-output tests, native model attestation, and deterministic results for pinned inputs and artifacts.

### Release qualification

Freeze the exact standard and checker before report-only validation. Freeze the detector and rewriter at the same boundary, together with their thresholds and decoding configuration. Open the sealed test once after all earlier gates pass.

Run blind human review, rule-level detector evaluation, protected-content tests, procedure and warning tests, Unicode tests, resource-limit tests, and native-to-export agreement checks. A safety-sensitive omission or changed protected fact vetoes release.

Keep observed results, release recommendations, and maintainer approval as separate states. A recommendation does not deploy a model.

**Completion evidence:** immutable prediction files, raw counts, evaluation report, artifact manifests, cost record, and explicit approval state.

### Packaging and maintenance

Export approved native models to ONNX and verify output agreement. Add browser packaging only when the native artifacts pass. Record every model and tokenizer revision. Include the dataset revision. Record the standard and code revisions in the same manifest, along with the runtime revision.

Collect production corrections only with explicit consent. Do not train directly on unreviewed user text. Review false positives, missed violations, and failed rewrites by rule before registering a new data or model program.

**Completion evidence:** reproducible packages, upgrade and rollback instructions, privacy defaults, and a release checklist.

## Acceptance criteria

The first production release is complete when:

- all Issue 9 records are reviewed and validated
- every rule has a conformance-matrix treatment
- deterministic checks and learned findings remain distinguishable
- detector results meet registered per-rule and aggregate gates
- rewrite results meet the meaning and protected-content gates as well as the compliance gates
- no source-document leakage exists between split roles
- native and exported artifacts agree within the registered limit
- resource and safety suites pass
- the release report identifies the exact approved artifacts
- no automatic result claims official compliance

## Verification commands

The implementation will provide stable commands for these checks:

```text
validate-standard
check-rule-coverage
verify-splits
run-checker-tests
run-detector-evaluation
run-rewriter-evaluation
verify-model-manifest
run-safety-suite
```

The command names describe the checks required by this plan. They are not implemented interfaces. The implementation can choose their final CLI spelling in one hard cutover before the first release.

## Stop conditions

Stop and report evidence when source records cannot be reconciled with Issue 9, a rule lacks a reviewable interpretation, model data leaks across split roles, protected content cannot be preserved, a tokenizer cannot represent the corpus, or a model improvement remains inside the registered practical tie region.

Do not expand synthetic generation, train larger students, open sealed data, or deploy a candidate to work around one of these conditions.

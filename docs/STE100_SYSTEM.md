# STE100 detection and rewriting specification

This specification defines a system that finds ASD-STE100 violations and rewrites complicated English as an STE100 candidate. The system combines reviewed Issue 9 data, deterministic checks, a learned violation detector, and a learned rewriter.

The learned models do not certify compliance. The system reports which checks ran, which findings remain, and which requirements need human review.

## System outline

```text
                         Reviewed Issue 9 data
                                  |
                    deterministic STE100 checker
                                  |
          +-----------------------+----------------------+
          |                                              |
  violation detector                              STE100 rewriter
          |                                              |
          +------------- check candidate ---------------+
```

The detector and rewriter are separate models. They share the standard pack, document model, project terminology, dataset records, and benchmark splits. Each model has its own training and calibration. It also has its own release and replacement cycle.

## Repository structure

The production repository uses this structure:

```text
standard/
└── issue-9/
    ├── manifest.json
    ├── rules.json
    ├── dictionary.jsonl
    ├── examples.jsonl
    └── schemas/
        ├── manifest.schema.json
        ├── rule.schema.json
        ├── dictionary-entry.schema.json
        └── example.schema.json
src/
├── document/
├── checker/
├── detector/
├── rewriter/
└── reporting/
tests/
├── standard/
├── document/
├── checker/
└── integration/
```

Training code and generated datasets belong in a separate research repository. Checkpoints, predictions, and experiment journals also stay there. Published datasets and models live in revision-pinned Hugging Face repositories. The production repository contains the contracts needed to load and evaluate them.

## Standard pack

A standard pack is a local directory containing one reviewed representation of an ASD-STE100 issue. The runtime loads the manifest first and then loads the files named by the manifest. It does not fetch remote files while processing a document.

### Minimal manifest

```json
{
  "format_version": "1",
  "standard": "ASD-STE100",
  "issue": "9",
  "rules": "rules.json",
  "dictionary": "dictionary.jsonl",
  "examples": "examples.jsonl"
}
```

### Manifest fields

| Field | Required | Type | Meaning |
| --- | --- | --- | --- |
| `format_version` | Yes | string | Standard-pack format. The first format is `1`. |
| `standard` | Yes | string | Must be `ASD-STE100`. |
| `issue` | Yes | string | ASD issue represented by the pack. |
| `rules` | Yes | relative path | Rule records. |
| `dictionary` | Yes | relative path | Dictionary records. |
| `examples` | Yes | relative path | Verified example records. |
| `source` | No | object | Source PDF identity and digest. |
| `counts` | No | object | Expected record counts checked at load time. |

Paths must remain inside the pack. Absolute paths and parent traversal are invalid. URLs and symbolic-link escapes are also invalid. Unknown fields are rejected by the schema.

### Source identity

A complete Issue 9 manifest records the official source:

```json
{
  "format_version": "1",
  "standard": "ASD-STE100",
  "issue": "9",
  "rules": "rules.json",
  "dictionary": "dictionary.jsonl",
  "examples": "examples.jsonl",
  "source": {
    "title": "ASD-STE100 Simplified Technical English",
    "issue": "9",
    "pages": 434,
    "pdf_sha256": "d1f4ea9e7cd6e46b47aa9057209f99e78c0e9cfc4e27a5b07895b05c1a166431"
  },
  "counts": {
    "numbered_rules": 53,
    "general_rules": 8,
    "approved_words": 875,
    "unapproved_words": 1274
  }
}
```

The extracted text remains unchanged as provenance. Reviewed records supply runtime data. OCR output does not.

## Rule records

`rules.json` contains an array of rule records. A rule record describes the standard requirement and how the system treats it.

```json
{
  "id": "3.4",
  "title": "Do not use complex verb constructions",
  "scope": "sentence",
  "requirement": "Use the verb forms permitted by the rule.",
  "treatment": "learned",
  "checks": ["complex-verb-construction"],
  "source": {
    "section": "Part 1, Section 1",
    "page": 69
  }
}
```

### Rule fields

| Field | Required | Type | Meaning |
| --- | --- | --- | --- |
| `id` | Yes | string | Rule identifier used by ASD-STE100. |
| `title` | Yes | string | Rule title. |
| `scope` | Yes | enum | `token`, `sentence`, `paragraph`, `step`, or `document`. |
| `requirement` | Yes | string | Reviewed operational statement of the requirement. |
| `treatment` | Yes | enum | `deterministic`, `learned`, `configured`, or `human_review`. |
| `checks` | Yes | string array | Checker or detector identifiers assigned to the rule. |
| `source` | Yes | object | Issue and section, with page and optional row provenance. |
| `exceptions` | No | array | Reviewed exceptions defined by the standard. |
| `notes` | No | string | Implementation limits that do not change the requirement. |

The rule identifier is stable. A checker identifier describes an implementation and can change without changing the rule identifier. One checker can support more than one rule, and one rule can require more than one checker.

## Dictionary records

`dictionary.jsonl` contains one JSON object per dictionary entry. A record represents a word together with its approval status, part of speech, and meanings.

```json
{
  "id": "close-v",
  "word": "close",
  "part_of_speech": "verb",
  "approval": "approved",
  "meanings": [
    {
      "id": "close-v-1",
      "definition": "Move two parts together until they touch.",
      "alternatives": []
    }
  ],
  "source": {
    "page": 214,
    "row": 6
  }
}
```

### Dictionary fields

| Field | Required | Type | Meaning |
| --- | --- | --- | --- |
| `id` | Yes | string | Stable entry identifier. |
| `word` | Yes | string | Dictionary headword in its published spelling. |
| `part_of_speech` | Yes | string | Published part of speech. |
| `approval` | Yes | enum | `approved` or `unapproved`. |
| `meanings` | Yes | array | Approved meanings or replacement guidance. |
| `forms` | No | string array | Permitted inflected forms stated or derived under a reviewed rule. |
| `source` | Yes | object | Page and row provenance. |

A word is not approved in every context merely because an approved entry exists. The checker must consider the part of speech and approved meaning. When meaning cannot be determined reliably, it reports human review.

## Standard examples

`examples.jsonl` contains verified STE and non-STE examples from the standard.

```json
{
  "id": "issue-9-3.4-example-1",
  "rule_ids": ["3.4"],
  "non_ste": "The operator should have been notified.",
  "ste": ["Notify the operator."],
  "source": {
    "page": 69
  }
}
```

`ste` is an array because the standard can permit more than one valid rendering. Examples are fixtures and public diagnostic cases. They are not a substitute for a document-held validation or sealed test set.

## Project dictionary

A project dictionary supplies terminology that the general standard pack cannot know.

```json
{
  "format_version": "1",
  "standard_issue": "9",
  "terms": [
    {
      "text": "auxiliary power unit",
      "category": "technical_name",
      "forms": ["auxiliary power units"],
      "abbreviations": ["APU"],
      "preserve": true
    }
  ]
}
```

### Project term fields

| Field | Required | Type | Meaning |
| --- | --- | --- | --- |
| `text` | Yes | string | Canonical term. |
| `category` | Yes | enum | `technical_name` or `technical_verb`. |
| `forms` | No | string array | Approved written forms. |
| `abbreviations` | No | string array | Approved abbreviations. |
| `meaning` | No | string | Meaning used for review and disambiguation. |
| `preserve` | No | boolean | Whether rewriting must preserve the matched text exactly. Default is `true`. |

Duplicate terms with conflicting categories are invalid. The runtime uses longest-match-first resolution when project terms overlap.

## Document model

The parser converts input into one document model before checks or rewriting begin.

```text
Document
  Block
    Paragraph | List | Procedure | Note | Caution | Warning
      Unit
        Sentence
          Token
          ProtectedSpan
```

Every node carries half-open UTF-8 byte offsets into the original input. A range starts at `start` and stops before `end`. The parser preserves original text and line endings for reporting and diff generation.

A procedure is divided into steps before sentence analysis. The rewriter processes one paragraph or one procedural step at a time. It never moves text between document units without an explicit document-level operation approved by the caller.

## Findings

A finding reports the result of one check against one source range.

```json
{
  "rule_id": "3.4",
  "check_id": "complex-verb-construction",
  "status": "probable_violation",
  "source": "learned",
  "locations": [
    {
      "start": 18,
      "end": 41
    }
  ],
  "message": "This verb construction can make the instruction difficult to understand.",
  "confidence": 0.94
}
```

### Finding fields

| Field | Required | Type | Meaning |
| --- | --- | --- | --- |
| `rule_id` | Yes | string | Standard rule. |
| `check_id` | Yes | string | Checker or detector that produced the result. |
| `status` | Yes | enum | Result status. |
| `source` | Yes | enum | `deterministic` or `learned`. |
| `locations` | Yes | array | Source ranges involved in the finding. |
| `message` | Yes | string | Plain explanation. |
| `confidence` | Learned only | number | Calibrated probability from 0 through 1. |
| `evidence` | No | object | Tokens, parse relations, or values that support the finding. |

Finding statuses are:

| Status | Meaning |
| --- | --- |
| `violation` | The check has conclusive evidence. |
| `probable_violation` | The learned detector found evidence above its registered threshold. |
| `passed` | The named check ran and found no violation in its declared scope. |
| `not_checked` | The check could not run, usually because configuration was absent. |
| `human_review` | The standard requires a judgment the system cannot make reliably. |

A missing finding does not mean that a rule passed. The response includes a coverage record for every applicable rule.

## Detector

The learned detector is a bidirectional encoder with independent outputs for rule applicability, sentence-level labels, and token spans. Multiple rules can apply to the same token.

For each rule, training annotations use these labels:

| Label | Meaning |
| --- | --- |
| `violation` | The text violates the rule. |
| `no_violation` | The rule applies and the text satisfies it. |
| `not_applicable` | The rule does not apply to this unit. |
| `insufficient_context` | The available unit does not permit a decision. |

The detector publishes thresholds and calibration evidence per rule. It does not convert a low probability into proof that a rule passed.

Deterministic and learned results remain separate in storage. The reporting layer can merge them for display, but it cannot replace a conclusive deterministic result with a learned result.

## Rewriter

The rewriter is a direct encoder-decoder. It receives source text, document-unit type, project terms, protected-span sentinels, and optional detector findings. It returns text only.

```text
<unit>procedure-step</unit>
<terms>auxiliary power unit | APU</terms>
<rules>1.1 3.4</rules>
<text>The source sentence.</text>
```

Training includes inputs with correct findings, predicted findings, incomplete findings, and no findings. This prevents a detector miss from making rewriting impossible.

The first decoding baseline is greedy decoding. A more expensive decoder is adopted only when a registered comparison shows a worthwhile improvement without a safety regression.

## Protected spans

The preprocessing layer identifies content that rewriting must preserve. It replaces each protected span with a unique sentinel before model inference.

```text
Disconnect <KEEP_0> from connector <KEEP_1>.
```

A candidate is invalid when a sentinel is missing, duplicated, reordered where order is significant, or changed. The runtime restores original bytes only after sentinel validation passes.

Protected spans include configured terms and part numbers. They also include identifiers, URLs, code, and other caller-supplied ranges. Numbers and units receive rule-aware comparison because an STE rewrite can change presentation without permission to change value.

## Analysis operation

The transport-independent analysis operation accepts the following request. `document_type` is `descriptive`, `procedural`, `mixed`, or `unknown`.

```json
{
  "text": "The component should have been removed.",
  "standard_issue": "9",
  "project_dictionary": null,
  "document_type": "descriptive"
}
```

It returns:

```json
{
  "findings": [],
  "coverage": [],
  "revisions": {
    "standard": "issue-9@sha256:...",
    "checker": "...",
    "detector": "..."
  }
}
```

`coverage` lists every applicable rule and whether its checks passed, failed, did not run, or require review. Results are deterministic when the input, configuration, standard pack, checker revision, detector revision, and thresholds do not change.

## Rewrite operation

The rewrite operation accepts the analysis input plus rewrite settings and returns one candidate:

```json
{
  "candidate": "Remove the component.",
  "candidate_status": "review_required",
  "diff": [],
  "before": {
    "findings": []
  },
  "after": {
    "findings": []
  },
  "protected_spans": {
    "status": "passed"
  },
  "revisions": {
    "standard": "issue-9@sha256:...",
    "checker": "...",
    "detector": "...",
    "rewriter": "..."
  }
}
```

Candidate statuses are `review_required` and `rejected`. A candidate is rejected after a protected-span failure, malformed model output, resource-limit failure, or configured safety veto. The system does not produce an `approved` status. Approval belongs to the document owner.

## Dataset records

Detector and rewriter training use one shared record format.

```json
{
  "id": "manual-17/paragraph-42",
  "document_id": "manual-17",
  "unit_type": "paragraph",
  "source": "The original complicated text.",
  "annotations": [
    {
      "rule_id": "3.4",
      "label": "violation",
      "spans": [
        {
          "start": 13,
          "end": 25
        }
      ],
      "label_source": "human_reviewed",
      "review_state": "adjudicated"
    }
  ],
  "accepted_rewrites": ["The clear STE text."],
  "protected_spans": [],
  "split": "train",
  "provenance": {
    "source_collection": "example",
    "source_record": "17/42"
  }
}
```

### Dataset fields

| Field | Required | Type | Meaning |
| --- | --- | --- | --- |
| `id` | Yes | string | Stable row identity within a dataset revision. |
| `document_id` | Yes | string | Source-document identity and split boundary. |
| `unit_type` | Yes | enum | `sentence`, `paragraph`, `procedure_step`, `note`, `caution`, or `warning`. |
| `source` | Yes | string | Original English text. |
| `annotations` | Yes | array | Rule labels and source spans. An empty array means that no reviewed label is present. |
| `accepted_rewrites` | No | string array | Human-accepted STE100 candidates. |
| `protected_spans` | Yes | array | Half-open UTF-8 byte ranges that rewriting must preserve. |
| `split` | Yes | enum | Dataset role. |
| `provenance` | Yes | object | Source collection and stable source identity. |

An annotation requires `rule_id`, `label`, `spans`, `label_source`, and `review_state`. A weak annotation can include `confidence` and `generator_revision`. Human annotations can include reviewer identities in restricted review records; published training rows use an adjudication record ID instead.

### Dataset rules

`id` is unique within a dataset revision. `document_id` defines the split boundary. All units from one source document belong to one split.

Annotation sources are `standard_example`, `deterministic_rule`, `spacy_weak`, `synthetic_transformation`, `teacher`, and `human_reviewed`. Review states are `unreviewed`, `reviewed`, and `adjudicated`.

Weak or absent labels are not negative labels. Model-selection sets contain only human-reviewed or adjudicated labels. Accepted rewrites can contain more than one valid target.

The split is one of `train`, `development`, `validation`, or `test`. Validation is report-only. Test remains sealed until the exact release candidate passes all earlier gates.

## Model manifests

Each learned artifact has a manifest containing:

- model kind and architecture
- model and tokenizer digests
- standard-pack revision
- training dataset revisions and split manifests
- code and configuration revisions
- training seed and numerical policy
- rule thresholds for a detector
- decoding settings for a rewriter
- evaluation report revision
- registered role and approval state

A model artifact cannot replace its manifest with a later report. A new manifest identifies a new artifact revision.

## Runtime sequence

Analysis runs in this order:

1. Validate request and resource limits.
2. Load and validate local standard and project data.
3. Parse the document and identify protected spans.
4. Run deterministic checks.
5. Run the learned detector when configured.
6. Produce findings and complete coverage.

Rewriting continues from the same parsed document:

1. Select one supported document unit.
2. Replace protected spans with sentinels.
3. Generate one candidate.
4. Validate sentinels and restore original content.
5. Parse and check the candidate.
6. Compare structure and all facts, including numbers and units.
7. Return the candidate and diff together with checks and review requirements.

No runtime step downloads code, models, standards, or project data. Callers install or mount approved artifacts before startup.

## Resource and safety limits

The runtime applies fixed limits to input bytes, document units, model tokens, output tokens, processing time, and memory. An over-limit unit is not truncated. The operation returns a bounded error or marks the unit for review.

Raw document text is not logged by default. Diagnostics use record IDs, counts, timings, model revisions, and rule IDs. Applications can store text only under their own explicit retention policy.

Model output is always treated as text. Browser integrations insert it through text APIs and never parse it as markup.

## Evaluation contracts

Detector evaluation reports raw support, precision, recall, false positives, false negatives, span results, and calibration for every rule. It also reports false alarms per 1,000 words and results by document collection.

Rewrite evaluation reports violations removed, violations introduced, accepted rewrites, meaning-preservation judgments, omitted or added facts, protected-content results, changes to valid input, and document-structure results. Readability metrics can be diagnostic but cannot select a release on their own.

A safety-sensitive omission or changed protected fact vetoes release even when aggregate quality improves.

## Boundaries

This system assists authors and reviewers. It does not replace the ASD-STE100 standard, an organization’s terminology process, or human approval of technical content.

The detector does not prove that text without findings is compliant. The rewriter does not prove that its candidate preserves all intended meaning. Rules outside automatic coverage remain visible in the response.

The repository’s MIT license covers original code and documentation. ASD source material retains the copyright terms described in [`../NOTICE`](../NOTICE).

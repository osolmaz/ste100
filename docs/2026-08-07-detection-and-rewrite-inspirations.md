---
title: Detection and rewrite research inspirations
author: Onur Solmaz <2453968+osolmaz@users.noreply.github.com>
date: 2026-08-07
---

# Detection and rewrite research inspirations

This document records possible inspirations for the STE100 detector and rewriter. The cited work studies response revision, AI-writing style, mixed authorship, or model-output distributions. Those tasks differ from checking a controlled language. Their data and training methods can still inform the STE100 program.

These references are research inputs. They do not define ASD-STE100 requirements and are not production dependencies.

## Conversation revision mining

An existing private response-style project established a deterministic, branch-aware method for extracting revision pairs from coding-agent conversations. It retains the original request, initial response, explicit user feedback, and revised response. It also records the source agent and model together with timestamps and hashes. It excludes system prompts, hidden reasoning, and tool traffic.

The same extraction method can find broader feedback such as requests to simplify an explanation, remove jargon, shorten an answer, use direct language, restore missing detail, or correct an over-simplification. Each observed sequence has this shape:

```text
original request
→ initial response
→ explicit user feedback
→ revised response
```

The user feedback supplies real preference evidence. The revised response is not automatically an STE100 target. A mined pair remains weak data until the rule checker and a human reviewer assess it.

### Possible uses

Conversation pairs can support direct rewrite training and pairwise ranking. They can also supply hard examples where a simplification removed an important fact. Running the deterministic checker and spaCy bootstrap rules on both versions gives proposed rule deltas for detector training.

Edit-distance measurements can separate small corrections from complete rewrites. Model and source metadata permit holdouts by conversation and time. Other holdouts separate agent and model families. These holdouts matter because a detector must learn STE100 requirements instead of learning the style of one assistant model.

Silence is not approval. Only explicit feedback creates a preference pair. All units from one conversation must stay in one dataset split.

### Limits

Coding-agent responses are technical but do not represent maintenance manuals or procedural instructions. They contain model-specific habits and conversational structure. Conversation data can bootstrap the program, but natural human-authored documents must remain part of training and evaluation.

The corpus stays private unless each source has a separate publication decision. Public benchmark records require redistributable source material or newly authored text.

## Antislop

Sam Paech’s [Antislop announcement](https://x.com/sam_paech/status/1982247368725565853) links the [Antislop paper](https://arxiv.org/abs/2510.15061), [Auto-Antislop](https://github.com/sam-paech/auto-antislop), and [Not-X-But-Y Benchmark](https://github.com/sam-paech/not-x-but-y-bench). A related [Slop Score post](https://x.com/sam_paech/status/1987039136684056727) describes a browser tool optimized for longer essays and creative writing.

Auto-Antislop generates model responses, measures words and phrases that occur more often than in human reference writing, and creates preference data that suppresses those patterns. The Not-X-But-Y benchmark counts a specific construction across many prompts and reports its frequency per 1,000 characters against a human baseline.

### Transfer to STE100

A reviewed STE100 corpus can provide a distribution profile for words, parts of speech, sentence forms, and recurring phrases. Rewriter output can be compared with that profile to find new model habits. Rule-specific phrase counts can also reveal when a student repeatedly chooses one valid construction and makes the output unnatural.

Distribution differences are diagnostic. A frequent phrase is not an STE100 violation, and a human-like distribution does not prove compliance. These measurements must not replace rule findings or meaning review.

The two GitHub repositories use the MIT license. Their code still requires normal dependency and provenance review before reuse.

## EditLens and Open Pangram

The [Open Pangram thread](https://x.com/kthai1618/status/2036509515839856646) links the [EditLens paper](https://arxiv.org/abs/2510.03154), [EditLens code](https://github.com/pangramlabs/EditLens), and released model and dataset collection. EditLens studies how much an AI system changed human-written text.

EditLens begins with original and edited text. It computes an edit magnitude from cosine distance or semantic soft n-grams, validates the measurements against expert judgments, and trains a model to predict the edit magnitude from the edited text alone. The public work supports continuous scores as well as binary and ternary classifications.

### Transfer to STE100

Conversation revisions and human STE100 rewrites already form source-target pairs. Soft n-grams can estimate which phrases are new, while embedding distance can measure the overall size of a rewrite. These values can help stratify examples and identify unnecessary changes to valid text.

The measurements can also create soft span proposals. Human annotations remain authoritative for rule IDs and exact locations. A large edit can be correct, and a small edit can still change a critical value.

EditLens is available under CC BY-NC-SA 4.0. Its code, models, and data require a separate licensing decision before commercial or differently licensed use. The method can be studied without making the released artifacts dependencies.

## Pangram 4

The [Pangram 4 discussion](https://x.com/askalphaxiv/status/2082980246194958350) summarizes the [Pangram 4 technical report](https://arxiv.org/html/2607.27183). Pangram 4 combines document-level classification with token-level mixed-authorship labels.

The model uses one shared causal backbone and separate linear heads. Its token classes distinguish human, AI-assisted, and AI-generated text. Synthetic AI edits provide soft token labels through semantic n-gram alignment. Long documents use overlapping windows, and predictions for the same source token are combined before structured decoding.

Pangram 4 trains cheaper segment objectives first. It adds the token objective in a later stage because token training processes more context. Its Repeat2 method duplicates each causal-model input and supervises the second copy so every scored token can see the full window.

### Transfer to STE100

The multi-resolution design supports separate unit-level and token-level detector outputs. A first stage can learn rule applicability and sentence findings before a later stage adds span supervision. Overlapping windows can provide context for long paragraphs or document rules.

Repeat2 is specific to causal attention. A bidirectional detector encoder already gives each token left and right context, so the STE100 detector should not copy Repeat2 without a measured need.

Soft token labels from synthetic edits can help bootstrap spans. Exact-span results should remain diagnostic during the first release because alignment can be harder to learn and annotate than unit-level rule detection.

Pangram 4 is evidence about an adjacent task. Its reported AI-detection accuracy does not predict STE100 rule accuracy.

## Distribution Fine Tuning

Rosmine’s [Distribution Fine Tuning announcement](https://x.com/rosmine/status/2056406399471558872) proposes reducing the distance between model output and human reference writing instead of optimizing a loosely defined writing-quality score. The post reports improvements in several writing measures and fewer recurring model phrases.

The author later stated that the [technical report was withdrawn](https://x.com/rosmine/status/2077178594778837150) while a new version was being prepared. The public claims are not enough to reproduce or validate the method.

The general idea can motivate an output-distribution audit for an STE100 rewriter. It cannot support an implementation decision until a complete method and evaluation are available.

## Combined data strategy

The strongest combined approach uses several levels of evidence:

| Evidence | Use | Authority |
| --- | --- | --- |
| Issue 9 records | Rule definitions and verified examples | Normative source |
| Deterministic checks | Exact weak labels and runtime findings | Conclusive within declared coverage |
| spaCy patterns | Candidate grammar labels and spans | Weak |
| Controlled violations | Known transformation labels | Weak until source and transformation review |
| Conversation revisions | Pairwise clarity preferences and rewrite candidates | Weak |
| Edit-distance measures | Rewrite magnitude and soft changed regions | Diagnostic |
| Human annotation | Rule applicability, findings, and accepted rewrites | Gold after adjudication |
| Teacher output | Synthetic rewrite targets | Synthetic, even after automatic checks |

The detector can combine absolute rule labels from human data with pairwise ranking from revisions. The rewriter can learn directly from reviewed targets and later use qualified synthetic targets. Phrase-distribution audits can identify output artifacts after training.

No one evidence source is sufficient. In particular, checker-clean output must not become automatic rewrite truth, and conversation revisions must not become STE100 targets without review.

## Proposed experiments

A small first corpus can combine mined conversation revisions with legally usable technical documents. Reviewers should annotate rule applicability and violations for the highest-priority rule families. The same units can measure spaCy weak-label quality and teacher rewrite quality.

The detector experiment should compare unit-level classification with and without pairwise revision supervision. Span prediction remains a secondary result. The rewrite experiment should compare source-only input with detector-hint input and test whether hints produce a worthwhile gain.

Output audits should report rule findings, meaning judgments, protected-content results, edit magnitude, and phrase-distribution differences. The release decision continues to use the gates in [`STE100_SYSTEM.md`](STE100_SYSTEM.md).

## Open decisions

Before using these methods, the project must decide:

- which conversation sources are authorized for private training
- which technical corpora permit training and redistribution
- which human STE100 corpus defines the output-distribution reference
- whether EditLens artifacts are compatible with the intended use
- which weak-label fields remain report-only
- how model-family and time holdouts are constructed

These decisions belong in the dataset manifest and experiment plan before large-scale mining or generation begins.

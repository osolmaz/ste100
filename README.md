# ste100

`ste100` is an offline deterministic checker for ASD-STE100 Issue 9. It finds mechanical writing and vocabulary problems, cites the applicable rule and byte range, and shows which requirements still need human review.

The package includes a source-traceable Issue 9 dictionary and rule pack. `ste100 analyze` uses it automatically, so users do not need to supply a separate standard pack.

The checker does not certify official ASD-STE100 compliance.

## Install

`ste100` requires Python 3.12 or later.

```sh
uv tool install .
```

The default checker does not need network access or a language model.

Optional part-of-speech, morphology, imperative, and passive-voice checks use the pinned spaCy pipeline:

```sh
uv tool install '.[spacy]' \
  --with 'https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl'
```

All runtime files must already be installed before offline use.

## Analyze a file

```sh
ste100 analyze manual.txt
```

Use JSON output for integrations:

```sh
ste100 analyze manual.txt --format json
```

Enable the optional pinned spaCy checks:

```sh
ste100 analyze manual.txt --spacy --format json
```

A result reports one of four states for every Issue 9 rule and general recommendation. `passed` means the complete mechanical requirement ran and passed. `failed` marks a conclusive violation. `human_review` means that the requirement or remaining clause needs judgment. `not_applicable` means that the document does not contain the applicable structure.

The command exits with status `1` when it finds a conclusive violation and `2` for invalid input or configuration.

## Project terminology

A project dictionary approves technical nouns and verbs that do not belong in the general dictionary:

```json
{
  "format_version": "1",
  "terms": [
    {
      "term": "fuel boost pump",
      "category": "technical_noun",
      "approved_forms": ["fuel boost pumps"],
      "meaning": "A pump that increases fuel pressure",
      "source": "Aircraft glossary"
    }
  ]
}
```

Validate and use it:

```sh
ste100 validate-project-dictionary project-terms.json
ste100 analyze manual.txt --project-dictionary project-terms.json
```

The validator rejects ambiguous forms and technical nouns longer than three words. A project term can use a general word that the standard dictionary does not approve for that part of speech.

## Rules and standard packs

Explain a rule and its automatic coverage:

```sh
ste100 explain 8.1
```

Validate another local Issue 9 pack:

```sh
ste100 validate-standard /path/to/issue-9-pack
ste100 analyze manual.txt --standard-pack /path/to/issue-9-pack
```

The bundled pack keeps every dictionary row tied to the exact source digest and page. Its manifest records the extracted counts. Differences from the totals printed in Issue 9 produce a warning, and valid source rows stay in the pack.

See [`docs/STE100_SYSTEM.md`](docs/STE100_SYSTEM.md) for the file formats, coverage rules, and checker boundaries.

## Standard and license

The source specification is [ASD-STE100 Issue 9](https://www.asd-ste100.org/assets/files/ASD-STE100_ISSUE9.pdf), published by ASD. The searchable text copy is [`docs/ASD-STE100_ISSUE9.txt`](docs/ASD-STE100_ISSUE9.txt).

The MIT license covers this repository's original code and documentation. ASD source material remains under the terms in [`NOTICE`](NOTICE).

[MIT](LICENSE)

# ste100

`ste100` is an offline checker for parts of ASD-STE100 Issue 9. It checks pasted or saved technical text against an extracted dictionary and a set of source-backed writing checks.

The tool does not certify ASD-STE100 compliance. `PASS` means that the checks implemented by this tool found no issue. Rules that the tool cannot determine produce no result.

## Install

`ste100` requires Python 3.12 or later.

```sh
uv tool install .
```

The default checks run without network access or a language model.

Optional part-of-speech and verb-form checks use a pinned spaCy pipeline. The same pipeline supports imperative and note checks, plus passive voice:

```sh
uv tool install '.[spacy]' \
  --with 'https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl'
```

Install all runtime files before offline use.

## Check a file

```sh
ste100 analyze manual.txt
```

Text output starts with `PASS` or `FAIL`. A failed result lists each source span once with every applicable rule number.

Use JSON output for integrations:

```sh
ste100 analyze manual.txt --format json
```

The JSON result contains:

```json
{
  "standard_id": "ASD-STE100",
  "standard_issue": 9,
  "standard_digest": "sha256:...",
  "passed": false,
  "findings": [
    {
      "rule_ids": ["1.1", "1.6"],
      "message": "'option' is listed as unapproved. Use: alternative, can, possible.",
      "byte_range": {"start": 20, "end": 26},
      "excerpt": "option"
    }
  ]
}
```

The command exits with status `0` for `PASS`, `1` for `FAIL`, and `2` for invalid input or configuration.

Enable the optional spaCy checks with:

```sh
ste100 analyze manual.txt --spacy
```

## Project terms

ASD-STE100 permits approved technical nouns and technical verbs. Supply them in a project dictionary so the checker does not treat them as missing vocabulary:

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

Validate and use the file:

```sh
ste100 validate-project-dictionary project-terms.json
ste100 analyze manual.txt --project-dictionary project-terms.json
```

A word absent from both the extracted STE dictionary and the supplied project dictionary causes `FAIL`.

## Source data

The package includes an internal extraction of the Issue 9 rule summaries and dictionary table. It is not an official machine-readable ASD data set.

Show an extracted rule or general recommendation:

```sh
ste100 explain 8.1
ste100 explain GR-1
```

Validate another local extraction:

```sh
ste100 validate-standard /path/to/issue-9-data
ste100 analyze manual.txt --standard-pack /path/to/issue-9-data
```

See [`docs/STE100_SYSTEM.md`](docs/STE100_SYSTEM.md) for the result and data formats.

## Standard and license

The source specification is [ASD-STE100 Issue 9](https://www.asd-ste100.org/assets/files/ASD-STE100_ISSUE9.pdf), published by ASD. The searchable text copy is [`docs/ASD-STE100_ISSUE9.txt`](docs/ASD-STE100_ISSUE9.txt).

The MIT license covers this repository's original code and documentation. ASD source material remains under the terms in [`NOTICE`](NOTICE).

[MIT](LICENSE)

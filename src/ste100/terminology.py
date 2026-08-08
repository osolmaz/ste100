"""Project terminology validation and deterministic longest-match lookup."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from ste100.document import char_to_byte_offsets
from ste100.models import ByteRange, ProjectDictionary, ProjectTerm
from ste100.standard import StandardPack, ValidationIssue, ValidationReport


@dataclass(frozen=True, slots=True)
class TermMatch:
    term: ProjectTerm
    text: str
    byte_range: ByteRange


def load_project_dictionary(path: Path) -> ProjectDictionary:
    with path.open(encoding="utf-8") as handle:
        return ProjectDictionary.model_validate(json.load(handle))


def validate_project_dictionary(
    project: ProjectDictionary,
    *,
    standard: StandardPack | None = None,
) -> ValidationReport:
    """Reject ambiguous forms and contradictions with reviewed vocabulary."""

    issues: list[ValidationIssue] = []
    owners: dict[str, str] = {}
    for term in project.terms:
        if term.category == "technical_noun" and len(term.term.split()) > 3:
            issues.append(
                ValidationIssue(
                    code="long_technical_noun",
                    message=f"technical noun has more than three words: {term.term}",
                )
            )
        forms = (term.term, *term.approved_forms)
        for form in forms:
            key = " ".join(form.casefold().split())
            prior = owners.get(key)
            if prior is not None and prior != term.term:
                issues.append(
                    ValidationIssue(
                        code="ambiguous_project_term",
                        message=f"form {form!r} belongs to both {prior!r} and {term.term!r}",
                    )
                )
            owners[key] = term.term
            if standard is not None:
                for entry in standard.dictionary_by_word.get(key, ()):
                    if entry.status == "unapproved":
                        issues.append(
                            ValidationIssue(
                                code="standard_conflict",
                                message=(
                                    f"project term form is unapproved in the standard: {form}"
                                ),
                            )
                        )
    return ValidationReport(tuple(issues))


class TermMatcher:
    """Find caller-approved terms with longest matches taking precedence."""

    def __init__(self, project: ProjectDictionary) -> None:
        forms: list[tuple[str, ProjectTerm]] = []
        for term in project.terms:
            for form in (term.term, *term.approved_forms):
                forms.append((form, term))
        forms.sort(key=lambda item: (-len(item[0]), item[0].casefold()))
        self._forms = tuple(forms)
        if forms:
            alternatives = "|".join(re.escape(form) for form, _ in forms)
            self._pattern: re.Pattern[str] | None = re.compile(
                rf"(?<![\w-])(?:{alternatives})(?![\w-])",
                re.IGNORECASE,
            )
            self._owners = {form.casefold(): term for form, term in forms}
        else:
            self._pattern = None
            self._owners = {}

    def find(self, text: str) -> tuple[TermMatch, ...]:
        if self._pattern is None:
            return ()
        offsets = char_to_byte_offsets(text)
        matches: list[TermMatch] = []
        occupied_until = -1
        for match in self._pattern.finditer(text):
            if match.start() < occupied_until:
                continue
            key = match.group().casefold()
            term = self._owners[key]
            matches.append(
                TermMatch(
                    term=term,
                    text=match.group(),
                    byte_range=ByteRange(
                        start=offsets[match.start()],
                        end=offsets[match.end()],
                    ),
                )
            )
            occupied_until = match.end()
        return tuple(matches)


def parse_project_dictionary(path: Path) -> tuple[ProjectDictionary | None, ValidationReport]:
    try:
        project = load_project_dictionary(path)
    except (OSError, ValueError, ValidationError, json.JSONDecodeError) as error:
        return None, ValidationReport(
            (
                ValidationIssue(
                    code="invalid_project_dictionary", message=str(error), path=str(path)
                ),
            )
        )
    return project, validate_project_dictionary(project)

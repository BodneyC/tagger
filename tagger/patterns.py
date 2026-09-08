"""Turn the user-facing `.tagger.yaml` pattern strings into compiled regexes.

Two different pattern styles are supported, deliberately:

* ``tag_pattern`` is a *template*: everything except ``{field}`` placeholders
  is treated as a literal string (and regex-escaped for you). This lets a repo
  write ``"v{major}.{minor}.{patch}"`` or ``"{major}.{minor}.{patch}-release"``
  without needing to know regex syntax, and without the literal ``.`` being
  misinterpreted as "any character".

* ``commit_pattern`` is a *raw regex* with ``{field}`` placeholders substituted
  in as named groups. This is because commit patterns often need real regex
  features (alternation, optional groups, character classes) around the
  placeholders, e.g. ``"[^:]*: {type}(\\({scope}\\)|): {message}"``.

Field placeholders in both styles must look like identifiers, e.g. ``{major}``
or ``{scope}`` -- specifically ``[A-Za-z_]\\w*`` -- so that a real regex
quantifier such as ``{2,4}`` in a commit pattern is never mistaken for a
placeholder (quantifiers start with a digit).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_FIELD_TOKEN = re.compile(r"\{([A-Za-z_]\w*)\}")

# The three fields every tag_pattern must define, exactly once each.
REQUIRED_VERSION_FIELDS = ("major", "minor", "patch")

# Default per-field regex fragments used when substituting `{field}` into a
# *commit* pattern. Callers can override/add to these via config.
DEFAULT_COMMIT_FIELD_PATTERNS: dict[str, str] = {
    "type": r"[A-Za-z]+!?",
    "scope": r"[^()]*",
    "message": r".*",
}
_DEFAULT_COMMIT_FIELD_FALLBACK = r".+?"

# Fields inside a tag_pattern get a numeric group; version fields must be
# digits so they can be parsed with int() and compared/incremented.
_TAG_FIELD_PATTERN = r"\d+"


class PatternError(ValueError):
    """Raised when a configured pattern is malformed or unusable."""


@dataclass(frozen=True, slots=True)
class TagPattern:
    """A compiled tag template: matches existing tags and formats new ones."""

    template: str
    regex: re.Pattern[str]

    @classmethod
    def compile(cls, template: str) -> TagPattern:
        field_names = _FIELD_TOKEN.findall(template)
        missing = [f for f in REQUIRED_VERSION_FIELDS if f not in field_names]
        if missing:
            raise PatternError(
                f"tag_pattern {template!r} is missing required field(s) "
                f"{missing}; it must contain {{major}}, {{minor}} and {{patch}} "
                "exactly once each"
            )
        extra = [f for f in field_names if f not in REQUIRED_VERSION_FIELDS]
        if extra:
            raise PatternError(
                f"tag_pattern {template!r} has unsupported field(s) {extra}; "
                "only {major}, {minor}, {patch} are allowed"
            )
        for name in REQUIRED_VERSION_FIELDS:
            if field_names.count(name) != 1:
                raise PatternError(f"tag_pattern {template!r} must use {{{name}}} exactly once")

        pattern_parts: list[str] = []
        pos = 0
        for match in _FIELD_TOKEN.finditer(template):
            literal = template[pos : match.start()]
            pattern_parts.append(re.escape(literal))
            name = match.group(1)
            pattern_parts.append(f"(?P<{name}>{_TAG_FIELD_PATTERN})")
            pos = match.end()
        pattern_parts.append(re.escape(template[pos:]))

        regex = re.compile("^" + "".join(pattern_parts) + "$")
        return cls(template=template, regex=regex)

    def format(self, major: int, minor: int, patch: int) -> str:
        return self.template.format(major=major, minor=minor, patch=patch)


@dataclass(frozen=True, slots=True)
class CommitPattern:
    """A compiled commit-subject regex built from a raw-regex + placeholders."""

    template: str
    regex: re.Pattern[str]
    field_names: tuple[str, ...]

    @classmethod
    def compile(cls, template: str, field_patterns: dict[str, str] | None = None) -> CommitPattern:
        merged_patterns = {**DEFAULT_COMMIT_FIELD_PATTERNS, **(field_patterns or {})}
        field_names = tuple(_FIELD_TOKEN.findall(template))
        if "type" not in field_names:
            raise PatternError(f"commit_pattern {template!r} must define a {{type}} field")
        seen: set[str] = set()
        duplicates = [f for f in field_names if f in seen or seen.add(f)]  # type: ignore[func-returns-value]
        if duplicates:
            raise PatternError(
                f"commit_pattern {template!r} uses field(s) {duplicates} more than once"
            )

        raw_parts: list[str] = []
        pos = 0
        for match in _FIELD_TOKEN.finditer(template):
            raw_parts.append(template[pos : match.start()])
            name = match.group(1)
            frag = merged_patterns.get(name, _DEFAULT_COMMIT_FIELD_FALLBACK)
            raw_parts.append(f"(?P<{name}>{frag})")
            pos = match.end()
        raw_parts.append(template[pos:])

        try:
            regex = re.compile("".join(raw_parts))
        except re.error as exc:
            raise PatternError(
                f"commit_pattern {template!r} did not compile to valid regex: {exc}"
            ) from exc
        return cls(template=template, regex=regex, field_names=field_names)

    def match(self, subject: str) -> re.Match[str] | None:
        return self.regex.search(subject)

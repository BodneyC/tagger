"""Shared data types for repo-tagger."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum


class BumpLevel(IntEnum):
    """Semver bump levels, ordered so max() picks the highest-precedence bump."""

    NONE = 0
    PATCH = 1
    MINOR = 2
    MAJOR = 3

    @classmethod
    def from_name(cls, name: str) -> BumpLevel:
        try:
            return cls[name.upper()]
        except KeyError as exc:
            valid = ", ".join(m.name for m in cls)
            raise ValueError(f"Unknown bump level {name!r}; expected one of {valid}") from exc


@dataclass(frozen=True, slots=True)
class Version:
    """A parsed semver-style version extracted from a tag."""

    major: int
    minor: int
    patch: int

    def bumped(self, level: BumpLevel) -> Version:
        if level is BumpLevel.MAJOR:
            return Version(self.major + 1, 0, 0)
        if level is BumpLevel.MINOR:
            return Version(self.major, self.minor + 1, 0)
        if level is BumpLevel.PATCH:
            return Version(self.major, self.minor, self.patch + 1)
        return self

    def as_tuple(self) -> tuple[int, int, int]:
        return (self.major, self.minor, self.patch)

    def __str__(self) -> str:  # human-friendly, not used for the actual git tag
        return f"{self.major}.{self.minor}.{self.patch}"


@dataclass(frozen=True, slots=True)
class TaggedVersion:
    """A git tag paired with the version it was parsed into."""

    tag: str
    version: Version


@dataclass(frozen=True, slots=True)
class Commit:
    """A single commit's subject + body, as returned by git log."""

    sha: str
    message: str  # full message: subject + blank line + body, if any

    @property
    def subject(self) -> str:
        return self.message.splitlines()[0] if self.message else ""


@dataclass(frozen=True, slots=True)
class CommitClassification:
    """The bump level a single commit contributes, plus why."""

    commit: Commit
    level: BumpLevel
    matched_type: str | None = None
    reason: str = ""


@dataclass(frozen=True, slots=True)
class BumpResult:
    """The overall outcome of scanning a repo and deciding on a bump."""

    previous_tag: str | None
    previous_version: Version | None
    level: BumpLevel
    next_version: Version | None
    next_tag: str | None
    classifications: list[CommitClassification] = field(default_factory=list)

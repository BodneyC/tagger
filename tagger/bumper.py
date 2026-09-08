"""Decide how much to bump, based on commit messages since the last tag."""

from __future__ import annotations

from tagger.config import Config
from tagger.models import (
    BumpLevel,
    BumpResult,
    Commit,
    CommitClassification,
    TaggedVersion,
    Version,
)
from tagger.patterns import CommitPattern, TagPattern


def classify_commit(
    commit: Commit, commit_pattern: CommitPattern, config: Config
) -> CommitClassification:
    """Work out what bump level (if any) a single commit contributes."""
    if config.breaking_change_marker and config.breaking_change_marker in commit.message:
        return CommitClassification(
            commit=commit,
            level=BumpLevel.MAJOR,
            reason=f"contains {config.breaking_change_marker!r} marker",
        )

    match = commit_pattern.match(commit.subject)
    if match is None:
        return CommitClassification(
            commit=commit,
            level=BumpLevel.NONE,
            reason="subject did not match commit_pattern",
        )

    commit_type = match.group("type")
    bare_type = commit_type.rstrip("!")
    is_bang_breaking = commit_type.endswith("!")

    if is_bang_breaking:
        return CommitClassification(
            commit=commit,
            level=BumpLevel.MAJOR,
            matched_type=commit_type,
            reason="type has a '!' breaking-change suffix",
        )
    if bare_type in config.major_types:
        level = BumpLevel.MAJOR
    elif bare_type in config.minor_types:
        level = BumpLevel.MINOR
    elif bare_type in config.patch_types:
        level = BumpLevel.PATCH
    else:
        level = BumpLevel.NONE

    return CommitClassification(
        commit=commit,
        level=level,
        matched_type=commit_type,
        reason=f"type {commit_type!r} maps to {level.name}",
    )


def determine_bump(
    commits: list[Commit], commit_pattern: CommitPattern, config: Config
) -> list[CommitClassification]:
    return [classify_commit(c, commit_pattern, config) for c in commits]


def compute_bump_result(
    previous: TaggedVersion | None,
    commits: list[Commit],
    commit_pattern: CommitPattern,
    tag_pattern: TagPattern,
    config: Config,
) -> BumpResult:
    classifications = determine_bump(commits, commit_pattern, config)
    level = max((c.level for c in classifications), default=BumpLevel.NONE)

    previous_version = previous.version if previous else None
    base_version = previous_version if previous_version is not None else Version(0, 0, 0)

    if level is BumpLevel.NONE:
        next_version = None
        next_tag = None
    else:
        next_version = base_version.bumped(level)
        next_tag = tag_pattern.format(
            major=next_version.major, minor=next_version.minor, patch=next_version.patch
        )

    return BumpResult(
        previous_tag=previous.tag if previous else None,
        previous_version=previous_version,
        level=level,
        next_version=next_version,
        next_tag=next_tag,
        classifications=classifications,
    )
